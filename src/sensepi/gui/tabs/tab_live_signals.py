from __future__ import annotations

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

        # TODO: Phase 3+ – connect to QTimer and real buffers.
        # For now, optionally create a basic timer with fake data, or leave static.

    def _on_channel_visibility_changed(self) -> None:
        for ch, cb in self.channel_checks.items():
            self._curves[ch].setVisible(cb.isChecked())
        print(
            "[LiveSignalsTab] visible channels =",
            [ch for ch, cb in self.channel_checks.items() if cb.isChecked()],
        )
