from __future__ import annotations

import math
from typing import Dict, Iterable, Optional, Set, Tuple

from PySide6.QtCore import QSettings, Signal, Slot, QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ..widgets import CollapsibleSection
from ...core.models import LiveSample
from ...core.ringbuffer import RingBuffer
from ...sensors.mpu6050 import MpuSample

DEFAULT_REFRESH_MODE = "fixed"
DEFAULT_REFRESH_INTERVAL_MS = 250  # 4 Hz
MIN_REFRESH_INTERVAL_MS = 20  # Max 50 Hz

REFRESH_PRESETS: list[tuple[str, int]] = [
    ("4 Hz (250 ms) – Low CPU", 250),
    ("20 Hz (50 ms) – Medium", 50),
    ("50 Hz (20 ms) – High (CPU heavy)", 20),
]


class SignalPlotWidget(QWidget):
    """
    Matplotlib widget that shows a grid of time‑domain plots:

        - one row per sensor_id
        - one column per channel

    Example with 3 sensors and channels ax, ay, gz:
        3 rows x 3 columns = 9 subplots
    """

    def __init__(self, parent: Optional[QWidget] = None, max_seconds: float = 10.0):
        super().__init__(parent)

        self._max_seconds = float(max_seconds)
        self._max_rate_hz = 500.0
        # key = (sensor_id, channel)  -> RingBuffer[(t, value)]
        self._buffers: Dict[Tuple[int, str], RingBuffer[Tuple[float, float]]] = {}
        self._buffer_capacity = max(1, int(self._max_seconds * self._max_rate_hz))

        # Channels currently visible & their preferred order (columns)
        self._visible_channels: Set[str] = set()
        self._channel_order: list[str] = []

        # Appearance
        self._line_width: float = 0.8  # thinner than Matplotlib default

        # Optional base-correction (per sensor/channel)
        self._base_correction_enabled: bool = False
        self._baseline_offsets: Dict[Tuple[int, str], float] = {}

        self._figure = Figure(figsize=(6, 6), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)

        layout = QVBoxLayout(self)
        layout.addWidget(self._canvas)

    @property
    def window_seconds(self) -> float:
        """Length of the sliding time window shown in the plots."""
        return self._max_seconds

    @staticmethod
    def _channel_units(channel: str) -> str:
        """Return a human-readable unit for a channel name."""
        ch = channel.lower()
        if ch in {"ax", "ay", "az"}:
            return "m/s²"
        if ch in {"gx", "gy", "gz"}:
            return "deg/s"
        return ""

    # --------------------------------------------------------------- public API
    def clear(self) -> None:
        """Clear all buffered data and reset the plot."""
        self._buffers.clear()
        self._baseline_offsets.clear()
        self._figure.clear()
        self._canvas.draw_idle()

    def set_visible_channels(self, channels: Iterable[str]) -> None:
        """
        Select which channels should be rendered and in what column order.

        The *order* of the iterable defines the column order in the grid.
        """
        channels_list = list(channels)
        self._visible_channels = set(channels_list)
        self._channel_order = channels_list

    def add_sample(self, sample: LiveSample | MpuSample) -> None:
        """Append a sample from any supported sensor type."""
        if isinstance(sample, MpuSample):
            # Use sensor_id as row index; default to 1 if missing
            sensor_id = int(sample.sensor_id) if sample.sensor_id is not None else 1
            t = (
                float(sample.t_s)
                if sample.t_s is not None
                else sample.timestamp_ns * 1e-9
            )
            for ch in ("ax", "ay", "az", "gx", "gy", "gz"):
                val = getattr(sample, ch, None)
                if val is None:
                    continue
                try:
                    v = float(val)
                except (TypeError, ValueError):
                    continue
                if math.isnan(v):
                    continue
                self._append_point(sensor_id, ch, t, v)

        elif isinstance(sample, LiveSample):
            # Generic samples are treated as a single "sensor" row (id 0)
            sensor_id = 0
            t = sample.timestamp_ns * 1e-9
            for idx, val in enumerate(sample.values):
                try:
                    v = float(val)
                except (TypeError, ValueError):
                    continue
                if math.isnan(v):
                    continue
                ch = f"ch{idx}"
                self._append_point(sensor_id, ch, t, v)

    def redraw(self) -> None:
        """Refresh the Matplotlib plot (intended to be driven by a QTimer)."""
        # Determine which channels are visible (columns)
        visible_channels = [
            ch for ch in self._channel_order if ch in self._visible_channels
        ]
        if not visible_channels:
            self._figure.clear()
            self._canvas.draw_idle()
            return

        # Active buffers that actually have data
        active_buffers = [
            buf
            for (sid, ch), buf in self._buffers.items()
            if ch in visible_channels and len(buf) > 0
        ]
        if not active_buffers:
            self._figure.clear()
            self._canvas.draw_idle()
            return

        # Time window: last max_seconds across all sensors/channels.
        # Clamp to 0 so a fresh stream starts at t = 0 on the x-axis.
        latest = max(buf[-1][0] for buf in active_buffers)
        cutoff = max(0.0, latest - self._max_seconds)

        # Sensor rows
        sensor_ids = sorted(
            {
                sid
                for (sid, ch) in self._buffers.keys()
                if ch in visible_channels
            }
        )
        if not sensor_ids:
            self._figure.clear()
            self._canvas.draw_idle()
            return

        nrows = len(sensor_ids)
        ncols = len(visible_channels)

        self._figure.clear()

        for row_idx, sid in enumerate(sensor_ids):
            for col_idx, ch in enumerate(visible_channels):
                subplot_index = row_idx * ncols + col_idx + 1
                ax = self._figure.add_subplot(nrows, ncols, subplot_index)

                buf = self._buffers.get((sid, ch))
                if buf is None or len(buf) == 0:
                    ax.set_visible(False)
                    continue

                points = [(t, v) for (t, v) in buf if t >= cutoff]
                if not points:
                    ax.set_visible(False)
                    continue

                times = [t - cutoff for (t, v) in points]
                raw_values = [v for (_t, v) in points]

                offset = 0.0
                if self._base_correction_enabled:
                    offset = self._baseline_offsets.get((sid, ch), 0.0)
                values = [v - offset for v in raw_values]

                ax.plot(times, values, linewidth=self._line_width)

                # X label only on the bottom row
                if row_idx == nrows - 1:
                    ax.set_xlabel("Time (s)")

                unit = self._channel_units(ch)
                base_label = ch.upper()
                if unit:
                    base_label = f"{base_label} [{unit}]"

                # Leftmost column shows sensor row + channel
                if col_idx == 0:
                    if sid == 0:
                        prefix = "Live"
                    else:
                        prefix = f"S{sid}"
                    ax.set_ylabel(f"{prefix}\n{base_label}")
                else:
                    ax.set_ylabel(base_label)

                ax.grid(True)

        self._figure.tight_layout()
        self._canvas.draw_idle()

    # --------------------------------------------------------------- base correction API
    def enable_base_correction(self, enabled: bool) -> None:
        """Enable or disable baseline subtraction."""
        self._base_correction_enabled = bool(enabled)

    def reset_calibration(self) -> None:
        """Clear all stored baseline offsets."""
        self._baseline_offsets.clear()

    def calibrate_from_buffer(self) -> None:
        """
        Compute per-channel baseline from the most recent time window.

        For each (sensor_id, channel) we take the mean over the same sliding
        window that is used for plotting (self._max_seconds).
        """
        if not self._buffers:
            return

        latest_times = [buf[-1][0] for buf in self._buffers.values() if len(buf) > 0]
        if not latest_times:
            return

        latest = max(latest_times)
        cutoff = max(0.0, latest - self._max_seconds)

        new_offsets: Dict[Tuple[int, str], float] = {}
        for key, buf in self._buffers.items():
            if not buf:
                continue
            values = [v for (t, v) in buf if t >= cutoff]
            if not values:
                continue
            new_offsets[key] = sum(values) / float(len(values))

        self._baseline_offsets = new_offsets

    # --------------------------------------------------------------- internals
    def _append_point(self, sensor_id: int, channel: str, t: float, value: float) -> None:
        key = (sensor_id, channel)
        buf = self._buffers.get(key)
        if buf is None:
            buf = RingBuffer(self._buffer_capacity)
            self._buffers[key] = buf
        buf.append((t, value))


class SignalsTab(QWidget):
    """
    Tab that embeds a :class:`SignalPlotWidget` and exposes a small
    configuration UI for selecting sensor type and channels.

    Layout: one row per sensor, one column per selected channel.
    """

    start_stream_requested = Signal(bool)  # bool = recording mode
    stop_stream_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Refresh configuration
        self.refresh_mode: str = DEFAULT_REFRESH_MODE
        self.refresh_interval_ms: int = DEFAULT_REFRESH_INTERVAL_MS
        self._sampling_rate_hz: Optional[float] = None
        self._load_refresh_settings()

        self._plot = SignalPlotWidget(max_seconds=10.0)
        self._channel_checkboxes: Dict[str, QCheckBox] = {}
        self._controls_section: CollapsibleSection | None = None

        layout = QVBoxLayout(self)

        # Top controls ---------------------------------------------------------
        top_row_group = QGroupBox("Streaming / recording controls", self)
        top_row = QHBoxLayout(top_row_group)

        self.sensor_combo = QComboBox(top_row_group)
        self.sensor_combo.addItem("MPU6050", userData="mpu6050")
        self.sensor_combo.addItem("Generic live", userData="generic")
        top_row.addWidget(self.sensor_combo)

        # View preset selector (9 vs 18 charts)
        top_row.addWidget(QLabel("View:", top_row_group))
        self.view_mode_combo = QComboBox(top_row_group)
        self.view_mode_combo.addItem(
            "AX / AY / GZ (9 charts)", userData="default3"
        )
        self.view_mode_combo.addItem(
            "All axes (18 charts)", userData="all6"
        )
        top_row.addWidget(self.view_mode_combo)

        self.sensor_combo.currentIndexChanged.connect(
            self._rebuild_channel_checkboxes
        )
        self.view_mode_combo.currentIndexChanged.connect(
            self._on_view_mode_changed
        )

        self.recording_check = QCheckBox("Recording", top_row_group)
        self.recording_check.setToolTip(
            "Default is live streaming only. Tick this to also record every "
            "sample on the Pi at the configured rate."
        )

        # Base correction controls
        self.base_correction_check = QCheckBox("Base correction", top_row_group)
        self.calibrate_button = QPushButton("Calibrate", top_row_group)

        # Start/stop
        self.start_button = QPushButton("Start", top_row_group)
        self.stop_button = QPushButton("Stop", top_row_group)
        self.stop_button.setEnabled(False)

        # Small info labels: stream rate + calibration window length
        self._stream_rate_label = QLabel("Stream rate: -- Hz", top_row_group)
        self._stream_rate_label.setToolTip(
            "Estimated rate at which samples arrive in this GUI tab."
        )
        self._base_window_label = QLabel("", top_row_group)

        self.start_button.clicked.connect(self._on_start_clicked)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.base_correction_check.stateChanged.connect(
            self._on_base_correction_toggled
        )
        self.calibrate_button.clicked.connect(self._on_calibrate_clicked)

        top_row.addWidget(self.recording_check)
        top_row.addWidget(self.base_correction_check)
        top_row.addWidget(self.calibrate_button)
        top_row.addWidget(self.start_button)
        top_row.addWidget(self.stop_button)
        top_row.addWidget(self._stream_rate_label)
        top_row.addWidget(self._base_window_label)
        top_row.addStretch()

        group_layout = QVBoxLayout(top_row_group)
        group_layout.addLayout(top_row)

        # Short explanatory text under the buttons
        self._mode_hint_label = QLabel(
            "Default: live streaming only. Tick 'Recording' to also save data on the Pi.",
            top_row_group,
        )
        self._mode_hint_label.setWordWrap(True)
        group_layout.addWidget(self._mode_hint_label)

        top_row_group.setLayout(group_layout)

        self._update_base_window_label()

        # Channel selection -----------------------------------------------------
        channel_group = QGroupBox("Channels", self)
        self._channel_layout = QHBoxLayout(channel_group)
        channel_group.setLayout(self._channel_layout)

        # Refresh settings -----------------------------------------------------
        refresh_group = self._build_refresh_controls()

        controls_section = CollapsibleSection(
            "Controls / channels / refresh", self
        )
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(top_row_group)
        controls_layout.addWidget(channel_group)
        controls_layout.addWidget(refresh_group)
        controls_section.setContentLayout(controls_layout)
        layout.addWidget(controls_section)
        self._controls_section = controls_section

        # Plot widget -----------------------------------------------------------
        layout.addWidget(self._plot, stretch=1)

        # Status label ----------------------------------------------------------
        self._status_label = QLabel("Waiting for stream...", self)
        layout.addWidget(self._status_label)

        self._rebuild_channel_checkboxes()

        # periodic redraw of the plot
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._plot.redraw)
        self._apply_refresh_settings()

    # --------------------------------------------------------------- slots
    @Slot()
    def _on_start_clicked(self) -> None:
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._status_label.setText("Streaming...")
        self.start_stream_requested.emit(self.recording_check.isChecked())
        if self._controls_section is not None:
            self._controls_section.setCollapsed(True)

    @Slot()
    def _on_stop_clicked(self) -> None:
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._status_label.setText("Stopping...")
        self.stop_stream_requested.emit()
        if self._controls_section is not None:
            self._controls_section.setCollapsed(False)

    @Slot(object)
    def handle_sample(self, sample: object) -> None:
        """Called by RecorderTab when a new sample arrives."""
        sensor_key = self.sensor_combo.currentData()
        if sensor_key == "mpu6050":
            if not isinstance(sample, MpuSample):
                return
        elif sensor_key == "generic":
            if not isinstance(sample, LiveSample):
                return
        else:
            return

        self._plot.add_sample(sample)  # type: ignore[arg-type]

    # --------------------------------------------------------------- helpers
    def _update_base_window_label(self) -> None:
        seconds = self._plot.window_seconds
        self._base_window_label.setText(f"Base/cali window: last {seconds:.1f} s")

    @Slot(str, float)
    def update_stream_rate(self, sensor_type: str, hz: float) -> None:
        """Update the small stream-rate label from RecorderTab."""
        if sensor_type != "mpu6050":
            return
        self._stream_rate_label.setText(f"Stream rate: {hz:.1f} Hz")
        self._sampling_rate_hz = hz
        if self.refresh_mode == "follow_sampling_rate":
            self._apply_refresh_settings()

    def _rebuild_channel_checkboxes(self) -> None:
        # Clear previous
        while self._channel_layout.count():
            item = self._channel_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        self._channel_checkboxes.clear()

        sensor_key = self.sensor_combo.currentData()
        if sensor_key == "mpu6050":
            # Use view preset:
            #   - "default3" => AX, AY, GZ (3 columns)
            #   - "all6"     => AX, AY, AZ, GX, GY, GZ (6 columns)
            view_mode = (
                self.view_mode_combo.currentData()
                if hasattr(self, "view_mode_combo")
                else "all6"
            )
            if view_mode == "default3":
                channels = ["ax", "ay", "gz"]
            else:
                channels = ["ax", "ay", "az", "gx", "gy", "gz"]
        else:
            # Generic LiveSample channels (first few indices)
            channels = [f"ch{i}" for i in range(8)]

        for ch in channels:
            cb = QCheckBox(ch)
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_channel_toggles_changed)
            self._channel_checkboxes[ch] = cb
            self._channel_layout.addWidget(cb)

        self._channel_layout.addStretch(1)
        self._on_channel_toggles_changed()

    @Slot()
    def _on_view_mode_changed(self) -> None:
        """Called when the view preset combo changes."""
        self._rebuild_channel_checkboxes()

    @Slot()
    def _on_channel_toggles_changed(self) -> None:
        # Preserve the checkbox order as the column order
        visible = [
            ch for ch, cb in self._channel_checkboxes.items() if cb.isChecked()
        ]
        self._plot.set_visible_channels(visible)

    def _build_refresh_controls(self) -> QGroupBox:
        group = QGroupBox("Plot refresh rate", self)
        form = QFormLayout(group)

        self.refresh_mode_combo = QComboBox(group)
        self.refresh_mode_combo.addItem("Fixed refresh rate", "fixed")
        self.refresh_mode_combo.addItem(
            "Follow sampling rate (advanced / may be heavy)",
            "follow_sampling_rate",
        )
        idx = self.refresh_mode_combo.findData(self.refresh_mode)
        if idx >= 0:
            self.refresh_mode_combo.setCurrentIndex(idx)
        self.refresh_mode_combo.currentIndexChanged.connect(
            self._on_refresh_mode_changed
        )

        self.fixed_interval_combo = QComboBox(group)
        for label, interval in REFRESH_PRESETS:
            self.fixed_interval_combo.addItem(label, interval)
        self._select_fixed_interval(self.refresh_interval_ms)
        self.fixed_interval_combo.currentIndexChanged.connect(
            self._on_fixed_interval_changed
        )

        help_label = QLabel(
            "High refresh rates and 'Follow sampling rate' may be heavy on CPU, "
            "especially with many channels.",
            group,
        )
        help_label.setWordWrap(True)
        help_label.setToolTip(
            "Use 'Low CPU' unless you specifically need fast visual updates."
        )

        form.addRow("Mode:", self.refresh_mode_combo)
        form.addRow("Fixed rate:", self.fixed_interval_combo)
        form.addRow(help_label)

        self.fixed_interval_combo.setEnabled(self.refresh_mode == "fixed")

        group.setLayout(form)
        return group

    def _select_fixed_interval(self, interval_ms: int) -> None:
        for i in range(self.fixed_interval_combo.count()):
            if self.fixed_interval_combo.itemData(i) == interval_ms:
                self.fixed_interval_combo.setCurrentIndex(i)
                return

    def _on_refresh_mode_changed(self, index: int) -> None:
        self.refresh_mode = self.refresh_mode_combo.currentData()
        self.fixed_interval_combo.setEnabled(self.refresh_mode == "fixed")
        self._apply_refresh_settings()
        self._save_refresh_settings()

    def _on_fixed_interval_changed(self, index: int) -> None:
        value = self.fixed_interval_combo.itemData(index)
        if value is None:
            return
        self.refresh_interval_ms = int(value)
        if self.refresh_mode == "fixed":
            self._apply_refresh_settings()
        self._save_refresh_settings()

    def _get_sampling_rate_hz(self) -> Optional[float]:
        if self._sampling_rate_hz is not None:
            return self._sampling_rate_hz
        return None

    def _compute_refresh_interval(self) -> int:
        if self.refresh_mode == "follow_sampling_rate":
            rate_hz = self._get_sampling_rate_hz()
            if not rate_hz or rate_hz <= 0:
                return DEFAULT_REFRESH_INTERVAL_MS

            interval_ms = int(1000.0 / rate_hz)
            if interval_ms < MIN_REFRESH_INTERVAL_MS:
                interval_ms = MIN_REFRESH_INTERVAL_MS
            return interval_ms

        return int(self.refresh_interval_ms)

    def _apply_refresh_settings(self) -> None:
        interval_ms = self._compute_refresh_interval()
        if hasattr(self, "_timer"):
            self._timer.start(interval_ms)

    def _load_refresh_settings(self) -> None:
        settings = QSettings("SensePi", "SensePiLocal")
        mode = str(settings.value("signals/refresh_mode", DEFAULT_REFRESH_MODE))
        if mode not in {"fixed", "follow_sampling_rate"}:
            mode = DEFAULT_REFRESH_MODE
        self.refresh_mode = mode

        interval_value = settings.value(
            "signals/refresh_interval_ms", DEFAULT_REFRESH_INTERVAL_MS
        )
        try:
            interval_ms = int(interval_value)
        except (TypeError, ValueError):
            interval_ms = DEFAULT_REFRESH_INTERVAL_MS
        self.refresh_interval_ms = interval_ms

    def _save_refresh_settings(self) -> None:
        settings = QSettings("SensePi", "SensePiLocal")
        settings.setValue("signals/refresh_mode", self.refresh_mode)
        settings.setValue("signals/refresh_interval_ms", self.refresh_interval_ms)

    @Slot()
    def on_stream_started(self) -> None:
        self._status_label.setText("Streaming...")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    @Slot()
    def on_stream_stopped(self) -> None:
        self._status_label.setText("Stopped.")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._plot.clear()

    @Slot(str)
    def handle_error(self, message: str) -> None:
        self._status_label.setText(message)

    @Slot(int)
    def _on_base_correction_toggled(self, state: int) -> None:
        enabled = state == Qt.Checked
        self._plot.enable_base_correction(enabled)
        if enabled:
            self._status_label.setText("Base correction enabled.")
        else:
            self._status_label.setText("Base correction disabled.")

    @Slot()
    def _on_calibrate_clicked(self) -> None:
        self._plot.calibrate_from_buffer()
        if self.base_correction_check.isChecked():
            self._status_label.setText(
                "Calibration updated (base correction applied)."
            )
        else:
            self._status_label.setText(
                "Calibration stored (enable 'Base correction' to apply)."
            )

    def attach_recorder_controls(self, recorder_tab: "RecorderTab") -> None:
        """
        Embed the RecorderTab's connection/settings widgets at the top of this tab
        so users can manage the Pi directly from here.

        The RecorderTab itself can stay hidden; we just reuse its widgets.
        """
        # Local import to avoid circular dependency
        from .tab_recorder import RecorderTab as _RecorderTab  # type: ignore

        if not isinstance(recorder_tab, _RecorderTab):
            return

        host_group = getattr(recorder_tab, "host_group", None)
        mpu_group = getattr(recorder_tab, "mpu_group", None)
        if host_group is None or mpu_group is None:
            return

        parent_layout = recorder_tab.layout()
        if parent_layout is not None:
            parent_layout.removeWidget(host_group)
            parent_layout.removeWidget(mpu_group)

        host_group.setParent(self)
        mpu_group.setParent(self)

        layout = self.layout()
        if layout is not None:
            # Insert above the streaming controls group (which is currently at index 0)
            layout.insertWidget(0, host_group)
            layout.insertWidget(1, mpu_group)
