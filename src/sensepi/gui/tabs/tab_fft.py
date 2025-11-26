"""Live FFT / spectrum tab.

Supports MPU6050 samples and generic LiveSample data.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

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

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ...analysis.fft import compute_fft
from ...analysis import filters
from ...core.models import LiveSample
from ...core.ringbuffer import RingBuffer
from ...sensors.mpu6050 import MpuSample


class FftTab(QWidget):
    """
    Tab that computes a frequency spectrum over a sliding window of
    recent samples from the live stream.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._buffers: Dict[Tuple[str, int, str], RingBuffer[Tuple[float, float]]] = {}
        self._max_window_seconds = 10.0  # longest supported FFT window
        self._max_rate_hz = 500.0
        self._buffer_capacity = max(1, int(self._max_window_seconds * self._max_rate_hz * 2))

        # Figure / canvas -------------------------------------------------------
        self._figure = Figure(figsize=(5, 3), tight_layout=True)
        self._axes = self._figure.add_subplot(111)
        self._canvas = FigureCanvasQTAgg(self._figure)

        # Controls --------------------------------------------------------------
        controls_group = QGroupBox("FFT settings")
        form = QFormLayout(controls_group)

        # Sensor + view selection
        top_row = QHBoxLayout()
        self.sensor_combo = QComboBox()
        self.sensor_combo.addItem("MPU6050", userData="mpu6050")
        self.sensor_combo.addItem("Generic live", userData="generic")

        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItem(
            "AX / AY / GZ (9 charts)", userData="default3"
        )
        self.view_mode_combo.addItem(
            "All axes (18 charts)", userData="all6"
        )

        top_row.addWidget(QLabel("Sensor:"))
        top_row.addWidget(self.sensor_combo)
        top_row.addWidget(QLabel("View:"))
        top_row.addWidget(self.view_mode_combo)
        top_row.addStretch()
        form.addRow(top_row)

        # FFT window length (seconds)
        self.window_spin = QDoubleSpinBox()
        self.window_spin.setRange(0.5, 10.0)
        self.window_spin.setSingleStep(0.5)
        self.window_spin.setValue(2.0)
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

        # Status label
        self._status_label = QLabel("Waiting for data...")

        # Layout ---------------------------------------------------------------
        layout = QVBoxLayout(self)
        layout.addWidget(controls_group)
        layout.addWidget(self._canvas)
        layout.addWidget(self._status_label)

        # Timer to recompute FFT periodically
        self._timer = QTimer(self)
        self._timer.setInterval(750)  # ms
        self._timer.timeout.connect(self._update_fft)
        self._timer.start()

        # Wiring
        self.sensor_combo.currentIndexChanged.connect(self._on_sensor_changed)
        self.view_mode_combo.currentIndexChanged.connect(self._on_sensor_changed)
        self._on_sensor_changed()

    # --------------------------------------------------------------- API from RecorderTab
    @Slot(object)
    def handle_sample(self, sample: object) -> None:
        """Called by RecorderTab when a new sample arrives."""
        if isinstance(sample, MpuSample):
            sensor_key = "mpu6050"
            sensor_id = sample.sensor_id if sample.sensor_id is not None else 1
            try:
                sensor_id_int = int(sensor_id)
            except (TypeError, ValueError):
                sensor_id_int = 1

            t = (
                float(sample.t_s)
                if sample.t_s is not None
                else sample.timestamp_ns * 1e-9
            )
            for ch in ("ax", "ay", "az", "gx", "gy", "gz"):
                val = getattr(sample, ch, None)
                if val is not None:
                    self._append_point(sensor_key, sensor_id_int, ch, t, float(val))

        elif isinstance(sample, LiveSample):
            sensor_key = "generic"
            sensor_id_int = 0
            t = sample.timestamp_ns * 1e-9
            for idx, val in enumerate(sample.values):
                self._append_point(
                    sensor_key, sensor_id_int, f"ch{idx}", t, float(val)
                )

    @Slot()
    def on_stream_started(self) -> None:
        self._buffers.clear()
        self._status_label.setText("Streaming...")

    @Slot()
    def on_stream_stopped(self) -> None:
        # Keep last spectrum visible but update status.
        self._status_label.setText("Stream stopped.")

    # --------------------------------------------------------------- internals
    def _on_sensor_changed(self) -> None:
        """
        Enable/disable view presets based on the selected sensor type.
        For generic data we fall back to a single FFT plot.
        """
        sensor_key = self.sensor_combo.currentData()
        # Only MPU6050 supports 9/18 chart grid; keep the selector disabled otherwise.
        self.view_mode_combo.setEnabled(sensor_key == "mpu6050")

    @staticmethod
    def _channel_units(channel: str) -> str:
        ch = channel.lower()
        if ch in {"ax", "ay", "az"}:
            return "m/s²"
        if ch in {"gx", "gy", "gz"}:
            return "deg/s"
        return ""

    def _append_point(
        self, sensor_key: str, sensor_id: int, channel: str, t: float, value: float
    ) -> None:
        key = (sensor_key, sensor_id, channel)
        buf = self._buffers.get(key)
        if buf is None:
            buf = RingBuffer(self._buffer_capacity)
            self._buffers[key] = buf

        buf.append((t, value))

    def _update_fft(self) -> None:
        sensor_key = self.sensor_combo.currentData()
        if sensor_key == "mpu6050":
            self._update_mpu6050_fft()
        else:
            self._update_generic_fft()

    def _update_mpu6050_fft(self) -> None:
        # Determine which channels we want in the grid
        view_mode = self.view_mode_combo.currentData()
        if view_mode == "default3":
            channels = ["ax", "ay", "gz"]
        else:
            channels = ["ax", "ay", "az", "gx", "gy", "gz"]

        # Collect sensor_ids that have any data for these channels
        keys = [
            key
            for key in self._buffers.keys()
            if key[0] == "mpu6050" and key[2] in channels and len(self._buffers[key]) > 0
        ]
        sensor_ids = sorted({sensor_id for (_sensor, sensor_id, _ch) in keys})
        if not sensor_ids:
            self._draw_waiting()
            return

        window_s = float(self.window_spin.value())

        self._figure.clear()

        nrows = len(sensor_ids)
        ncols = len(channels)

        # Stats for status label (take from first populated subplot)
        stats_samples = None
        stats_fs = None

        subplot_index = 1
        for row_idx, sensor_id in enumerate(sensor_ids):
            for col_idx, ch in enumerate(channels):
                buf = self._buffers.get(("mpu6050", sensor_id, ch))
                ax = self._figure.add_subplot(nrows, ncols, subplot_index)
                subplot_index += 1

                if buf is None or len(buf) < 4:
                    ax.set_visible(False)
                    continue

                points = list(buf)
                t_latest = points[-1][0]
                t_min = t_latest - window_s

                times = [t for (t, _v) in points if t >= t_min]
                values = [v for (t, v) in points if t >= t_min]

                if len(values) < 4 or times[-1] == times[0]:
                    ax.set_visible(False)
                    continue

                times_arr = np.asarray(times, dtype=float)
                values_arr = np.asarray(values, dtype=float)

                dt = times_arr[-1] - times_arr[0]
                sample_rate_hz = (len(times_arr) - 1) / dt if dt > 0 else 1.0

                signal = values_arr.copy()

                # Optional detrend / lowpass
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

                freqs, mag = compute_fft(signal, sample_rate_hz)
                if freqs.size == 0:
                    ax.set_visible(False)
                    continue

                ax.plot(freqs, mag)
                ax.set_xlim(0.0, freqs[-1])

                if row_idx == nrows - 1:
                    ax.set_xlabel("Frequency [Hz]")

                units = self._channel_units(ch)
                title = f"S{sensor_id} {ch.upper()}"
                if units:
                    title = f"{title} [{units}]"
                ax.set_title(title)
                if col_idx == 0:
                    ax.set_ylabel("Magnitude")

                ax.grid(True)

                if stats_samples is None:
                    stats_samples = len(values)
                    stats_fs = sample_rate_hz

        self._figure.tight_layout()
        self._canvas.draw_idle()

        if stats_samples is not None and stats_fs is not None:
            self._status_label.setText(
                f"Window: {window_s:.1f} s, samples: {stats_samples}, fs≈{stats_fs:.1f} Hz"
            )
        else:
            self._status_label.setText("Waiting for data...")

    def _update_generic_fft(self) -> None:
        # Pick the first available generic channel
        generic_keys = [
            key
            for key in self._buffers.keys()
            if key[0] == "generic" and len(self._buffers[key]) >= 4
        ]
        if not generic_keys:
            self._draw_waiting()
            return

        sensor_key, sensor_id, channel = generic_keys[0]
        buf = self._buffers[generic_keys[0]]

        window_s = float(self.window_spin.value())
        points = list(buf)
        t_latest = points[-1][0]
        t_min = t_latest - window_s

        times = [t for (t, _v) in points if t >= t_min]
        values = [v for (t, v) in points if t >= t_min]

        if len(values) < 4 or times[-1] == times[0]:
            self._draw_waiting()
            return

        times_arr = np.asarray(times, dtype=float)
        values_arr = np.asarray(values, dtype=float)

        dt = times_arr[-1] - times_arr[0]
        sample_rate_hz = (len(times_arr) - 1) / dt if dt > 0 else 1.0

        signal = values_arr.copy()

        if self.detrend_check.isChecked():
            signal = filters.detrend(signal)

        if self.lowpass_check.isChecked():
            cutoff = float(self.lowpass_cutoff.value())
            nyquist = 0.5 * sample_rate_hz
            if 0.0 < cutoff < nyquist:
                signal = filters.butter_lowpass(
                    signal, cutoff_hz=cutoff, sample_rate_hz=sample_rate_hz
                )

        freqs, mag = compute_fft(signal, sample_rate_hz)

        self._figure.clear()
        self._axes = self._figure.add_subplot(111)
        if freqs.size > 0:
            self._axes.plot(freqs, mag)
            self._axes.set_xlim(0.0, freqs[-1])
        self._axes.set_xlabel("Frequency [Hz]")
        self._axes.set_ylabel("Magnitude")
        self._axes.set_title(f"generic / {channel}")
        self._figure.tight_layout()
        self._canvas.draw_idle()

        self._status_label.setText(
            f"Window: {window_s:.1f} s, samples: {len(values)}, fs≈{sample_rate_hz:.1f} Hz"
        )

    def _draw_waiting(self) -> None:
        self._figure.clear()
        self._axes = self._figure.add_subplot(111)
        self._axes.set_xlabel("Frequency [Hz]")
        self._axes.set_ylabel("Magnitude")
        self._axes.set_title("Waiting for data...")
        self._canvas.draw_idle()
        self._status_label.setText("Waiting for data...")
