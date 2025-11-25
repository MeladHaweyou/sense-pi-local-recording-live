"""Settings tab for SSH and application defaults."""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SettingsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Settings and configuration will go here."))
