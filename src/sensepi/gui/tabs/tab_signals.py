"""Live signal view tab."""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple

from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ...core.models import LiveSample
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
        self._buffers: Dict[str, Deque[Tuple[float, float]]] = {}
        self._visible_channels: Set[str] = set()
        self._lines: Dict[str, any] = {}

        self._figure = Figure(figsize=(5, 3), tight_layout=True)
        self._axes = self._figure.add_subplot(111)
        self._canvas = FigureCanvasQTAgg(self._figure)

        layout = QVBoxLayout(self)
        layout.addWidget(self._canvas)

        self._axes.set_xlabel("Time (s)")
        self._axes.set_ylabel("Value")
        self._axes.set_title("Live signal")

    # --------------------------------------------------------------- public API
    def clear(self) -> None:
        """Clear all buffered data and reset the plot."""
        self._buffers.clear()
        self._lines.clear()
        self._axes.clear()
        self._axes.set_xlabel("Time (s)")
        self._axes.set_ylabel("Value")
        self._axes.set_title("Live signal")
        self._canvas.draw_idle()

    def set_visible_channels(self, channels: Iterable[str]) -> None:
        """Select which channels should be rendered."""
        self._visible_channels = set(channels)

    def add_sample(self, sample: LiveSample | MpuSample | AdxlSample) -> None:
        """Append a sample from any supported sensor type."""
        # Determine time axis (seconds)
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

        elif isinstance(sample, AdxlSample):
            t = sample.timestamp_ns * 1e-9
            if sample.x is not None:
                self._append_point("x", t, float(sample.x))
            if sample.y is not None:
                self._append_point("y", t, float(sample.y))

        elif isinstance(sample, LiveSample):
            t = sample.timestamp_ns * 1e-9
            for idx, val in enumerate(sample.values):
                self._append_point(f"ch{idx}", t, float(val))

        # Unknown sample types are silently ignored.

    def redraw(self) -> None:
        """Refresh the Matplotlib plot (intended to be driven by a QTimer)."""
        # Collect visible buffers
        active_channels = [
            ch
            for ch in self._visible_channels
            if ch in self._buffers and self._buffers[ch]
        ]
        if not active_channels:
            # Nothing to show
            self._axes.clear()
            self._axes.set_xlabel("Time (s)")
            self._axes.set_ylabel("Value")
            self._axes.set_title("Waiting for data...")
            self._canvas.draw_idle()
            return

        # Compute global time origin so plots share the same x-axis
        min_t = min(self._buffers[ch][0][0] for ch in active_channels)

        self._axes.clear()
        for ch in active_channels:
            buf = self._buffers[ch]
            times = [t - min_t for (t, _) in buf]
            values = [v for (_, v) in buf]
            (line,) = self._axes.plot(times, values, label=ch)
            self._lines[ch] = line

        self._axes.set_xlabel("Time (s)")
        self._axes.set_ylabel("Value")
        self._axes.legend(loc="upper right")
        self._canvas.draw_idle()

    # --------------------------------------------------------------- internals
    def _append_point(self, channel: str, t: float, value: float) -> None:
        buf = self._buffers.get(channel)
        if buf is None:
            buf = deque()
            self._buffers[channel] = buf

        buf.append((t, value))

        # Drop old points beyond the configured time window
        cutoff = t - self._max_seconds
        while buf and buf[0][0] < cutoff:
            buf.popleft()


class SignalsTab(QWidget):
    """
    Tab that embeds a :class:`SignalPlotWidget` and exposes a small
    configuration UI for selecting sensor type and channels.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._plot = SignalPlotWidget(max_seconds=10.0)
        self._channel_checkboxes: Dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)

        # Sensor selection ------------------------------------------------------
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Sensor:"))

        self.sensor_combo = QComboBox()
        self.sensor_combo.addItem("MPU6050", userData="mpu6050")
        self.sensor_combo.addItem("ADXL203/ADS1115", userData="adxl203_ads1115")
        top_row.addWidget(self.sensor_combo)
        top_row.addStretch()
        layout.addLayout(top_row)

        # Channel selection -----------------------------------------------------
        self._channel_group = QGroupBox("Channels")
        self._channel_layout = QHBoxLayout()
        self._channel_group.setLayout(self._channel_layout)
        layout.addWidget(self._channel_group)

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

        # Wiring ----------------------------------------------------------------
        self.sensor_combo.currentIndexChanged.connect(
            self._rebuild_channel_checkboxes
        )
        self._rebuild_channel_checkboxes()

    # --------------------------------------------------------------- API from RecorderTab
    @Slot(object)
    def handle_sample(self, sample: object) -> None:
        """Called by RecorderTab when a new sample arrives."""
        sensor_type = self.sensor_combo.currentData()
        if sensor_type == "mpu6050" and not isinstance(sample, MpuSample):
            return
        if sensor_type == "adxl203_ads1115" and not isinstance(
            sample, AdxlSample
        ):
            return

        self._plot.add_sample(sample)  # type: ignore[arg-type]

    @Slot()
    def on_stream_started(self) -> None:
        self._plot.clear()
        self._status_label.setText("Streaming...")

    @Slot()
    def on_stream_stopped(self) -> None:
        # Keep the last trace visible but update status text.
        self._status_label.setText("Stream stopped.")

    # --------------------------------------------------------------- internals
    def _rebuild_channel_checkboxes(self) -> None:
        # Clear existing widgets
        while self._channel_layout.count():
            item = self._channel_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._channel_checkboxes.clear()

        sensor_type = self.sensor_combo.currentData()
        if sensor_type == "mpu6050":
            channels = ["ax", "ay", "az", "gx", "gy", "gz"]
            default_checked = {"ax", "ay", "gz"}
        else:
            channels = ["x", "y"]
            default_checked = set(channels)

        for ch in channels:
            cb = QCheckBox(ch)
            cb.setChecked(ch in default_checked)
            cb.toggled.connect(self._update_visible_channels)
            self._channel_layout.addWidget(cb)
            self._channel_checkboxes[ch] = cb

        self._channel_layout.addStretch()
        self._update_visible_channels()

    def _update_visible_channels(self) -> None:
        selected = [
            name
            for name, cb in self._channel_checkboxes.items()
            if cb.isChecked()
        ]
        self._plot.set_visible_channels(selected)
