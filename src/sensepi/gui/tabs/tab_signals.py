"""Live signal view tab."""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SignalsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Live signal plot will go here."))
