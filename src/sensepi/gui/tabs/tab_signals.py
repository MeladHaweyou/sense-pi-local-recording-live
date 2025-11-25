"""Live signal view tab."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set, Tuple

from PySide6.QtCore import QTimer, Slot, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ...core.models import LiveSample
from ...core.ringbuffer import RingBuffer
from ...sensors.adxl203_ads1115 import AdxlSample
from ...sensors.mpu6050 import MpuSample


class SignalPlotWidget(QWidget):
    """
    Thin wrapper around a Matplotlib FigureCanvas that manages
    fixed-length time-domain buffers for one or more channels.
    """

    def __init__(self, parent: Optional[QWidget] = None, max_seconds: float = 10.0):
        super().__init__(parent)

        self._max_seconds = float(max_seconds)
        self._max_rate_hz = 500.0
        self._buffers: Dict[str, RingBuffer[Tuple[float, float]]] = {}
        self._visible_channels: Set[str] = set()
        self._lines: Dict[str, any] = {}
        self._axes: Dict[str, any] = {}

        self._buffer_capacity = max(1, int(self._max_seconds * self._max_rate_hz))

        self._figure = Figure(figsize=(5, 6), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)

        layout = QVBoxLayout(self)
        layout.addWidget(self._canvas)

    # --------------------------------------------------------------- public API
    def clear(self) -> None:
        """Clear all buffered data and reset the plot."""
        self._buffers.clear()
        self._lines.clear()
        self._axes.clear()
        self._figure.clear()
        self._canvas.draw_idle()

    def set_visible_channels(self, channels: Iterable[str]) -> None:
        """Select which channels should be rendered."""
        self._visible_channels = set(channels)

    def add_sample(self, sample: LiveSample | MpuSample | AdxlSample) -> None:
        """Append a sample from any supported sensor type."""
        if isinstance(sample, MpuSample):
            sid = getattr(sample, "sensor_id", 1) or 1
            t = (
                float(sample.t_s)
                if sample.t_s is not None
                else sample.timestamp_ns * 1e-9
            )

            for ch_key in ("ax", "ay", "gz"):
                val = getattr(sample, ch_key, None)
                if val is not None:
                    key = f"mpu{sid}_{ch_key}"
                    self._append_point(key, t, float(val))

        elif isinstance(sample, AdxlSample):
            t = sample.timestamp_ns * 1e-9
            if sample.x is not None:
                self._append_point("adxl_x", t, float(sample.x))
            if sample.y is not None:
                self._append_point("adxl_y", t, float(sample.y))

        elif isinstance(sample, LiveSample):
            t = sample.timestamp_ns * 1e-9
            for idx, val in enumerate(sample.values):
                self._append_point(f"ch{idx}", t, float(val))

        # Unknown sample types are silently ignored.

    def redraw(self) -> None:
        """Refresh the Matplotlib plot (intended to be driven by a QTimer)."""
        visible = [
            ch
            for ch in self._visible_channels
            if ch in self._buffers and self._buffers[ch]
        ]
        if not visible:
            self._figure.clear()
            self._axes.clear()
            self._canvas.draw_idle()
            return

        has_mpu = any(ch.startswith("mpu") for ch in visible)
        has_adxl = any(ch.startswith("adxl") for ch in visible)

        rows = 0
        mpu_sids = sorted({int(ch[3]) for ch in visible if ch.startswith("mpu")})
        rows += len(mpu_sids)
        if has_adxl:
            rows += 1

        self._figure.clear()
        self._axes.clear()

        row_index = 1

        for sid in mpu_sids:
            ax = self._figure.add_subplot(rows, 1, row_index)
            key = f"mpu{sid}"
            self._axes[key] = ax
            row_index += 1

            sensor_channels = [ch for ch in visible if ch.startswith(f"mpu{sid}_")]
            if not sensor_channels:
                continue

            latest = max(self._buffers[ch][-1][0] for ch in sensor_channels)
            cutoff = latest - self._max_seconds

            for ch in sensor_channels:
                buf = self._buffers[ch]
                points = [(t, v) for (t, v) in buf if t >= cutoff]
                if not points:
                    continue
                times = [t - cutoff for (t, _) in points]
                values = [v for (_, v) in points]
                label = ch.split("_", 1)[1].upper()
                ax.plot(times, values, label=label)

            ax.set_ylabel("MPU m/s² / deg/s")
            ax.set_title(f"MPU sensor {sid}")
            ax.legend(loc="upper right")

        if has_adxl:
            ax = self._figure.add_subplot(rows, 1, row_index)
            self._axes["adxl"] = ax

            adxl_channels = [ch for ch in visible if ch.startswith("adxl_")]
            latest = max(self._buffers[ch][-1][0] for ch in adxl_channels)
            cutoff = latest - self._max_seconds

            for ch in adxl_channels:
                buf = self._buffers[ch]
                points = [(t, v) for (t, v) in buf if t >= cutoff]
                if not points:
                    continue
                times = [t - cutoff for (t, _) in points]
                values = [v for (_, v) in points]
                label = ch.split("_", 1)[1].upper()
                ax.plot(times, values, label=label)

            ax.set_xlabel("Time (s)")
            ax.set_ylabel("ADXL (V or g)")
            ax.set_title("ADXL203/ADS1115")
            ax.legend(loc="upper right")

        self._canvas.draw_idle()

    # --------------------------------------------------------------- internals
    def _append_point(self, channel: str, t: float, value: float) -> None:
        buf = self._buffers.get(channel)
        if buf is None:
            buf = RingBuffer(self._buffer_capacity)
            self._buffers[channel] = buf

        buf.append((t, value))


class SignalsTab(QWidget):
    """
    Tab that embeds a :class:`SignalPlotWidget` and exposes a small
    configuration UI for selecting sensor type and channels.
    """

    start_stream_requested = Signal(bool)  # bool = recording mode
    stop_stream_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._plot = SignalPlotWidget(max_seconds=10.0)
        self._mpu_chks: Dict[str, QCheckBox] = {}
        self._adxl_chks: Dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)

        # Top controls ---------------------------------------------------------
        top_row = QHBoxLayout()
        self.recording_check = QCheckBox("Recording")
        self.recording_check.setToolTip(
            "Recording: logs every sample on the Pi at the selected rate, "
            "but only streams a subset of points to the GUI."
        )
        self.start_button = QPushButton("Start streaming")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)

        self.start_button.clicked.connect(self._on_start_clicked)
        self.stop_button.clicked.connect(self._on_stop_clicked)

        top_row.addWidget(self.recording_check)
        top_row.addWidget(self.start_button)
        top_row.addWidget(self.stop_button)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Channel selection -----------------------------------------------------
        self._mpu_channel_group = QGroupBox("MPU6050 channels (per sensor)")
        mpu_ch_layout = QHBoxLayout()
        self._mpu_channel_group.setLayout(mpu_ch_layout)

        for ch_label, ch_key in [("AX", "ax"), ("AY", "ay"), ("GZ", "gz")]:
            chk = QCheckBox(ch_label)
            chk.setChecked(True)
            chk.stateChanged.connect(self._on_channel_toggles_changed)
            self._mpu_chks[ch_key] = chk
            mpu_ch_layout.addWidget(chk)

        layout.addWidget(self._mpu_channel_group)

        self._adxl_channel_group = QGroupBox("ADXL203/ADS1115 channels")
        adxl_ch_layout = QHBoxLayout()
        self._adxl_channel_group.setLayout(adxl_ch_layout)

        for ch_label, ch_key in [("X", "x"), ("Y", "y")]:
            chk = QCheckBox(ch_label)
            chk.setChecked(True)
            chk.stateChanged.connect(self._on_channel_toggles_changed)
            self._adxl_chks[ch_key] = chk
            adxl_ch_layout.addWidget(chk)

        layout.addWidget(self._adxl_channel_group)

        # Plot widget -----------------------------------------------------------
        layout.addWidget(self._plot)

        # Status label ----------------------------------------------------------
        self._status_label = QLabel("Waiting for stream...")
        layout.addWidget(self._status_label)

        # Timer to refresh matplotlib at ~25 FPS
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(40)  # ms
        self._refresh_timer.timeout.connect(self._plot.redraw)
        self._refresh_timer.start()

        self._on_channel_toggles_changed()

    # --------------------------------------------------------------- API from RecorderTab
    @Slot(object)
    def handle_sample(self, sample: object) -> None:
        """Called by RecorderTab when a new sample arrives."""
        if not isinstance(sample, (MpuSample, AdxlSample, LiveSample)):
            return

        self._plot.add_sample(sample)  # type: ignore[arg-type]

    @Slot()
    def on_stream_started(self) -> None:
        self._plot.clear()
        self._status_label.setText("Streaming...")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    @Slot()
    def on_stream_stopped(self) -> None:
        # Keep the last trace visible but update status text.
        self._status_label.setText("Stream stopped.")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    # --------------------------------------------------------------- internals
    def _on_channel_toggles_changed(self) -> None:
        visible_channels: Set[str] = set()

        for sid in (1, 2, 3):
            for ch_key, chk in self._mpu_chks.items():
                if chk.isChecked():
                    visible_channels.add(f"mpu{sid}_{ch_key}")

        for ch_key, chk in self._adxl_chks.items():
            if chk.isChecked():
                visible_channels.add(f"adxl_{ch_key}")

        self._plot.set_visible_channels(visible_channels)

    def _on_start_clicked(self) -> None:
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.start_stream_requested.emit(self.recording_check.isChecked())

    def _on_stop_clicked(self) -> None:
        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.stop_stream_requested.emit()
