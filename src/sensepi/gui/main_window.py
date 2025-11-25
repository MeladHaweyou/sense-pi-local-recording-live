"""Main window for the SensePi GUI."""

from __future__ import annotations

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

        self.recorder_tab = RecorderTab()
        self.signals_tab = SignalsTab()
        self.fft_tab = FftTab()
        self.settings_tab = SettingsTab()

        self._tabs.addTab(self.recorder_tab, "Recorder")
        self._tabs.addTab(self.signals_tab, "Signals")
        self._tabs.addTab(self.fft_tab, "FFT")
        self._tabs.addTab(self.settings_tab, "Settings")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self._tabs)

        self.setCentralWidget(container)

        # Wire sample streams from RecorderTab into the visualization tabs
        self.recorder_tab.sample_received.connect(
            self.signals_tab.handle_sample
        )
        self.recorder_tab.sample_received.connect(self.fft_tab.handle_sample)

        self.recorder_tab.streaming_started.connect(
            self.signals_tab.on_stream_started
        )
        self.recorder_tab.streaming_started.connect(
            self.fft_tab.on_stream_started
        )

        self.recorder_tab.streaming_stopped.connect(
            self.signals_tab.on_stream_stopped
        )
        self.recorder_tab.streaming_stopped.connect(
            self.fft_tab.on_stream_stopped
        )
