"""Recorder tab for starting/stopping Raspberry Pi loggers."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, Optional, Tuple

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...config.app_config import HostInventory
from ...core.live_stream import select_parser, stream_lines
from ...remote.pi_recorder import PiRecorder
from ...remote.ssh_client import Host


class _StopStreaming(Exception):
    """Internal exception to break out of streaming loops."""


class RecorderTab(QWidget):
    """
    Tab that manages SSH connections to Raspberry Pi loggers and
    exposes a sample stream to other tabs via Qt signals.
    """

    # Emitted for every parsed sample object (MpuSample, AdxlSample, ...)
    sample_received = Signal(object)

    # Emitted when streaming starts or stops (for UI coordination)
    streaming_started = Signal()
    streaming_stopped = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._hosts: Dict[str, Tuple[Host, Path]] = {}
        self._pi_recorder: Optional[PiRecorder] = None

        self._mpu_thread: Optional[threading.Thread] = None
        self._adxl_thread: Optional[threading.Thread] = None
        self._stop_flags = {
            "mpu6050": threading.Event(),
            "adxl203_ads1115": threading.Event(),
        }

        self._build_ui()
        self._load_hosts()

    # --------------------------------------------------------------- UI setup
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Host selection --------------------------------------------------------
        host_group = QGroupBox("Raspberry Pi host")
        host_form = QFormLayout(host_group)

        self.host_combo = QComboBox()
        host_form.addRow("Host:", self.host_combo)

        self.host_status_label = QLabel("No hosts configured.")
        host_form.addRow("Status:", self.host_status_label)

        layout.addWidget(host_group)

        # Sensor streaming controls --------------------------------------------
        sensor_group = QGroupBox("Sensor streaming")
        sensor_form = QFormLayout(sensor_group)

        self.mpu_check = QCheckBox("Stream MPU6050")
        self.mpu_args_edit = QLineEdit()
        self.mpu_args_edit.setPlaceholderText(
            "--rate 200 --channels default --stream-fields ax,ay,gz"
        )
        sensor_form.addRow(self.mpu_check)
        sensor_form.addRow("MPU6050 extra args:", self.mpu_args_edit)

        self.adxl_check = QCheckBox("Stream ADXL203/ADS1115")
        self.adxl_args_edit = QLineEdit()
        self.adxl_args_edit.setPlaceholderText(
            "--rate 100 --channels both --stream-fields x_lp,y_lp"
        )
        sensor_form.addRow(self.adxl_check)
        sensor_form.addRow("ADXL extra args:", self.adxl_args_edit)

        # Start/stop buttons
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start streaming")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        sensor_form.addRow(btn_row)

        layout.addWidget(sensor_group)

        # Overall status
        self.overall_status = QLabel("Idle.")
        layout.addWidget(self.overall_status)

        # Wiring
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.stop_btn.clicked.connect(self._on_stop_clicked)

    def _load_hosts(self) -> None:
        """Populate the host combo from config/hosts.yaml."""
        try:
            inventory = HostInventory().load()
        except Exception as exc:
            self.host_status_label.setText(f"Error loading hosts.yaml: {exc}")
            return

        for entry in inventory.get("pis", []):
            name = entry.get("name")
            if not name:
                continue
            host_addr = entry.get("host", "raspberrypi.local")
            user = entry.get("user", "pi")
            ssh_key = entry.get("ssh_key")
            port = int(entry.get("port", 22))
            base_path = Path(
                entry.get("base_path", "/home/pi/raspberrypi_scripts")
            )

            if ssh_key:
                ssh_key = str(Path(ssh_key).expanduser())

            host = Host(
                name=name,
                host=host_addr,
                user=user,
                ssh_key=ssh_key,
                port=port,
            )
            self._hosts[name] = (host, base_path)
            self.host_combo.addItem(name)

        if self._hosts:
            self.host_status_label.setText("Ready.")
        else:
            self.host_status_label.setText(
                "No hosts configured in hosts.yaml (key 'pis')."
            )

    # --------------------------------------------------------------- helpers
    def _ensure_recorder(self) -> PiRecorder:
        if self._pi_recorder is not None:
            return self._pi_recorder

        name = self.host_combo.currentText()
        if not name or name not in self._hosts:
            raise RuntimeError("No Raspberry Pi host selected.")

        host, base_path = self._hosts[name]
        recorder = PiRecorder(host, base_path)
        recorder.connect()

        self._pi_recorder = recorder
        self.host_status_label.setText(f"Connected to {name}")
        return recorder

    # --------------------------------------------------------------- slots
    @Slot()
    def _on_start_clicked(self) -> None:
        if not (self.mpu_check.isChecked() or self.adxl_check.isChecked()):
            QMessageBox.information(
                self,
                "No sensors selected",
                "Select at least one sensor to stream.",
            )
            return

        try:
            recorder = self._ensure_recorder()
        except Exception as exc:
            QMessageBox.critical(self, "SSH error", str(exc))
            return

        started_any = False

        if self.mpu_check.isChecked() and self._mpu_thread is None:
            self._start_stream(
                recorder,
                sensor_type="mpu6050",
                extra_args=self.mpu_args_edit.text().strip(),
            )
            started_any = True

        if self.adxl_check.isChecked() and self._adxl_thread is None:
            self._start_stream(
                recorder,
                sensor_type="adxl203_ads1115",
                extra_args=self.adxl_args_edit.text().strip(),
            )
            started_any = True

        if not started_any:
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.overall_status.setText("Streaming...")
        self.streaming_started.emit()

    @Slot()
    def _on_stop_clicked(self) -> None:
        # Tell worker threads to stop
        self._stop_flags["mpu6050"].set()
        self._stop_flags["adxl203_ads1115"].set()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.overall_status.setText("Stopping streams...")
        self.streaming_stopped.emit()

        # Close SSH connection (remote processes will see broken pipes)
        if self._pi_recorder is not None:
            try:
                self._pi_recorder.close()
            except Exception:
                pass
            self._pi_recorder = None
            self.host_status_label.setText("Disconnected.")

    # --------------------------------------------------------------- streaming workers
    def _start_stream(
        self, recorder: PiRecorder, sensor_type: str, extra_args: str
    ) -> None:
        parser = select_parser(sensor_type)
        stop_event = self._stop_flags[sensor_type]
        stop_event.clear()

        if sensor_type == "mpu6050":
            def _iter_lines():
                return recorder.stream_mpu6050(extra_args=extra_args)
        else:
            def _iter_lines():
                return recorder.stream_adxl203(extra_args=extra_args)

        def _worker():
            try:
                lines = _iter_lines()

                def _callback(sample: object) -> None:
                    if stop_event.is_set():
                        raise _StopStreaming()
                    self.sample_received.emit(sample)

                stream_lines(lines, parser, _callback)
            except _StopStreaming:
                # Graceful stop requested
                pass
            except Exception as exc:
                self.overall_status.setText(
                    f"Stream error ({sensor_type}): {exc}"
                )
            finally:
                if sensor_type == "mpu6050":
                    self._mpu_thread = None
                else:
                    self._adxl_thread = None

        t = threading.Thread(target=_worker, daemon=True)
        if sensor_type == "mpu6050":
            self._mpu_thread = t
        else:
            self._adxl_thread = t
        t.start()
