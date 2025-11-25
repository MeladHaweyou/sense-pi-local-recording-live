"""Main window for the SensePi GUI."""

from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from .tabs.tab_fft import FftTab
from .tabs.tab_recorder import RecorderTab
from .tabs.tab_settings import SettingsTab
from .tabs.tab_signals import SignalsTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SensePi Recorder")

        self._tabs = QTabWidget()
        self._tabs.addTab(RecorderTab(), "Recorder")
        self._tabs.addTab(SignalsTab(), "Signals")
        self._tabs.addTab(FftTab(), "FFT")
        self._tabs.addTab(SettingsTab(), "Settings")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self._tabs)

        self.setCentralWidget(container)
