from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget
import numpy as np
import pyqtgraph as pg


class LiveSignalsTab(QWidget):
    """
    Live signals view.

    Phase 2: uses dummy data (e.g., a sine wave) and updates on a timer.
    Later phases will connect this to real streaming buffers.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)

        # Channel visibility controls (dummy)
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Channels:"))
        self.channel_checks: dict[str, QCheckBox] = {}
        for ch in ["ax", "ay", "az", "gx", "gy", "gz"]:
            cb = QCheckBox(ch)
            cb.setChecked(ch in ["ax", "ay", "az"])
            cb.stateChanged.connect(self._on_channel_visibility_changed)
            self.channel_checks[ch] = cb
            channel_layout.addWidget(cb)
        layout.addLayout(channel_layout)

        # pyqtgraph plot
        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)

        # Create dummy curves
        self._x = np.linspace(0, 1, 500)
        self._curves: dict[str, pg.PlotDataItem] = {}
        for ch in self.channel_checks:
            curve = self.plot_widget.plot(self._x, np.zeros_like(self._x), name=ch)
            self._curves[ch] = curve

        # Time state for dummy animation
        self._t = 0.0

        # QTimer driving the fake live data
        self._timer = QTimer(self)
        self._timer.setInterval(40)  # ~25 Hz GUI update
        self._timer.timeout.connect(self._advance_dummy_data)
        self._timer.start()

    def _on_channel_visibility_changed(self) -> None:
        for ch, cb in self.channel_checks.items():
            self._curves[ch].setVisible(cb.isChecked())
        print(
            "[LiveSignalsTab] visible channels =",
            [ch for ch, cb in self.channel_checks.items() if cb.isChecked()],
        )

    def _advance_dummy_data(self) -> None:
        """
        Advance dummy sine-wave data over time for all channels.

        Phase 2: this is purely fake data for the GUI; later phases will
        replace this with real streaming buffers.
        """
        # Advance “time” based on timer interval
        if self._timer is None:
            return
        self._t += self._timer.interval() / 1000.0  # seconds

        base_freq_hz = 2.0
        for i, (ch, curve) in enumerate(self._curves.items()):
            # Different phase per channel, just for visual separation
            phase = i * np.pi / 3.0
            y = np.sin(2 * np.pi * base_freq_hz * self._x + phase + self._t)
            curve.setData(self._x, y)
