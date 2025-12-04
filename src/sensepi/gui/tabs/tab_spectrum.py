from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class SpectrumTab(QWidget):
    """
    Spectrum / FFT view.

    Phase 2: Display a placeholder FFT using dummy data.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Spectrum (FFT) – placeholder"))

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self._ax = self.figure.add_subplot(111)
        self._draw_placeholder()

    def _draw_placeholder(self) -> None:
        # Example: FFT of a sine wave
        t = np.linspace(0, 1.0, 1000, endpoint=False)
        sig = np.sin(2 * np.pi * 50 * t)
        fft = np.fft.rfft(sig)
        freqs = np.fft.rfftfreq(t.size, d=t[1] - t[0])

        self._ax.clear()
        self._ax.plot(freqs, np.abs(fft))
        self._ax.set_xlabel("Frequency [Hz]")
        self._ax.set_ylabel("Magnitude")
        self._ax.set_title("Dummy FFT (Phase 2)")
        self.canvas.draw_idle()
