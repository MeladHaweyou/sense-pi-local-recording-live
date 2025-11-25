"""FFT/analysis tab."""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class FftTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("FFT view will go here."))
