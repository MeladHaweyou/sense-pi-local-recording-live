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

from ...analysis.rate import RateController
from ...config.app_config import HostInventory
from ...core.live_stream import select_parser, stream_lines
from ...remote.pi_recorder import PiRecorder
from ...remote.ssh_client import Host
from ...sensors.adxl203_ads1115 import AdxlSample
from ...sensors.mpu6050 import MpuSample


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

    # Emitted on connection / streaming errors
    error_reported = Signal(str)
    rate_updated = Signal(str, float)

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
        self._rate_controllers: Dict[str, RateController] = {
            "mpu6050": RateController(window_size=500, default_hz=0.0),
            "adxl203_ads1115": RateController(window_size=500, default_hz=0.0),
        }

        self._build_ui()
        self._load_hosts()

        self.error_reported.connect(self._show_error)
        self.rate_updated.connect(self._on_rate_updated)

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

        self.mpu_rate_label = QLabel("MPU6050 rate: --")
        self.adxl_rate_label = QLabel("ADXL203 rate: --")
        layout.addWidget(self.mpu_rate_label)
        layout.addWidget(self.adxl_rate_label)

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
            password = entry.get("password")
            port = int(entry.get("port", 22))
            base_path = Path(
                entry.get("base_path", "/home/pi/raspberrypi_scripts")
            )

            host = Host(
                name=name,
                host=host_addr,
                user=user,
                password=password,
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

        self.mpu_rate_label.setText("MPU6050 rate: --")
        self.adxl_rate_label.setText("ADXL203 rate: --")

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
                rc = self._rate_controllers[sensor_type]
                rc.reset()

                def _callback(sample: object) -> None:
                    if stop_event.is_set():
                        raise _StopStreaming()
                    t = self._sample_time_seconds(sample)
                    if t is not None:
                        rc.add_sample_time(t)
                        self.rate_updated.emit(sensor_type, rc.estimated_hz)
                    self.sample_received.emit(sample)

                stream_lines(lines, parser, _callback)
            except _StopStreaming:
                # Graceful stop requested
                pass
            except Exception as exc:
                self.error_reported.emit(
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

    def _sample_time_seconds(self, sample: object) -> Optional[float]:
        if isinstance(sample, MpuSample):
            if sample.t_s is not None:
                return float(sample.t_s)
            return sample.timestamp_ns * 1e-9
        if isinstance(sample, AdxlSample):
            return sample.timestamp_ns * 1e-9
        return None

    @Slot(str)
    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "SensePi Error", message)
        self.overall_status.setText(f"Error: {message}")

    @Slot(str, float)
    def _on_rate_updated(self, sensor: str, hz: float) -> None:
        text = f"{hz:.1f} Hz"
        if sensor == "mpu6050":
            self.mpu_rate_label.setText(f"MPU6050 rate: {text}")
        elif sensor == "adxl203_ads1115":
            self.adxl_rate_label.setText(f"ADXL203 rate: {text}")
