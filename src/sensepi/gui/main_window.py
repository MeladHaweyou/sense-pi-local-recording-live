"""Main window for the SensePi GUI."""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from ..config.app_config import AppConfig, AppPaths
from .tabs.tab_acquisition import AcquisitionRatesTab
from .tabs.tab_device_sensors import DeviceSensorsTab
from .tabs.tab_live_signals import LiveSignalsTab
from .tabs.tab_logs import LogsTab
from .tabs.tab_recorder import RecorderTab
from .tabs.tab_recordings import RecordingsTab
from .tabs.tab_settings import SettingsTab
from .tabs.tab_spectrum import SpectrumTab


class MainWindow(QMainWindow):
    """Main window for the SensePi GUI.

    Responsibilities:
    - Owns the high-level workflow tabs: Device, Sensors & Rates, Live Signals,
      Spectrum, Recordings, and App Logs.
    - Acts as the integration point for app-wide configuration (AppConfig,
      AppPaths). New tabs should be registered here to participate in the
      coordinated workflow.
    """
    def __init__(self, app_config: AppConfig | None = None) -> None:
        super().__init__()
        self.setWindowTitle("SensePi Recorder")

        self._app_config = app_config or AppConfig()
        self._tabs = QTabWidget()

        self._build_tabs()

        # TODO: When backend wiring is reintroduced, connect the recorder,
        # live signals, and spectrum tabs here.

    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self.recorder_tab.stop_live_stream(wait=True)
        except Exception as exc:  # pragma: no cover - best-effort shutdown
            self.recorder_tab.report_error(
                f"Failed to stop stream on close: {exc!r}"
            )
        super().closeEvent(event)

    def _build_tabs(self) -> None:
        """Create and register all main workflow tabs."""
        app_paths = AppPaths()

        # Phase 2: scaffolded UI tabs (logic wiring to be added later).
        self.device_sensors_tab = DeviceSensorsTab(parent=self)
        self.acquisition_tab = AcquisitionRatesTab(parent=self)
        self.signals_tab = LiveSignalsTab(parent=self)
        self.fft_tab = SpectrumTab(parent=self)

        # Keep existing tabs around for offline browsing and settings, even in
        # placeholder mode.
        self.recorder_tab = RecorderTab()
        self.settings_tab = SettingsTab()
        self.recordings_tab = RecordingsTab(app_paths, self.recorder_tab)
        # Expose the inner OfflineTab for compatibility with existing code paths.
        self.offline_tab = self.recordings_tab.offline_tab
        self.logs_tab = LogsTab(app_paths)

        # Order tabs by the typical workflow from device setup through analysis.
        self._tabs.addTab(self.device_sensors_tab, self.tr("Device && Sensors"))
        self._tabs.addTab(self.acquisition_tab, self.tr("Acquisition && Rates"))
        self._tabs.addTab(self.signals_tab, self.tr("Live Signals"))
        self._tabs.addTab(self.fft_tab, self.tr("Spectrum"))
        self._tabs.addTab(self.recordings_tab, self.tr("Recordings"))
        self._tabs.addTab(self.logs_tab, self.tr("App Logs"))

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self._tabs)

        self.setCentralWidget(container)
