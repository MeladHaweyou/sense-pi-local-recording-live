"""Recorder tab for starting/stopping Raspberry Pi loggers."""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class RecorderTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Recorder controls will go here."))
