from __future__ import annotations

import math
from typing import Dict, Iterable, Optional, Set, Tuple

from PySide6.QtCore import Signal, Slot, QTimer
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

        self._figure = Figure(figsize=(6, 6), tight_layout=True)
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

        # Time window: last max_seconds across all sensors/channels
        latest = max(buf[-1][0] for buf in active_buffers)
        cutoff = latest - self._max_seconds

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

                times = [t - cutoff for (t, _) in points]
                values = [v for (_, v) in points]

                ax.plot(times, values)

                # X label only on the bottom row
                if row_idx == nrows - 1:
                    ax.set_xlabel("Time (s)")

                # Leftmost column shows sensor row + channel
                if col_idx == 0:
                    if sid == 0:
                        prefix = "Live"
                    else:
                        prefix = f"S{sid}"
                    ax.set_ylabel(f"{prefix}\n{ch.upper()}")
                else:
                    ax.set_ylabel(ch.upper())

                ax.grid(True)

        self._figure.tight_layout()
        self._canvas.draw_idle()

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

        # periodic redraw of the plot
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._plot.redraw)
        self._timer.start()

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
            # You can reduce this to ["ax", "ay", "gz"] if you only want
            # the default 3 channels initially.
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
        # Preserve the checkbox order as the column order
        visible = [
            ch for ch, cb in self._channel_checkboxes.items() if cb.isChecked()
        ]
        self._plot.set_visible_channels(visible)

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
