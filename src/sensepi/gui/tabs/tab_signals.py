from __future__ import annotations

from typing import Dict, Iterable, Optional

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
        self._buffers: Dict[str, RingBuffer[tuple[float, float]]] = {}
        self._visible_channels: set[str] = set()
        self._buffer_capacity = max(1, int(self._max_seconds * self._max_rate_hz))

        self._figure = Figure(figsize=(5, 6), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)

        layout = QVBoxLayout(self)
        layout.addWidget(self._canvas)

    # --------------------------------------------------------------- public API
    def clear(self) -> None:
        """Clear all buffered data and reset the plot."""
        self._buffers.clear()
        self._figure.clear()
        self._canvas.draw_idle()

    def set_visible_channels(self, channels: Iterable[str]) -> None:
        """Select which channels should be rendered."""
        self._visible_channels = set(channels)

    def add_sample(self, sample: LiveSample | MpuSample) -> None:
        """Append a sample from any supported sensor type."""
        if isinstance(sample, MpuSample):
            t = (
                float(sample.t_s)
                if sample.t_s is not None
                else sample.timestamp_ns * 1e-9
            )
            for ch in ("ax", "ay", "az", "gx", "gy", "gz"):
                val = getattr(sample, ch, None)
                if val is not None:
                    self._append_point(ch, t, float(val))

        elif isinstance(sample, LiveSample):
            t = sample.timestamp_ns * 1e-9
            for idx, val in enumerate(sample.values):
                self._append_point(f"ch{idx}", t, float(val))

    def redraw(self) -> None:
        """Refresh the Matplotlib plot (intended to be driven by a QTimer)."""
        visible = [
            ch
            for ch in self._visible_channels
            if ch in self._buffers and self._buffers[ch]
        ]
        if not visible:
            self._figure.clear()
            self._canvas.draw_idle()
            return

        latest = max(self._buffers[ch][-1][0] for ch in visible)
        cutoff = latest - self._max_seconds

        self._figure.clear()
        ax = self._figure.add_subplot(1, 1, 1)

        for ch in visible:
            buf = self._buffers[ch]
            points = [(t, v) for (t, v) in buf if t >= cutoff]
            if not points:
                continue
            times = [t - cutoff for (t, _) in points]
            values = [v for (_, v) in points]
            ax.plot(times, values, label=ch.upper())

        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Value")
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
        self._channel_checkboxes: Dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)

        # Top controls ---------------------------------------------------------
        top_row_group = QGroupBox("Streaming controls", self)
        top_row = QHBoxLayout(top_row_group)

        self.sensor_combo = QComboBox(top_row_group)
        self.sensor_combo.addItem("MPU6050", userData="mpu6050")
        self.sensor_combo.addItem("Generic live", userData="generic")
        top_row.addWidget(self.sensor_combo)

        self.sensor_combo.currentIndexChanged.connect(
            self._rebuild_channel_checkboxes
        )

        self.recording_check = QCheckBox("Recording", top_row_group)
        self.recording_check.setToolTip(
            "Recording: logs every sample on the Pi at the selected rate, "
            "but only streams a subset of points to the GUI."
        )
        self.start_button = QPushButton("Start streaming", top_row_group)
        self.stop_button = QPushButton("Stop", top_row_group)
        self.stop_button.setEnabled(False)

        self.start_button.clicked.connect(self._on_start_clicked)
        self.stop_button.clicked.connect(self._on_stop_clicked)

        top_row.addWidget(self.recording_check)
        top_row.addWidget(self.start_button)
        top_row.addWidget(self.stop_button)
        top_row.addStretch()
        top_row_group.setLayout(top_row)
        layout.addWidget(top_row_group)

        # Channel selection -----------------------------------------------------
        channel_group = QGroupBox("Channels", self)
        self._channel_layout = QHBoxLayout(channel_group)
        channel_group.setLayout(self._channel_layout)
        layout.addWidget(channel_group)

        # Plot widget -----------------------------------------------------------
        layout.addWidget(self._plot)

        # Status label ----------------------------------------------------------
        self._status_label = QLabel("Waiting for stream...", self)
        layout.addWidget(self._status_label)

        self._rebuild_channel_checkboxes()

    # --------------------------------------------------------------- slots
    @Slot()
    def _on_start_clicked(self) -> None:
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._status_label.setText("Streaming...")
        self.start_stream_requested.emit(self.recording_check.isChecked())

    @Slot()
    def _on_stop_clicked(self) -> None:
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._status_label.setText("Stopping...")
        self.stop_stream_requested.emit()

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
    def _on_channel_toggles_changed(self) -> None:
        visible = [
            ch for ch, cb in self._channel_checkboxes.items() if cb.isChecked()
        ]
        self._plot.set_visible_channels(visible)

    def handle_stream_started(self) -> None:
        self._status_label.setText("Streaming...")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def handle_stream_stopped(self) -> None:
        self._status_label.setText("Stopped.")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._plot.clear()

    def handle_error(self, message: str) -> None:
        self._status_label.setText(message)
