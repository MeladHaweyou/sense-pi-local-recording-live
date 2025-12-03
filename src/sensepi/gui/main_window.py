"""Main window for the SensePi GUI."""

from __future__ import annotations

import logging

from PySide6.QtCore import Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from ..config.app_config import AppConfig, AppPaths
from .config.acquisition_state import GuiAcquisitionConfig, SensorSelectionConfig
from .tabs.tab_fft import FftTab
from .tabs.tab_logs import LogsTab
from .tabs.tab_recorder import RecorderTab
from .tabs.tab_recordings import RecordingsTab
from .tabs.tab_settings import SettingsTab
from .tabs.tab_signals import SignalsTab


class MainWindow(QMainWindow):
    """Main window for the SensePi GUI."""

    def __init__(self, app_config: AppConfig | None = None) -> None:
        super().__init__()
        self.setWindowTitle("SensePi Recorder")

        self._app_config = app_config or AppConfig()
        self._tabs = QTabWidget()
        self._logger = logging.getLogger(__name__)

        self._current_sensor_selection = SensorSelectionConfig()
        self._current_gui_acquisition_config: GuiAcquisitionConfig | None = None

        self._build_tabs()

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

        self.recorder_tab = RecorderTab()
        self.settings_tab = SettingsTab()
        self.signals_tab = SignalsTab(
            recorder_tab=self.recorder_tab, parent=self, app_config=self._app_config
        )
        self.signals_tab.attach_recorder_controls(self.recorder_tab)
        self.fft_tab = FftTab(
            recorder_tab=self.recorder_tab,
            signals_tab=self.signals_tab,
            parent=self,
            app_config=self._app_config,
        )
        self.recordings_tab = RecordingsTab(app_paths, self.recorder_tab)
        self.offline_tab = self.recordings_tab.offline_tab
        self.logs_tab = LogsTab(app_paths)

        self.signals_tab.start_stream_requested.connect(
            self._on_start_stream_requested
        )
        self.signals_tab.stop_stream_requested.connect(self._on_stop_stream_requested)
        self.recorder_tab.sensorSelectionChanged.connect(
            self._on_sensor_selection_changed
        )
        self.signals_tab.acquisitionConfigChanged.connect(
            self._on_acquisition_config_changed
        )

        self._tabs.addTab(self.signals_tab, self.tr("Live Signals"))
        self._tabs.addTab(self.fft_tab, self.tr("Spectrum"))
        self._tabs.addTab(self.recordings_tab, self.tr("Recordings"))
        self._tabs.addTab(self.settings_tab, self.tr("Settings"))
        self._tabs.addTab(self.logs_tab, self.tr("App Logs"))

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self._tabs)

        self.setCentralWidget(container)

    @Slot(bool)
    def _on_start_stream_requested(self, recording: bool) -> None:
        acquisition = self.signals_tab.current_acquisition_settings()
        stream_rate_hz = float(acquisition.effective_stream_rate_hz)

        sensor_selection = self._current_sensor_selection

        gui_cfg = GuiAcquisitionConfig(
            sampling=acquisition.sampling,
            stream_rate_hz=stream_rate_hz,
            record_only=bool(getattr(acquisition, "record_only", False)),
            sensor_selection=sensor_selection,
        )
        self._current_gui_acquisition_config = gui_cfg
        self._logger.info(
            "Starting stream with GuiAcquisitionConfig: %s", gui_cfg.summary()
        )

        self.recorder_tab.apply_sensor_selection(gui_cfg.sensor_selection)
        self.recorder_tab.apply_gui_acquisition_config(gui_cfg)

        self.signals_tab.set_sensor_selection(gui_cfg.sensor_selection)
        self.signals_tab.apply_gui_acquisition_config(gui_cfg)

        self.fft_tab.set_sensor_selection(gui_cfg.sensor_selection)
        self.fft_tab.apply_gui_acquisition_config(gui_cfg)

        self.signals_tab.set_sampling_rate_hz(float(gui_cfg.sampling.device_rate_hz))
        self.signals_tab.update_stream_rate(stream_rate_hz)
        self.fft_tab.update_stream_rate(stream_rate_hz)

        self.fft_tab.set_refresh_interval_ms(acquisition.fft_refresh_ms)

        record_only = gui_cfg.record_only
        recording_flag = bool(recording or record_only)

        self.signals_tab.set_record_only_mode(record_only)
        self.fft_tab.set_record_only_mode(record_only)
        if record_only:
            self._logger.info("Record-only mode active: live streaming disabled.")

        session_name = self.signals_tab.session_name() or None
        self.recorder_tab.start_live_stream(
            recording=recording_flag,
            acquisition=acquisition,
            session_name=session_name,
        )

    @Slot()
    def _on_stop_stream_requested(self) -> None:
        self.recorder_tab.stop_live_stream()

    @Slot(SensorSelectionConfig)
    def _on_sensor_selection_changed(self, cfg: SensorSelectionConfig) -> None:
        self._current_sensor_selection = cfg
        print("[MainWindow] SensorSelectionConfig:", cfg.summary())
        self.signals_tab.set_sensor_selection(cfg)
        self.fft_tab.set_sensor_selection(cfg)

    @Slot(GuiAcquisitionConfig)
    def _on_acquisition_config_changed(self, cfg: GuiAcquisitionConfig) -> None:
        self._current_gui_acquisition_config = cfg
        print("[MainWindow] GuiAcquisitionConfig:", cfg.summary())
        self.signals_tab.apply_gui_acquisition_config(cfg)
        self.recorder_tab.apply_gui_acquisition_config(cfg)
        self.fft_tab.apply_gui_acquisition_config(cfg)
        self.signals_tab.set_record_only_mode(cfg.record_only)
        self.fft_tab.set_record_only_mode(cfg.record_only)
