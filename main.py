import sys
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

from ssh_client import SSHConfig
from pi_recorder import PiRecorder


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Sense-Pi Recorder")
        self.recorder: Optional[PiRecorder] = None

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

        self.setCentralWidget(central)

        # Signals
        self.connect_btn.clicked.connect(self.on_connect_clicked)
        self.disconnect_btn.clicked.connect(self.on_disconnect_clicked)

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
    def _ensure_recorder(self) -> bool:
        if self.recorder is None:
            QMessageBox.information(
                self,
                "Not connected",
                "Please connect to the Raspberry Pi first.",
            )
            return False
        return True

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

    @Slot()
    def on_mpu_start_clicked(self):
        if not self._ensure_recorder():
            return

        extra_args = self.mpu_extra_args_edit.text().strip()
        try:
            pid = self.recorder.start_mpu6050(extra_args=extra_args)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Start error",
                f"Failed to start MPU6050 logger:\n{exc}",
            )
            return

        self.mpu_status_label.setText(f"Running (PID {pid})")
        self.mpu_start_btn.setEnabled(False)
        self.mpu_stop_btn.setEnabled(True)

    @Slot()
    def on_mpu_stop_clicked(self):
        if not self._ensure_recorder():
            return

        try:
            stopped = self.recorder.stop_mpu6050()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Stop error",
                f"Error stopping MPU6050 logger:\n{exc}",
            )
            return

        if stopped:
            self.mpu_status_label.setText("Stopped")
        else:
            self.mpu_status_label.setText("Was not running")

        self.mpu_start_btn.setEnabled(True)
        self.mpu_stop_btn.setEnabled(False)

    @Slot()
    def on_adxl_start_clicked(self):
        if not self._ensure_recorder():
            return

        extra_args = self.adxl_extra_args_edit.text().strip()
        try:
            pid = self.recorder.start_adxl203(extra_args=extra_args)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Start error",
                f"Failed to start ADXL203 logger:\n{exc}",
            )
            return

        self.adxl_status_label.setText(f"Running (PID {pid})")
        self.adxl_start_btn.setEnabled(False)
        self.adxl_stop_btn.setEnabled(True)

    @Slot()
    def on_adxl_stop_clicked(self):
        if not self._ensure_recorder():
            return

        try:
            stopped = self.recorder.stop_adxl203()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Stop error",
                f"Error stopping ADXL203 logger:\n{exc}",
            )
            return

        if stopped:
            self.adxl_status_label.setText("Stopped")
        else:
            self.adxl_status_label.setText("Was not running")

        self.adxl_start_btn.setEnabled(True)
        self.adxl_stop_btn.setEnabled(False)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
