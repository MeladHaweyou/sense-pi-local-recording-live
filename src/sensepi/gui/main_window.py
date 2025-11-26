"""Main window for the SensePi GUI."""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from ..config.app_config import AppPaths
from .tabs.tab_fft import FftTab
from .tabs.tab_offline import OfflineTab
from .tabs.tab_recorder import RecorderTab
from .tabs.tab_settings import SettingsTab
from .tabs.tab_signals import SignalsTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SensePi Recorder")

        self._tabs = QTabWidget()

        app_paths = AppPaths()

        self.recorder_tab = RecorderTab()
        self.signals_tab = SignalsTab()
        self.fft_tab = FftTab()
        self.settings_tab = SettingsTab()
        self.offline_tab = OfflineTab(app_paths)

        # Move the Connect/Recorder controls into the Signals tab
        self.signals_tab.attach_recorder_controls(self.recorder_tab)

        # Only expose Signals/FFT/Settings/Offline as main tabs
        # (RecorderTab is now used as a hidden backend controller)
        self._tabs.addTab(self.signals_tab, "Signals")
        self._tabs.addTab(self.fft_tab, "FFT")
        self._tabs.addTab(self.settings_tab, "Settings")
        self._tabs.addTab(self.offline_tab, "Offline")

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

        self.signals_tab.start_stream_requested.connect(
            self._on_start_stream_requested
        )
        self.signals_tab.stop_stream_requested.connect(
            self._on_stop_stream_requested
        )

        self.recorder_tab.error_reported.connect(
            self.signals_tab.handle_error
        )
        self.recorder_tab.rate_updated.connect(
            self.signals_tab.update_stream_rate
        )

        self.settings_tab.sensorsUpdated.connect(
            self.recorder_tab.on_sensors_updated
        )

    def _on_start_stream_requested(self, recording: bool) -> None:
        """
        Called when the user presses Start in the Signals tab.
        Delegates to RecorderTab using the current Connect-tab settings.
        """
        try:
            self.recorder_tab.start_live_stream(recording=recording)
        except Exception as exc:
            # TODO: replace with user-visible dialog if desired
            print(f"Failed to start stream: {exc!r}")

    def _on_stop_stream_requested(self) -> None:
        try:
            self.recorder_tab.stop_live_stream()
        except Exception as exc:
            print(f"Failed to stop stream: {exc!r}")
