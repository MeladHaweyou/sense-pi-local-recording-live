"""Main window for the SensePi GUI."""

from __future__ import annotations

from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from ..config.app_config import AppConfig, AppPaths
from .tabs.tab_fft import FftTab
from .tabs.tab_logs import LogsTab
from .tabs.tab_offline import OfflineTab
from .tabs.tab_recorder import RecorderTab
from .tabs.tab_settings import SettingsTab
from .tabs.tab_signals import SignalsTab, create_signal_plot_widget


class MainWindow(QMainWindow):
    """Main window for the SensePi GUI.

    Responsibilities:
    - Owns the high-level workflow tabs: Device, Sensors & Rates, Live Signals,
      Spectrum, Recordings, and App Logs.
    - Wires RecorderTab start/stop signals into live plotting (SignalsTab) and
      spectrum (FftTab).
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

        view_menu = self.menuBar().addMenu("&View")
        self._act_show_perf_hud = QAction("Show Performance HUD", self)
        self._act_show_perf_hud.setCheckable(True)
        self._act_show_perf_hud.setChecked(False)
        self._act_show_perf_hud.toggled.connect(
            self.signals_tab.set_perf_hud_visible
        )
        view_menu.addAction(self._act_show_perf_hud)

        self.recorder_tab.recording_started.connect(
            self.signals_tab.on_stream_started
        )
        self.recorder_tab.recording_started.connect(
            self.fft_tab.on_stream_started
        )

        self.recorder_tab.recording_stopped.connect(
            self.signals_tab.on_stream_stopped
        )
        self.recorder_tab.recording_stopped.connect(
            self.fft_tab.on_stream_stopped
        )
        self.recorder_tab.recording_stopped.connect(
            self._on_recording_stopped
        )

        self.signals_tab.start_stream_requested.connect(
            self._on_start_stream_requested
        )
        self.signals_tab.stop_stream_requested.connect(
            self._on_stop_stream_requested
        )

        self.recorder_tab.recording_error.connect(
            self.signals_tab.handle_error
        )
        self.recorder_tab.rate_updated.connect(
            self.signals_tab.update_stream_rate
        )
        self.recorder_tab.rate_updated.connect(
            self.fft_tab.update_stream_rate
        )
        self.settings_tab.hostsUpdated.connect(
            self.recorder_tab.on_hosts_updated
        )
        self.settings_tab.sensorsUpdated.connect(
            self.recorder_tab.on_sensors_updated
        )

    def _on_start_stream_requested(self, recording: bool) -> None:
        """
        Called when the user presses Start in the Live Signals tab.
        Delegates to RecorderTab using the current Device tab settings.
        """
        try:
            acquisition = self.signals_tab.current_acquisition_settings()
            stream_rate_hz = acquisition.effective_stream_rate_hz

            # Update GUI refresh behaviour before data starts flowing
            if acquisition.signals_mode == "adaptive":
                self.signals_tab.set_refresh_mode(
                    "follow_sampling_rate", stream_rate_hz
                )
            else:
                self.signals_tab.fixed_interval_ms = acquisition.signals_refresh_ms
                self.signals_tab.set_refresh_mode("fixed")

            self.signals_tab.update_stream_rate("mpu6050", stream_rate_hz)
            self.fft_tab.set_refresh_interval_ms(acquisition.fft_refresh_ms)
            self.fft_tab.update_stream_rate("mpu6050", stream_rate_hz)

            session_name = self.signals_tab.session_name()
            self.recorder_tab.start_live_stream(
                recording=recording,
                acquisition=acquisition,
                session_name=session_name or None,
            )
        except Exception as exc:
            self.recorder_tab.report_error(f"Failed to start stream: {exc!r}")

    def _on_stop_stream_requested(self) -> None:
        try:
            self.recorder_tab.stop_live_stream()
        except Exception as exc:
            self.recorder_tab.report_error(f"Failed to stop stream: {exc!r}")

    def _on_recording_stopped(self) -> None:
        """
        Called whenever a recording run finishes.
        Hints that offline sync is now the next step.
        """
        status = self.statusBar()

        remote_dir = None
        try:
            remote_dir = self.recorder_tab.current_remote_data_dir()
        except AttributeError:
            remote_dir = None

        if remote_dir:
            dest_text = (
                remote_dir.as_posix()
                if hasattr(remote_dir, "as_posix")
                else str(remote_dir)
            )
            msg = (
                f"Recording stopped. Logs saved to {dest_text} on the Pi. "
                "Open the Recordings tab to sync and replay this session."
            )
        else:
            msg = (
                "Recording stopped. Open the Recordings tab to sync logs from "
                "the Pi and replay previous sessions."
            )

        status.showMessage(msg, 8000)

        idx = self._tabs.indexOf(self.offline_tab)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

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
        backend = self._app_config.normalized_signal_backend()
        plot_window_s = self._app_config.plot_performance.normalized_time_window_s()
        plot_widget = create_signal_plot_widget(
            parent=None,
            backend=backend,
            max_seconds=plot_window_s,
        )
        self.signals_tab = SignalsTab(
            self.recorder_tab,
            plot_widget=plot_widget,
            app_config=self._app_config,
        )
        self.fft_tab = FftTab(
            self.recorder_tab,
            self.signals_tab,
            app_config=self._app_config,
        )
        self.signals_tab.fft_refresh_interval_changed.connect(
            self.fft_tab.set_refresh_interval_ms
        )
        self.settings_tab = SettingsTab()
        self.offline_tab = OfflineTab(app_paths, self.recorder_tab)
        self.logs_tab = LogsTab(app_paths)

        # Order tabs by the typical workflow from device setup through analysis.
        self._tabs.addTab(self.recorder_tab, self.tr("Device"))
        self._tabs.addTab(self.settings_tab, self.tr("Sensors && Rates"))
        self._tabs.addTab(self.signals_tab, self.tr("Live Signals"))
        self._tabs.addTab(self.fft_tab, self.tr("Spectrum"))
        self._tabs.addTab(self.offline_tab, self.tr("Recordings"))
        self._tabs.addTab(self.logs_tab, self.tr("App Logs"))

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self._tabs)

        self.setCentralWidget(container)
