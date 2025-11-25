# ui/main_window.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTabWidget, QLabel

from ..core.state import AppState
from .tab_ssh import SSHTab
from .tab_signals import SignalsTab
from .tab_recorder import RecorderTab
from .tab_fft import FFTTab
from .styles import apply_styles


class MainWindow(QMainWindow):
    """Top-level window with core tabs only (Signals, Record, FFT + placeholders)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sense Pi – Qt Shell")
        self.resize(1000, 700)

        self.state = AppState()

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # SSH control tab (connection + run config)
        self.ssh_tab = SSHTab(self.state)
        self.tabs.addTab(self.ssh_tab, "SSH")

        # Signals (time-domain)
        self.signals_tab = SignalsTab(self.state, parent=self)
        self.tabs.addTab(self.signals_tab, "Signals")

        # Recorder (Capture / View / Split / FFT)
        self.recorder_tab = RecorderTab(self.state, parent=self)
        self.tabs.addTab(self.recorder_tab, "Record")

        # FFT (frequency-domain, 9 channels)
        self.fft_tab = FFTTab(self.state, parent=self)
        self.tabs.addTab(self.fft_tab, "FFT")

        # Simple placeholders for future features
        for title in ["Analysis results", "Digital twin"]:
            page = QWidget()
            vbox = QVBoxLayout(page)
            label = QLabel("Placeholder – not implemented yet")
            label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            vbox.addStretch(1)
            vbox.addWidget(label)
            vbox.addStretch(1)
            self.tabs.addTab(page, title)

        apply_styles(self)
