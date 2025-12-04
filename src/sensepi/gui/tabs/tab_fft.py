"""Live FFT / spectrum tab for MPU6050 samples."""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Sequence, Tuple, TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from matplotlib.axes import Axes
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from ...analysis import filters
from ..config.acquisition_state import (
    CalibrationOffsets,
    GuiAcquisitionConfig,
    SensorSelectionConfig,
)
from ...config.app_config import AppConfig, PlotPerformanceConfig
from ...core.ringbuffer import RingBuffer
from ...data import StreamingDataBuffer
from ...tools.debug import debug_enabled
from . import SampleKey

if TYPE_CHECKING:  # pragma: no cover - circular import guard
    from .tab_recorder import RecorderTab
    from .tab_signals import SignalsTab

DEFAULT_FFT_WINDOW_S = 2.0
MIN_FFT_WINDOW_S = 0.5
MAX_FFT_WINDOW_S = 10.0

DEFAULT_FFT_UPDATE_MS = 500  # fallback if config missing
MIN_FFT_UPDATE_MS = 50
MAX_FFT_UPDATE_MS = 2000

DEFAULT_MAX_FREQUENCY_HZ = 200.0  # cap plotted frequency if useful

logger = logging.getLogger(__name__)


class FftTab(QWidget):
    """
    Live spectrum/FFT view for the streaming MPU6050 channels.

    Responsibilities:
    - Pull sliding windows of samples from the shared
      :class:`StreamingDataBuffer` (owned by :class:`RecorderTab`).
    - Render frequency-domain plots that complement :class:`SignalsTab`'s time
      series, using matching sensor/channel layouts.
    - Track stream rate updates and refresh interval hints emitted by the
      signals tab so spectral analysis follows live data pacing.
    """

    def __init__(
        self,
        recorder_tab: RecorderTab,
        signals_tab: "SignalsTab | None" = None,
        parent: Optional[QWidget] = None,
        app_config: AppConfig | None = None,
    ) -> None:
        super().__init__(parent)

        self._recorder_tab = recorder_tab
        self._signals_tab: SignalsTab | None = signals_tab
        self._app_config: AppConfig = app_config or AppConfig()
        self._gui_acq_config: GuiAcquisitionConfig | None = None
        self._sensor_selection: SensorSelectionConfig | None = None
        self._calibration_offsets: CalibrationOffsets | None = None
        plot_perf = getattr(self._app_config, "plot_performance", None)
        if not isinstance(plot_perf, PlotPerformanceConfig):
            plot_perf = PlotPerformanceConfig()
        self._plot_perf_config: PlotPerformanceConfig = plot_perf
        self._max_subplots = self._plot_perf_config.normalized_max_subplots()
        self._stream_rate_hz: float = 0.0
        self._refresh_interval_ms: int = self._clamp_fft_interval(
            self._plot_perf_config.fft_refresh_interval_ms()
        )
        self._stream_active: bool = False
        self._last_rendered_latest_ts: Optional[float] = None
        self._force_next_update: bool = True
        self._fft_axes: Dict[SampleKey, Axes] = {}
        self._fft_lines: Dict[SampleKey, Line2D] = {}
        self._current_layout: Tuple[Tuple[int, ...], Tuple[str, ...]] | None = None
        # Bound how many samples each FFT uses so the GUI stays responsive.
        self._max_fft_samples = 4096
        self._fft_decimation_target = 2048
        self._fft_size = 512
        self._fft_sample_rate_hz: float = 1.0
        self._fft_freqs = np.fft.rfftfreq(self._fft_size, 1.0 / self._fft_sample_rate_hz)
        self._fft_window = np.hanning(self._fft_size)
        self._default_ylim = (0.0, 1.0)

        # Figure / canvas -------------------------------------------------------
        self._figure = Figure(figsize=(5, 3), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)

        # Controls --------------------------------------------------------------
        controls_group = QGroupBox("FFT settings")
        form = QFormLayout(controls_group)

        # View selection
        top_row = QHBoxLayout()
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItem(
            "AX / AY / GZ (9 charts)", userData="default3"
        )
        self.view_mode_combo.addItem(
            "All axes (18 charts)", userData="all6"
        )

        top_row.addWidget(QLabel("View:"))
        top_row.addWidget(self.view_mode_combo)
        top_row.addStretch()
        form.addRow(top_row)

        # FFT window length (seconds)
        self.window_spin = QDoubleSpinBox()
        self.window_spin.setRange(MIN_FFT_WINDOW_S, MAX_FFT_WINDOW_S)
        self.window_spin.setSingleStep(0.5)
        default_window_s = self._plot_perf_config.normalized_time_window_s()
        self.window_spin.setValue(default_window_s)
        form.addRow("Window (s):", self.window_spin)

        # Detrend / lowpass options
        self.detrend_check = QCheckBox("Detrend")
        self.lowpass_check = QCheckBox("Low-pass filter")

        self.lowpass_cutoff = QDoubleSpinBox()
        self.lowpass_cutoff.setRange(0.1, 5000.0)
        self.lowpass_cutoff.setSingleStep(1.0)
        self.lowpass_cutoff.setValue(100.0)
        form.addRow(self.detrend_check)
        row_lp = QHBoxLayout()
        row_lp.addWidget(self.lowpass_check)
        row_lp.addWidget(QLabel("Cutoff (Hz):"))
        row_lp.addWidget(self.lowpass_cutoff)
        row_lp.addStretch()
        form.addRow(row_lp)

        # FFT refresh control (decoupled from window length)
        self.fft_interval_spin = QDoubleSpinBox()
        self.fft_interval_spin.setRange(MIN_FFT_UPDATE_MS, MAX_FFT_UPDATE_MS)
        self.fft_interval_spin.setSingleStep(50.0)
        self.fft_interval_spin.setDecimals(0)
        self.fft_interval_spin.setValue(float(self._refresh_interval_ms))
        self.fft_interval_spin.setSuffix(" ms")
        self.fft_interval_spin.valueChanged.connect(
            lambda ms: self.set_refresh_interval_ms(int(ms))
        )
        form.addRow("FFT refresh:", self.fft_interval_spin)

        # Status label
        self._status_label = QLabel("Waiting for data...")

        # Layout ---------------------------------------------------------------
        layout = QVBoxLayout(self)
        layout.addWidget(controls_group)
        layout.addWidget(self._canvas)
        layout.addWidget(self._status_label)

        # NOTE: This timer drives the legacy FFT refresh cadence. Align with the
        # new acquisition config in the upcoming GUI refactor before changing it.
        # Timer to recompute FFT periodically
        self._timer = QTimer(self)
        self._timer.setInterval(self._refresh_interval_ms)
        self._timer.timeout.connect(self._on_fft_timer)
        self._debug_fft_ema_ms: float = 0.0
        self._debug_fft_last_log: float = time.perf_counter()

        # Wiring
        self.view_mode_combo.currentIndexChanged.connect(self._on_controls_changed)
        self.window_spin.valueChanged.connect(self._on_controls_changed)
        self.window_spin.valueChanged.connect(self._update_fft_timer_interval)
        self.detrend_check.toggled.connect(self._on_controls_changed)
        self.lowpass_check.toggled.connect(self._on_controls_changed)
        self.lowpass_cutoff.valueChanged.connect(self._on_controls_changed)
        self._update_fft_timer_interval()
        self._draw_waiting()

    def apply_gui_acquisition_config(self, cfg: GuiAcquisitionConfig) -> None:
        """Backward-compatible alias for :meth:`update_acquisition_config`."""

        self.update_acquisition_config(cfg)

    def update_acquisition_config(self, config: GuiAcquisitionConfig) -> None:
        """
        Receive the latest GUI acquisition configuration (sampling rate, stream rate,
        record-only flag, calibration, etc.).
        """

        self._gui_acq_config = config
        if config.stream_rate_hz and config.stream_rate_hz > 0.0:
            self._stream_rate_hz = float(config.stream_rate_hz)
            self._ensure_fft_frequency_axis(self._stream_rate_hz)
        if config.record_only:
            if self._timer.isActive():
                self._timer.stop()
            self._status_label.setText("Record-only mode: live FFT disabled.")
        else:
            if self._stream_active and not self._timer.isActive():
                self._timer.start(self._refresh_interval_ms)
            self._request_full_refresh()
        if getattr(config, "calibration", None) is not None:
            try:
                self.set_calibration_offsets(config.calibration)
            except Exception:
                # Defensive: avoid breaking updates if calibration payload is missing.
                pass

    def set_sensor_selection(self, cfg: SensorSelectionConfig) -> None:
        """Backward-compatible alias for :meth:`update_sensor_selection`."""

        self.update_sensor_selection(cfg)

    def update_sensor_selection(self, selection: SensorSelectionConfig) -> None:
        """
        Receive the latest sensor/channel selection so FFT can restrict what it plots.
        """

        self._sensor_selection = selection
        self._request_full_refresh()

    def set_calibration_offsets(self, offsets: CalibrationOffsets | None) -> None:
        """
        Update calibration offsets used when preparing the FFT input.
        """

        self._calibration_offsets = offsets
        self._request_full_refresh()

    def set_record_only_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled:
            self._timer.stop()
            self._status_label.setText("Record-only mode: live FFT disabled.")
        else:
            if self._refresh_interval_ms > 0 and self._stream_active:
                self._timer.start(self._refresh_interval_ms)

    def _is_record_only(self) -> bool:
        cfg = getattr(self, "_gui_acq_config", None)
        return bool(getattr(cfg, "record_only", False))

    def _make_key(self, sensor_id: int, channel: str) -> SampleKey:
        return int(sensor_id), str(channel)

    def _clamp_fft_interval(self, interval_ms: float | int) -> int:
        try:
            interval = int(round(float(interval_ms)))
        except (TypeError, ValueError):
            interval = DEFAULT_FFT_UPDATE_MS
        return max(MIN_FFT_UPDATE_MS, min(interval, MAX_FFT_UPDATE_MS))

    def _active_stream_buffer(self) -> StreamingDataBuffer:
        """Return the current streaming buffer (prepping for shared LiveDataStore)."""
        return self._recorder_tab.data_buffer()

    def _get_buffer_window(
        self,
        key: SampleKey,
        *,
        window_s: float,
        data_buffer: StreamingDataBuffer | None = None,
    ) -> tuple[Sequence[float], Sequence[float]]:
        # Prefer reusing the time-windowed data held by SignalsTab; if that
        # is unavailable, fall back to querying the shared StreamingDataBuffer.
        sensor_id, channel = key
        window = self._window_from_signals_tab(sensor_id, channel, window_s)
        if window is not None:
            return window

        buffer = data_buffer or self._active_stream_buffer()
        return buffer.get_axis_series(sensor_id, channel, seconds=window_s)

    def _on_controls_changed(self, *args: object) -> None:
        """Trigger an FFT refresh when the user changes view/filter controls."""
        self._request_full_refresh()
        self._update_fft()

    def _request_full_refresh(self) -> None:
        self._force_next_update = True

    def _update_fft_timer_interval(self, *_: object) -> None:
        """Adjust the FFT refresh cadence based on the selected window length."""
        if not hasattr(self, "_timer"):
            return
        try:
            window_s = float(self.window_spin.value())
        except (TypeError, ValueError):
            window_s = DEFAULT_FFT_WINDOW_S
        window_s = max(MIN_FFT_WINDOW_S, min(window_s, MAX_FFT_WINDOW_S))
        desired_period_s = window_s / 2.0
        interval_ms = int(desired_period_s * 1000.0)
        self.set_refresh_interval_ms(interval_ms)

    def set_refresh_interval_ms(self, interval_ms: int) -> None:
        """Public setter so other tabs can tune how often the FFT updates."""
        clamped = self._clamp_fft_interval(interval_ms)
        self._refresh_interval_ms = clamped
        self._timer.setInterval(clamped)
        spin = getattr(self, "fft_interval_spin", None)
        if spin is not None:
            try:
                from PySide6.QtCore import QSignalBlocker

                blocker = QSignalBlocker(spin)
            except Exception:
                blocker = None
            spin.setValue(float(clamped))
            if blocker is not None:
                del blocker

    def set_max_fft_samples(self, n: int) -> None:
        """Public setter mainly for tests / tuning of the FFT sample cap."""
        self._max_fft_samples = max(256, int(n))

    def set_signals_tab(self, signals_tab: "SignalsTab | None") -> None:
        """Inject the SignalsTab reference so we can reuse its ring buffers."""
        self._signals_tab = signals_tab

    @Slot(str, float)
    def update_stream_rate(self, sensor_type: str, hz: float) -> None:
        """Receive stream-rate updates so FFT windows know how much data to expect."""
        if sensor_type != "mpu6050":
            return
        self._stream_rate_hz = float(hz) if hz > 0.0 else 0.0
        self._ensure_fft_frequency_axis(self._stream_rate_hz)
        self._request_full_refresh()

    def set_sampling_rate_hz(self, hz: float) -> None:
        """
        Manually set the nominal sampling/stream rate used by the FFT timer.

        This is used when we already know the target stream/plot rate from
        the GUI (GuiAcquisitionConfig) before the RecorderTab has measured
        and reported a real rate.

        Internally it just routes through update_stream_rate().
        """
        try:
            value = float(hz)
        except (TypeError, ValueError):
            # Ignore invalid values; keep existing rate
            return

        # Reuse the existing logic that already updates labels, timers, etc.
        self.update_stream_rate("mpu6050", value)

    @Slot()
    def on_stream_started(self) -> None:
        self._clear_layout()
        self._draw_waiting()
        self._status_label.setText("Streaming...")
        self._last_rendered_latest_ts = None
        self._request_full_refresh()
        self._stream_active = True
        if not self._timer.isActive() and not self._is_record_only():
            self._timer.start(self._refresh_interval_ms)

    @Slot()
    def on_stream_stopped(self) -> None:
        # Keep last spectrum visible but update status.
        self._status_label.setText("Stream stopped.")
        self._stream_active = False
        if self._timer.isActive():
            self._timer.stop()

    # --------------------------------------------------------------- internals
    @staticmethod
    def _channel_units(channel: str) -> str:
        ch = channel.lower()
        if ch in {"ax", "ay", "az"}:
            return "m/s²"
        if ch in {"gx", "gy", "gz"}:
            return "deg/s"
        return ""

    def _min_samples_required(self, window_s: float) -> int:
        """
        Return the minimum number of samples needed before running the FFT.

        We require at least half of the expected samples for the window, or
        a modest constant so short windows still work.
        """
        if self._stream_rate_hz > 0.0:
            expected = self._stream_rate_hz * window_s
            return max(8, int(expected * 0.5))
        return 8

    def _decimate_signal_for_fft(
        self,
        times: np.ndarray,
        values: np.ndarray,
        target_points: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Downsample arrays to ~target_points to cap FFT cost."""
        if target_points <= 0 or values.size <= target_points:
            return times, values

        step = max(2, values.size // target_points)
        indices = np.arange(0, values.size, step, dtype=int)
        if indices[-1] != values.size - 1:
            indices = np.append(indices, values.size - 1)
        return times[indices], values[indices]

    def _window_signal(
        self,
        buf: Sequence[Tuple[float, float]] | RingBuffer[Tuple[float, float]],
        window_s: float,
    ) -> tuple[np.ndarray, np.ndarray, float] | None:
        if buf is None:
            return None
        points = list(buf)
        if len(points) < 4:
            return None
        t_latest = points[-1][0]
        t_min = t_latest - window_s

        times = [t for (t, _v) in points if t >= t_min]
        values = [v for (t, v) in points if t >= t_min]
        if len(values) < 4 or times[-1] <= times[0]:
            return None

        times_arr = np.asarray(times, dtype=float)
        values_arr = np.asarray(values, dtype=float)

        if values_arr.size > self._max_fft_samples:
            times_arr = times_arr[-self._max_fft_samples :]
            values_arr = values_arr[-self._max_fft_samples :]

        if values_arr.size > self._fft_decimation_target:
            times_arr, values_arr = self._decimate_signal_for_fft(
                times_arr, values_arr, self._fft_decimation_target
            )
            if times_arr.size < 2 or values_arr.size < 2:
                return None

        dt = times_arr[-1] - times_arr[0]
        if dt <= 0.0:
            return None
        sample_rate_hz = (len(times_arr) - 1) / dt if dt > 0 else 1.0
        if sample_rate_hz <= 0.0:
            sample_rate_hz = self._stream_rate_hz if self._stream_rate_hz > 0.0 else 1.0
        return times_arr, values_arr, sample_rate_hz

    def _preprocess_signal(
        self,
        values: np.ndarray,
        sample_rate_hz: float,
    ) -> np.ndarray:
        signal = values.copy()
        if self.detrend_check.isChecked():
            signal = filters.detrend(signal)
        if self.lowpass_check.isChecked():
            cutoff = float(self.lowpass_cutoff.value())
            nyquist = 0.5 * sample_rate_hz
            if 0.0 < cutoff < nyquist:
                signal = filters.butter_lowpass(
                    signal,
                    cutoff_hz=cutoff,
                    sample_rate_hz=sample_rate_hz,
                )
        return signal

    def _ensure_fft_frequency_axis(self, sample_rate_hz: float | None = None) -> None:
        """Ensure the cached frequency axis matches the latest sampling rate."""
        if sample_rate_hz is None or sample_rate_hz <= 0.0:
            sample_rate_hz = self._stream_rate_hz
        sample_rate_hz = float(sample_rate_hz) if sample_rate_hz and sample_rate_hz > 0 else 1.0
        if np.isclose(sample_rate_hz, self._fft_sample_rate_hz, rtol=1e-3):
            return
        self._fft_sample_rate_hz = sample_rate_hz
        self._fft_freqs = np.fft.rfftfreq(self._fft_size, 1.0 / self._fft_sample_rate_hz)
        self._fft_window = np.hanning(self._fft_size)
        zero_line = np.zeros_like(self._fft_freqs)
        for line in self._fft_lines.values():
            line.set_xdata(self._fft_freqs)
            line.set_ydata(zero_line.copy())
        for ax in self._fft_axes.values():
            self._apply_frequency_limits(ax)

    def _apply_frequency_limits(self, ax: Axes) -> None:
        max_freq = float(DEFAULT_MAX_FREQUENCY_HZ)
        if self._fft_freqs.size > 0:
            max_freq = min(max_freq, float(self._fft_freqs[-1]))
        if max_freq <= 0.0 or not np.isfinite(max_freq):
            max_freq = 1.0
        ax.set_xlim(0.0, max_freq)
        ax.set_ylim(*self._default_ylim)

    def _compute_fft_magnitude(self, signal: np.ndarray) -> np.ndarray:
        """Return FFT magnitudes for the most recent fft_size samples."""
        if signal.size == 0:
            return np.zeros_like(self._fft_freqs)
        window = signal[-self._fft_size :]
        if window.size < self._fft_size:
            padded = np.zeros(self._fft_size, dtype=float)
            if window.size > 0:
                padded[-window.size :] = window
            window = padded
        windowed = window * self._fft_window
        fft_vals = np.fft.rfft(windowed)
        return np.abs(fft_vals)

    def _on_fft_timer(self) -> None:
        if not debug_enabled():
            self._update_fft()
            return

        start = time.perf_counter()
        self._update_fft()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        alpha = 0.2
        if self._debug_fft_ema_ms <= 0.0:
            self._debug_fft_ema_ms = elapsed_ms
        else:
            self._debug_fft_ema_ms = (
                alpha * elapsed_ms + (1.0 - alpha) * self._debug_fft_ema_ms
            )
        now_perf = time.perf_counter()
        if now_perf - self._debug_fft_last_log >= 5.0:
            interval = self._timer.interval() if hasattr(self, "_timer") else 0
            print(
                f"[DEBUG] fft_redraw interval={interval} ms ema≈{self._debug_fft_ema_ms:.2f} ms",
                flush=True,
            )
            self._debug_fft_last_log = now_perf

    def _update_fft(self) -> None:
        self._update_mpu6050_fft()

    def _update_mpu6050_fft(self) -> None:
        if self._is_record_only():
            self._status_label.setText("Record-only mode: live FFT disabled.")
            return

        data_buffer = self._active_stream_buffer()

        sensor_ids = self._resolve_sensor_ids(data_buffer)
        if self._sensor_selection is not None and self._sensor_selection.active_sensors:
            sensor_ids = [
                sid for sid in sensor_ids if sid in self._sensor_selection.active_sensors
            ]
        if not sensor_ids:
            self._draw_waiting()
            return

        latest_ts = data_buffer.latest_timestamp()
        if latest_ts is None:
            self._draw_waiting()
            return

        if (
            not self._force_next_update
            and self._last_rendered_latest_ts is not None
            and latest_ts <= self._last_rendered_latest_ts
        ):
            return

        view_mode = self.view_mode_combo.currentData()
        if self._sensor_selection is not None:
            channels = list(self._sensor_selection.active_channels)
            if not channels:
                channels = ["ax", "ay", "gz"]
        else:
            if view_mode == "default3":
                channels = ["ax", "ay", "gz"]
            else:
                channels = ["ax", "ay", "az", "gx", "gy", "gz"]

        window_s = float(self.window_spin.value())
        min_samples = self._min_samples_required(window_s)

        if not self._ensure_fft_layout(sensor_ids, channels):
            self._draw_waiting()
            return

        stats_samples = None
        stats_fs = None
        have_data = False

        for sensor_id in sensor_ids:
            for ch in channels:
                key = self._make_key(sensor_id, ch)
                timestamps, values = self._get_buffer_window(
                    key,
                    window_s=window_s,
                    data_buffer=data_buffer,
                )
                if (
                    self._sequence_length(values) < min_samples
                    or self._sequence_length(timestamps) < 2
                ):
                    self._clear_line(sensor_id, ch)
                    continue

                if self._calibration_offsets is not None and self._sequence_length(values):
                    offset = self._calibration_offsets.offset_for(sensor_id, ch)
                    if offset != 0.0:
                        try:
                            values = np.asarray(values, dtype=float) - float(offset)
                        except Exception:
                            values = [float(v) - float(offset) for v in values]

                points = list(zip(timestamps, values))
                prepared = self._window_signal(points, window_s)
                if prepared is None:
                    self._clear_line(sensor_id, ch)
                    continue

                _times_arr, values_arr, sample_rate_hz = prepared
                signal = self._preprocess_signal(values_arr, sample_rate_hz)

                axis_sample_rate = self._stream_rate_hz if self._stream_rate_hz > 0.0 else sample_rate_hz
                self._ensure_fft_frequency_axis(axis_sample_rate)
                magnitude = self._compute_fft_magnitude(signal)
                if magnitude.size == 0:
                    self._clear_line(sensor_id, ch)
                    continue

                self._update_fft_line(key, magnitude)
                have_data = True
                if stats_samples is None:
                    stats_samples = self._fft_size
                    stats_fs = axis_sample_rate

        if not have_data:
            self._status_label.setText("Waiting for data...")
            self._last_rendered_latest_ts = latest_ts
            self._force_next_update = False
            self._canvas.draw_idle()
            return

        self._canvas.draw_idle()
        self._last_rendered_latest_ts = latest_ts
        self._force_next_update = False
        if stats_samples is not None and stats_fs is not None:
            self._status_label.setText(
                f"Window: {window_s:.1f} s, FFT samples: {stats_samples}, fs≈{stats_fs:.1f} Hz"
            )

    def _apply_subplot_limits(
        self,
        sensor_ids: Sequence[int],
        channels: Sequence[str],
    ) -> tuple[list[int], list[str], bool, bool]:
        limited_sensors = list(sensor_ids)
        limited_channels = list(channels)
        if not limited_sensors or not limited_channels:
            return limited_sensors, limited_channels, False, False
        limit = self._max_subplots
        if not limit or limit <= 0:
            return limited_sensors, limited_channels, False, False
        total = len(limited_sensors) * len(limited_channels)
        if total <= limit:
            return limited_sensors, limited_channels, False, False

        trimmed_channels = False
        max_channels = max(1, limit // len(limited_sensors))
        if len(limited_channels) > max_channels:
            limited_channels = limited_channels[:max_channels]
            trimmed_channels = True
        trimmed_sensors = False
        max_sensors = max(1, limit // len(limited_channels))
        if len(limited_sensors) > max_sensors:
            limited_sensors = limited_sensors[:max_sensors]
            trimmed_sensors = True
        return limited_sensors, limited_channels, trimmed_channels, trimmed_sensors

    def _ensure_fft_layout(self, sensor_ids: Sequence[int], channels: Sequence[str]) -> bool:
        sensor_list = [int(s) for s in sensor_ids]
        channel_list = [str(ch) for ch in channels]
        if not sensor_list or not channel_list:
            return False

        original_sensor_count = len(sensor_list)
        original_channel_count = len(channel_list)
        (
            sensor_list,
            channel_list,
            trimmed_channels,
            trimmed_sensors,
        ) = self._apply_subplot_limits(sensor_list, channel_list)
        if not sensor_list or not channel_list:
            return False

        signature = (tuple(sensor_list), tuple(channel_list))
        should_log_limits = (
            (trimmed_channels or trimmed_sensors)
            and signature != self._current_layout
        )
        if should_log_limits:
            limit = self._max_subplots
            if trimmed_channels and original_channel_count > len(channel_list):
                logger.warning(
                    "FFT tab: reducing visible channels from %d to %d to honor max subplot limit (%s).",
                    original_channel_count,
                    len(channel_list),
                    limit,
                )
            if trimmed_sensors and original_sensor_count > len(sensor_list):
                logger.warning(
                    "FFT tab: reducing visible sensors from %d to %d to honor max subplot limit (%s).",
                    original_sensor_count,
                    len(sensor_list),
                    limit,
                )

        if signature == self._current_layout:
            return True

        self._current_layout = signature
        self._fft_axes.clear()
        self._fft_lines.clear()
        self._figure.clear()
        self._ensure_fft_frequency_axis()

        nrows = len(sensor_list)
        ncols = len(channel_list)
        subplot_index = 1
        for row_idx, sensor_id in enumerate(sensor_list):
            for col_idx, ch in enumerate(channel_list):
                ax = self._figure.add_subplot(nrows, ncols, subplot_index)
                subplot_index += 1
                zero_line = np.zeros_like(self._fft_freqs)
                line, = ax.plot(self._fft_freqs, zero_line, lw=0.9)
                key = self._make_key(sensor_id, ch)
                self._fft_axes[key] = ax
                self._fft_lines[key] = line
                if row_idx == nrows - 1:
                    ax.set_xlabel("Frequency [Hz]")
                if col_idx == 0:
                    ax.set_ylabel("Magnitude")
                units = self._channel_units(ch)
                title = f"S{sensor_id} {ch.upper()}"
                if units:
                    title = f"{title} [{units}]"
                ax.set_title(title)
                ax.grid(True)
                self._apply_frequency_limits(ax)

        self._figure.tight_layout()
        self._canvas.draw_idle()
        return True

    def _update_fft_line(self, key: SampleKey, magnitude: np.ndarray) -> None:
        line = self._fft_lines.get(key)
        ax = self._fft_axes.get(key)
        if line is None or ax is None:
            return

        if magnitude.size != self._fft_freqs.size:
            padded = np.zeros_like(self._fft_freqs)
            count = min(len(padded), magnitude.size)
            if count > 0:
                padded[:count] = magnitude[:count]
            magnitude = padded

        line.set_ydata(magnitude)
        self._maybe_expand_ylim(ax, magnitude)

    def _clear_line(self, sensor_id: int, channel: str) -> None:
        key = self._make_key(sensor_id, channel)
        line = self._fft_lines.get(key)
        ax = self._fft_axes.get(key)
        if line is not None:
            line.set_ydata(np.zeros_like(self._fft_freqs))
        if ax is not None:
            ax.set_ylim(*self._default_ylim)

    def _maybe_expand_ylim(self, ax: Axes, magnitude: np.ndarray) -> None:
        if magnitude.size == 0:
            return
        try:
            mag_max = float(np.nanmax(magnitude))
        except ValueError:
            return
        if not np.isfinite(mag_max) or mag_max <= 0.0:
            return

        _current_min, current_max = ax.get_ylim()
        if current_max <= 0.0 or mag_max > current_max * 0.95:
            new_max = max(mag_max * 1.1, self._default_ylim[1])
            ax.set_ylim(self._default_ylim[0], new_max)

    def _clear_layout(self) -> None:
        self._fft_axes.clear()
        self._fft_lines.clear()
        self._current_layout = None
        self._figure.clear()

    def _draw_waiting(self) -> None:
        self._clear_layout()
        ax = self._figure.add_subplot(111)
        ax.set_xlabel("Frequency [Hz]")
        ax.set_ylabel("Magnitude")
        ax.set_title("Waiting for data...")
        self._canvas.draw_idle()
        self._status_label.setText("Waiting for data...")

    def _window_from_signals_tab(
        self,
        sensor_id: int,
        channel: str,
        window_s: float,
    ) -> tuple[Sequence[float], Sequence[float]] | None:
        signals_tab = self._signals_tab
        if signals_tab is None:
            return None
        getter = getattr(signals_tab, "get_time_series_window", None)
        if getter is None:
            return None
        try:
            times, values = getter(sensor_id, channel, window_s)
        except Exception:
            return None
        if times is None or values is None:
            return None
        if self._sequence_length(times) < 2 or self._sequence_length(values) < 2:
            return None
        return times, values

    def _sequence_length(self, seq: object) -> int:
        """Return len(seq) while tolerating numpy arrays."""
        if seq is None:
            return 0
        try:
            return len(seq)  # type: ignore[arg-type]
        except TypeError:
            size = getattr(seq, "size", None)
            if size is None:
                return 0
            try:
                return int(size)
            except (TypeError, ValueError):
                return 0

    def _sensor_ids_from_signals_tab(self) -> list[int]:
        signals_tab = self._signals_tab
        if signals_tab is None:
            return []
        getter = getattr(signals_tab, "live_sensor_ids", None)
        if getter is None:
            return []
        try:
            ids = list(getter())
        except Exception:
            return []
        normalized: list[int] = []
        for sensor_id in ids:
            try:
                normalized.append(int(sensor_id))
            except (TypeError, ValueError):
                continue

        deduped: list[int] = []
        for sensor_id in normalized:
            if sensor_id not in deduped:
                deduped.append(sensor_id)
        return sorted(deduped)

    def _resolve_sensor_ids(self, data_buffer: StreamingDataBuffer) -> list[int]:
        sensor_ids = self._sensor_ids_from_signals_tab()
        if sensor_ids:
            return sensor_ids
        raw_ids = data_buffer.get_sensor_ids()
        return sorted(raw_ids, key=str)
