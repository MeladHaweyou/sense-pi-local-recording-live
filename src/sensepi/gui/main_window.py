"""Main window for the SensePi GUI."""

from __future__ import annotations

import logging

from PySide6.QtCore import Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from ..config.app_config import AppConfig, AppPaths, HostInventory
from .config.acquisition_state import (
    CalibrationOffsets,
    GuiAcquisitionConfig,
    SensorSelectionConfig,
)
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
        self._current_calibration_offsets: CalibrationOffsets | None = None

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
        self.recorder_tab.streaming_started.connect(self.signals_tab.on_stream_started)
        self.recorder_tab.streaming_stopped.connect(self.signals_tab.on_stream_stopped)
        self.settings_tab.sensorSelectionChanged.connect(
            self._on_sensor_selection_changed
        )
        self.signals_tab.acquisitionConfigChanged.connect(
            self._on_acquisition_config_changed
        )
        self.signals_tab.calibrationChanged.connect(self._on_calibration_changed)
        if hasattr(self.settings_tab, "acquisitionConfigChanged"):
            self.settings_tab.acquisitionConfigChanged.connect(
                self.fft_tab.update_acquisition_config
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
        acquisition_settings = self.signals_tab.current_acquisition_settings()
        acquisition_widget = getattr(self.signals_tab, "_acquisition_widget", None)

        sensor_selection = getattr(self, "_current_sensor_selection", None)
        if sensor_selection is None:
            sensor_selection = SensorSelectionConfig(active_sensors=[], active_channels=[])

        if acquisition_widget is not None:
            gui_cfg = acquisition_widget.current_gui_acquisition_config(
                sensor_selection=sensor_selection
            )
        else:
            stream_rate_hz = float(acquisition_settings.effective_stream_rate_hz)
            gui_cfg = GuiAcquisitionConfig(
                sampling=acquisition_settings.sampling,
                stream_rate_hz=stream_rate_hz,
                record_only=bool(getattr(acquisition_settings, "record_only", False)),
                sensor_selection=sensor_selection,
            )

        gui_cfg.calibration = self._current_calibration_offsets
        self._current_gui_acquisition_config = gui_cfg
        self._logger.info(
            "Starting stream with GuiAcquisitionConfig: %s", gui_cfg.summary()
        )

        host_cfg_raw = self.settings_tab.current_host_config()
        if host_cfg_raw is None:
            self.recorder_tab.report_error("No Raspberry Pi host selected.")
            return

        host_cfg = HostInventory().to_host_config(host_cfg_raw)

        self.recorder_tab.apply_sensor_selection(gui_cfg.sensor_selection)
        self.recorder_tab.apply_gui_acquisition_config(gui_cfg)

        self.signals_tab.set_sensor_selection(gui_cfg.sensor_selection)
        self.signals_tab.apply_gui_acquisition_config(gui_cfg)

        self.fft_tab.update_sensor_selection(gui_cfg.sensor_selection)
        self.fft_tab.update_acquisition_config(gui_cfg)

        self.signals_tab.set_sampling_rate_hz(gui_cfg.stream_rate_hz)
        self.fft_tab.set_sampling_rate_hz(gui_cfg.stream_rate_hz)

        self.fft_tab.set_refresh_interval_ms(acquisition_settings.fft_refresh_ms)

        record_only = gui_cfg.record_only
        recording_flag = bool(recording or record_only)

        if recording_flag:
            self._log_recording_calibration("starting")

        self.signals_tab.set_record_only_mode(record_only)
        self.fft_tab.set_record_only_mode(record_only)
        if record_only:
            self._logger.info("Record-only mode active: live streaming disabled.")

        self.recorder_tab.start_live_stream(
            recording_enabled=recording_flag,
            gui_config=gui_cfg,
            host_cfg=host_cfg,
        )

    @Slot()
    def _on_stop_stream_requested(self) -> None:
        if getattr(self.recorder_tab, "_recording_mode", False):
            self._log_recording_calibration("stopping")
        self.recorder_tab.stop_live_stream()

    @Slot(SensorSelectionConfig)
    def _on_sensor_selection_changed(self, cfg: SensorSelectionConfig) -> None:
        self._current_sensor_selection = cfg
        print("Updated sensor selection:", cfg)
        self.signals_tab.set_sensor_selection(cfg)
        self.fft_tab.update_sensor_selection(cfg)

    @Slot(GuiAcquisitionConfig)
    def _on_acquisition_config_changed(self, cfg: GuiAcquisitionConfig) -> None:
        self._current_gui_acquisition_config = cfg
        if getattr(cfg, "calibration", None) is not None:
            self._current_calibration_offsets = cfg.calibration
        print("[MainWindow] GuiAcquisitionConfig:", cfg.summary())
        self.signals_tab.apply_gui_acquisition_config(cfg)
        self.recorder_tab.apply_gui_acquisition_config(cfg)
        self.fft_tab.update_acquisition_config(cfg)
        self.signals_tab.set_record_only_mode(cfg.record_only)
        self.fft_tab.set_record_only_mode(cfg.record_only)

    @Slot(CalibrationOffsets)
    def _on_calibration_changed(self, offsets: CalibrationOffsets) -> None:
        self._current_calibration_offsets = offsets
        self.fft_tab.set_calibration_offsets(offsets)

    def _log_recording_calibration(self, action: str) -> None:
        if not self.signals_tab.apply_calibration_to_recording():
            return

        offsets = self._current_calibration_offsets
        if offsets is None or offsets.is_empty():
            self._logger.info(
                "Recording %s: calibration requested but no offsets present.", action
            )
            return

        self._logger.info(
            "Recording %s with calibration (%d channels) at %s: %s",
            action,
            len(offsets.per_sensor_channel_offset),
            offsets.timestamp,
            offsets.description or "no description",
        )
        # TODO: apply calibration offsets to recorded samples before saving.

    def get_current_calibration(self) -> CalibrationOffsets | None:
        """Return the most recent calibration collected from the Signals tab."""

        return self._current_calibration_offsets
