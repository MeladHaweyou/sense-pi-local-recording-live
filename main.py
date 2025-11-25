from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTabWidget,
    QLabel,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QMessageBox,
    QGroupBox,
)

from local_plot_runner import LocalPlotRunner
from ssh_client import SSHConfig
from pi_recorder import PiRecorder


PROJECT_ROOT = Path(__file__).resolve().parent


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Sense-Pi Recorder")
        self.recorder: Optional[PiRecorder] = None
        self.plot_runner = LocalPlotRunner(project_root=PROJECT_ROOT, script_name="plotter.py")

        self._build_ui()

    def _build_ui(self):
        central = QWidget(self)
        root_layout = QVBoxLayout(central)

        # --- Connection section -------------------------------------------------
        conn_group = QGroupBox("Raspberry Pi connection", central)
        conn_form = QFormLayout(conn_group)

        self.host_edit = QLineEdit("raspberrypi.local", conn_group)
        self.user_edit = QLineEdit("pi", conn_group)
        self.password_edit = QLineEdit(conn_group)
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.port_edit = QLineEdit("22", conn_group)
        # Path on the Pi where your logger scripts live
        self.scripts_dir_edit = QLineEdit(
            "~/sense-pi/raspberrypi_scripts", conn_group
        )

        conn_form.addRow("Host:", self.host_edit)
        conn_form.addRow("User:", self.user_edit)
        conn_form.addRow("Password:", self.password_edit)
        conn_form.addRow("Port:", self.port_edit)
        conn_form.addRow("Remote scripts dir:", self.scripts_dir_edit)

        btn_row = QHBoxLayout()
        self.connect_btn = QPushButton("Connect", conn_group)
        self.disconnect_btn = QPushButton("Disconnect", conn_group)
        self.disconnect_btn.setEnabled(False)
        btn_row.addWidget(self.connect_btn)
        btn_row.addWidget(self.disconnect_btn)
        conn_form.addRow(btn_row)

        root_layout.addWidget(conn_group)

        # --- Tabs for individual loggers ---------------------------------------
        self.tabs = QTabWidget(central)
        self._build_mpu6050_tab()
        self._build_adxl203_tab()
        root_layout.addWidget(self.tabs)

        # --- Status bar-ish label ----------------------------------------------
        self.status_label = QLabel("Not connected.", central)
        self.status_label.setAlignment(Qt.AlignLeft)
        root_layout.addWidget(self.status_label)

        # --- Combined start/stop for recording + plotting -------------------
        action_row = QHBoxLayout()
        self.start_all_btn = QPushButton("Start Recording + Plot", central)
        self.stop_all_btn = QPushButton("Stop Recording + Plot", central)
        self.stop_all_btn.setEnabled(False)
        action_row.addWidget(self.start_all_btn)
        action_row.addWidget(self.stop_all_btn)
        root_layout.addLayout(action_row)

        self.setCentralWidget(central)

        # Signals
        self.connect_btn.clicked.connect(self.on_connect_clicked)
        self.disconnect_btn.clicked.connect(self.on_disconnect_clicked)
        self.start_all_btn.clicked.connect(self.handle_start_clicked)
        self.stop_all_btn.clicked.connect(self.handle_stop_clicked)

    def _build_mpu6050_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.mpu_status_label = QLabel("Stopped", tab)
        layout.addWidget(self.mpu_status_label)

        btn_row = QHBoxLayout()
        self.mpu_start_btn = QPushButton("Start MPU6050 logger", tab)
        self.mpu_stop_btn = QPushButton("Stop", tab)
        self.mpu_stop_btn.setEnabled(False)
        btn_row.addWidget(self.mpu_start_btn)
        btn_row.addWidget(self.mpu_stop_btn)
        layout.addLayout(btn_row)

        form = QFormLayout()
        self.mpu_extra_args_edit = QLineEdit(tab)
        self.mpu_extra_args_edit.setPlaceholderText(
            "Extra command-line args (optional, e.g. --log-dir /home/pi/logs/mpu)"
        )
        form.addRow("Extra args:", self.mpu_extra_args_edit)
        layout.addLayout(form)

        self.tabs.addTab(tab, "MPU6050")

        self.mpu_start_btn.clicked.connect(self.on_mpu_start_clicked)
        self.mpu_stop_btn.clicked.connect(self.on_mpu_stop_clicked)

    def _build_adxl203_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.adxl_status_label = QLabel("Stopped", tab)
        layout.addWidget(self.adxl_status_label)

        btn_row = QHBoxLayout()
        self.adxl_start_btn = QPushButton("Start ADXL203 logger", tab)
        self.adxl_stop_btn = QPushButton("Stop", tab)
        self.adxl_stop_btn.setEnabled(False)
        btn_row.addWidget(self.adxl_start_btn)
        btn_row.addWidget(self.adxl_stop_btn)
        layout.addLayout(btn_row)

        form = QFormLayout()
        self.adxl_extra_args_edit = QLineEdit(tab)
        self.adxl_extra_args_edit.setPlaceholderText(
            "Extra command-line args (optional, e.g. --log-dir /home/pi/logs/adxl)"
        )
        form.addRow("Extra args:", self.adxl_extra_args_edit)
        layout.addLayout(form)

        self.tabs.addTab(tab, "ADXL203")

        self.adxl_start_btn.clicked.connect(self.on_adxl_start_clicked)
        self.adxl_stop_btn.clicked.connect(self.on_adxl_stop_clicked)

    # ------------------------------------------------------------------ helpers
    def _ensure_recorder(self, *, show_dialog: bool = True) -> bool:
        if self.recorder is None:
            if show_dialog:
                QMessageBox.information(
                    self,
                    "Not connected",
                    "Please connect to the Raspberry Pi first.",
                )
            return False
        return True

    def _start_mpu6050(self, extra_args: str, *, show_dialog: bool = True) -> tuple[bool, Optional[str]]:
        if not self._ensure_recorder(show_dialog=show_dialog):
            return False, "Recorder not connected"

        try:
            pid = self.recorder.start_mpu6050(extra_args=extra_args)
        except Exception as exc:
            if show_dialog:
                QMessageBox.critical(
                    self,
                    "Start error",
                    f"Failed to start MPU6050 logger:\n{exc}",
                )
            return False, f"MPU6050 logger: {exc}"

        self.mpu_status_label.setText(f"Running (PID {pid})")
        self.mpu_start_btn.setEnabled(False)
        self.mpu_stop_btn.setEnabled(True)
        return True, None

    def _stop_mpu6050(self, *, show_dialog: bool = True) -> tuple[bool, Optional[str]]:
        if not self._ensure_recorder(show_dialog=show_dialog):
            return False, "Recorder not connected"

        try:
            stopped = self.recorder.stop_mpu6050()
        except Exception as exc:
            if show_dialog:
                QMessageBox.warning(
                    self,
                    "Stop error",
                    f"Error stopping MPU6050 logger:\n{exc}",
                )
            return False, f"MPU6050 logger: {exc}"

        if stopped:
            self.mpu_status_label.setText("Stopped")
        else:
            self.mpu_status_label.setText("Was not running")

        self.mpu_start_btn.setEnabled(True)
        self.mpu_stop_btn.setEnabled(False)
        return True, None

    def _start_adxl203(self, extra_args: str, *, show_dialog: bool = True) -> tuple[bool, Optional[str]]:
        if not self._ensure_recorder(show_dialog=show_dialog):
            return False, "Recorder not connected"

        try:
            pid = self.recorder.start_adxl203(extra_args=extra_args)
        except Exception as exc:
            if show_dialog:
                QMessageBox.critical(
                    self,
                    "Start error",
                    f"Failed to start ADXL203 logger:\n{exc}",
                )
            return False, f"ADXL203 logger: {exc}"

        self.adxl_status_label.setText(f"Running (PID {pid})")
        self.adxl_start_btn.setEnabled(False)
        self.adxl_stop_btn.setEnabled(True)
        return True, None

    def _stop_adxl203(self, *, show_dialog: bool = True) -> tuple[bool, Optional[str]]:
        if not self._ensure_recorder(show_dialog=show_dialog):
            return False, "Recorder not connected"

        try:
            stopped = self.recorder.stop_adxl203()
        except Exception as exc:
            if show_dialog:
                QMessageBox.warning(
                    self,
                    "Stop error",
                    f"Error stopping ADXL203 logger:\n{exc}",
                )
            return False, f"ADXL203 logger: {exc}"

        if stopped:
            self.adxl_status_label.setText("Stopped")
        else:
            self.adxl_status_label.setText("Was not running")

        self.adxl_start_btn.setEnabled(True)
        self.adxl_stop_btn.setEnabled(False)
        return True, None

    # ----------------------------------------------------------------- callbacks
    @Slot()
    def on_connect_clicked(self):
        host = self.host_edit.text().strip()
        username = self.user_edit.text().strip()
        password = self.password_edit.text()
        port_text = self.port_edit.text().strip() or "22"
        try:
            port = int(port_text)
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid port",
                f"Port must be an integer, got '{port_text}'.",
            )
            return

        scripts_dir = self.scripts_dir_edit.text().strip()

        cfg = SSHConfig(
            host=host,
            username=username,
            port=port,
            password=password or None,
        )

        recorder = PiRecorder(cfg, scripts_dir=scripts_dir)

        try:
            recorder.connect()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "SSH error",
                f"Could not connect to {host}:\n{exc}",
            )
            return

        self.recorder = recorder
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.status_label.setText(f"Connected to {host} as {username}")

    @Slot()
    def on_disconnect_clicked(self):
        if self.recorder is not None:
            try:
                self.recorder.disconnect()
            except Exception:
                # Best-effort; ignore errors on close
                pass
            self.recorder = None

        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.status_label.setText("Disconnected.")

        # Reset logger controls
        self.mpu_start_btn.setEnabled(True)
        self.mpu_stop_btn.setEnabled(False)
        self.mpu_status_label.setText("Stopped")

        self.adxl_start_btn.setEnabled(True)
        self.adxl_stop_btn.setEnabled(False)
        self.adxl_status_label.setText("Stopped")

        self.start_all_btn.setEnabled(True)
        self.stop_all_btn.setEnabled(False)

        try:
            self.plot_runner.stop()
        except Exception:
            # If we cannot stop the plotter, ignore during disconnect
            pass

    @Slot()
    def on_mpu_start_clicked(self):
        extra_args = self.mpu_extra_args_edit.text().strip()
        success, _ = self._start_mpu6050(extra_args)
        if not success:
            return

    @Slot()
    def on_mpu_stop_clicked(self):
        success, _ = self._stop_mpu6050()
        if not success:
            return

    @Slot()
    def on_adxl_start_clicked(self):
        extra_args = self.adxl_extra_args_edit.text().strip()
        success, _ = self._start_adxl203(extra_args)
        if not success:
            return

    @Slot()
    def on_adxl_stop_clicked(self):
        success, _ = self._stop_adxl203()
        if not success:
            return

    # ------------------------------------------------------------------
    # Combined start/stop for both loggers + local plotter
    # ------------------------------------------------------------------
    def handle_start_clicked(self):
        if not self._ensure_recorder():
            return

        mpu_args = self.mpu_extra_args_edit.text().strip()
        adxl_args = self.adxl_extra_args_edit.text().strip()

        mpu_started, mpu_err = self._start_mpu6050(mpu_args, show_dialog=False)
        if not mpu_started:
            QMessageBox.critical(
                self,
                "Start error",
                f"Failed to start MPU6050 logger:\n{mpu_err}",
            )
            return

        adxl_started, adxl_err = self._start_adxl203(adxl_args, show_dialog=False)
        if not adxl_started:
            QMessageBox.critical(
                self,
                "Start error",
                f"Failed to start ADXL203 logger:\n{adxl_err}",
            )
            self._stop_mpu6050(show_dialog=False)
            return

        try:
            self.plot_runner.start()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Start error",
                f"Failed to start local plotter:\n{exc}",
            )
            self._stop_mpu6050(show_dialog=False)
            self._stop_adxl203(show_dialog=False)
            return

        self.start_all_btn.setEnabled(False)
        self.stop_all_btn.setEnabled(True)
        self.status_label.setText("Recording and plotting in progress.")

    def handle_stop_clicked(self):
        errors = []

        if self.recorder is not None:
            _, err = self._stop_mpu6050(show_dialog=False)
            if err:
                errors.append(err)

            _, err = self._stop_adxl203(show_dialog=False)
            if err:
                errors.append(err)

        try:
            self.plot_runner.stop()
        except Exception as exc:
            errors.append(f"Plotter: {exc}")

        if errors:
            QMessageBox.warning(self, "Stop issues", "\n".join(errors))

        self.start_all_btn.setEnabled(True)
        self.stop_all_btn.setEnabled(False)
        if self.recorder is None:
            self.status_label.setText("Not connected.")
        else:
            self.status_label.setText("Recording stopped.")

    def closeEvent(self, event) -> None:
        if self.stop_all_btn.isEnabled():
            try:
                self.handle_stop_clicked()
            except Exception:
                pass
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
