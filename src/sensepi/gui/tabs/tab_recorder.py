"""Recorder tab for starting/stopping Raspberry Pi loggers."""

from __future__ import annotations

import threading
from dataclasses import dataclass
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
    QSpinBox,
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


@dataclass
class MpuGuiConfig:
    enabled: bool
    rate_hz: float
    sensors: str
    channels: str
    include_temp: bool
    stream_every: int


@dataclass
class AdxlGuiConfig:
    enabled: bool
    rate_hz: float
    channels: str
    stream_every: int


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

        self._recording_mode: bool = False

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

        # Sensor configuration -------------------------------------------------
        mpu_group = QGroupBox("MPU6050 settings")
        mpu_layout = QHBoxLayout()
        mpu_group.setLayout(mpu_layout)

        self.mpu_enable_chk = QCheckBox("Enable MPU6050")
        self.mpu_enable_chk.setChecked(True)
        mpu_layout.addWidget(self.mpu_enable_chk)

        mpu_layout.addWidget(QLabel("Rate (Hz):"))
        self.mpu_rate_spin = QSpinBox()
        self.mpu_rate_spin.setRange(4, 1000)
        self.mpu_rate_spin.setValue(100)
        mpu_layout.addWidget(self.mpu_rate_spin)

        mpu_layout.addWidget(QLabel("Sensors:"))
        self.mpu_sensors_edit = QLineEdit("1,2,3")
        self.mpu_sensors_edit.setToolTip("Comma-separated sensor IDs (1..3)")
        mpu_layout.addWidget(self.mpu_sensors_edit)

        mpu_layout.addWidget(QLabel("Channels:"))
        self.mpu_channels_combo = QComboBox()
        self.mpu_channels_combo.addItem("Default (AX, AY, GZ)", userData="default")
        self.mpu_channels_combo.addItem("Accel only (AX, AY, AZ)", userData="acc")
        self.mpu_channels_combo.addItem("Gyro only (GX, GY, GZ)", userData="gyro")
        self.mpu_channels_combo.addItem("Both (acc + gyro)", userData="both")
        mpu_layout.addWidget(self.mpu_channels_combo)

        self.mpu_temp_chk = QCheckBox("Include temperature")
        self.mpu_temp_chk.setChecked(False)
        mpu_layout.addWidget(self.mpu_temp_chk)

        mpu_layout.addWidget(QLabel("Stream every:"))
        self.mpu_stream_every_spin = QSpinBox()
        self.mpu_stream_every_spin.setRange(1, 1000)
        self.mpu_stream_every_spin.setValue(1)
        self.mpu_stream_every_spin.setToolTip(
            "Send every N-th sample over SSH (recording mode can use a larger value)."
        )
        mpu_layout.addWidget(self.mpu_stream_every_spin)

        layout.addWidget(mpu_group)

        adxl_group = QGroupBox("ADXL203/ADS1115 settings")
        adxl_layout = QHBoxLayout()
        adxl_group.setLayout(adxl_layout)

        self.adxl_enable_chk = QCheckBox("Enable ADXL203/ADS1115")
        self.adxl_enable_chk.setChecked(False)
        adxl_layout.addWidget(self.adxl_enable_chk)

        adxl_layout.addWidget(QLabel("Rate (Hz):"))
        self.adxl_rate_spin = QSpinBox()
        self.adxl_rate_spin.setRange(4, 1000)
        self.adxl_rate_spin.setValue(100)
        adxl_layout.addWidget(self.adxl_rate_spin)

        adxl_layout.addWidget(QLabel("Channels:"))
        self.adxl_channels_combo = QComboBox()
        self.adxl_channels_combo.addItem("X and Y", userData="both")
        self.adxl_channels_combo.addItem("X only", userData="x")
        self.adxl_channels_combo.addItem("Y only", userData="y")
        adxl_layout.addWidget(self.adxl_channels_combo)

        adxl_layout.addWidget(QLabel("Stream every:"))
        self.adxl_stream_every_spin = QSpinBox()
        self.adxl_stream_every_spin.setRange(1, 1000)
        self.adxl_stream_every_spin.setValue(1)
        adxl_layout.addWidget(self.adxl_stream_every_spin)

        layout.addWidget(adxl_group)

        # Overall status
        self.overall_status = QLabel("Idle.")
        layout.addWidget(self.overall_status)

        self.mpu_rate_label = QLabel("MPU6050 rate: --")
        self.adxl_rate_label = QLabel("ADXL203 rate: --")
        layout.addWidget(self.mpu_rate_label)
        layout.addWidget(self.adxl_rate_label)

        # Hidden legacy controls (retained for programmatic access)
        hidden_group = QGroupBox()
        hidden_group.setVisible(False)
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start streaming")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        hidden_group.setLayout(btn_row)
        layout.addWidget(hidden_group)

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
                entry.get("base_path", "/home/verwalter/sensor")
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

    def current_mpu_gui_config(self) -> MpuGuiConfig:
        return MpuGuiConfig(
            enabled=self.mpu_enable_chk.isChecked(),
            rate_hz=float(self.mpu_rate_spin.value()),
            sensors=self.mpu_sensors_edit.text().strip() or "1,2,3",
            channels=self.mpu_channels_combo.currentData(),
            include_temp=self.mpu_temp_chk.isChecked(),
            stream_every=max(1, int(self.mpu_stream_every_spin.value())),
        )

    def current_adxl_gui_config(self) -> AdxlGuiConfig:
        return AdxlGuiConfig(
            enabled=self.adxl_enable_chk.isChecked(),
            rate_hz=float(self.adxl_rate_spin.value()),
            channels=self.adxl_channels_combo.currentData(),
            stream_every=max(1, int(self.adxl_stream_every_spin.value())),
        )

    # --------------------------------------------------------------- slots
    @Slot()
    def _on_start_clicked(self) -> None:
        try:
            self.start_live_stream(recording=False)
        except Exception as exc:
            QMessageBox.critical(self, "SSH error", str(exc))

    @Slot()
    def _on_stop_clicked(self) -> None:
        self.stop_live_stream()

    def start_live_stream(self, recording: bool) -> None:
        """
        Called by MainWindow when the Signals tab requests streaming.

        Uses current GUI configuration (host + sensor settings) and passes a
        `recording` flag down to the internal _start_stream logic.
        """

        self._recording_mode = bool(recording)

        mpu_cfg = self.current_mpu_gui_config()
        adxl_cfg = self.current_adxl_gui_config()

        if not (mpu_cfg.enabled or adxl_cfg.enabled):
            raise RuntimeError("Select at least one sensor to stream.")

        recorder = self._ensure_recorder()
        started_any = False

        if mpu_cfg.enabled and self._mpu_thread is None:
            mpu_args: list[str] = ["--rate", f"{mpu_cfg.rate_hz:.3f}"]
            mpu_args.extend(["--sensors", mpu_cfg.sensors])
            mpu_args.extend(["--channels", mpu_cfg.channels])
            if mpu_cfg.include_temp:
                mpu_args.append("--temp")

            stream_every = mpu_cfg.stream_every
            if self._recording_mode:
                stream_every = max(stream_every, 5)
            mpu_args.extend(["--stream-every", str(stream_every)])

            self._start_stream(
                recorder,
                sensor_type="mpu6050",
                extra_args=" ".join(mpu_args),
            )
            started_any = True

        if adxl_cfg.enabled and self._adxl_thread is None:
            adxl_args: list[str] = ["--rate", f"{adxl_cfg.rate_hz:.3f}"]
            adxl_args.extend(["--channels", adxl_cfg.channels])
            adxl_stream_every = adxl_cfg.stream_every
            if self._recording_mode:
                adxl_stream_every = max(adxl_stream_every, 5)
            adxl_args.extend(["--stream-every", str(adxl_stream_every)])

            self._start_stream(
                recorder,
                sensor_type="adxl203_ads1115",
                extra_args=" ".join(adxl_args),
            )
            started_any = True

        if not started_any:
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.overall_status.setText("Streaming...")
        self.streaming_started.emit()

    def stop_live_stream(self) -> None:
        """Called by MainWindow when the Signals tab requests stop."""

        self._stop_stream()

    def _stop_stream(self) -> None:
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

        def _stderr_callback(line: str) -> None:
            # Forward stderr lines to the GUI
            self.error_reported.emit(f"{sensor_type} stderr: {line}")

        if sensor_type == "mpu6050":
            def _iter_lines():
                return recorder.stream_mpu6050(
                    extra_args=extra_args,
                    recording=self._recording_mode,
                    on_stderr=_stderr_callback,
                )
        else:
            def _iter_lines():
                return recorder.stream_adxl203(
                    extra_args=extra_args,
                    recording=self._recording_mode,
                    on_stderr=_stderr_callback,
                )

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

                # When stream_lines returns normally, stdout closed.
                stream_lines(lines, parser, _callback)

                # If we get here without a StopStreaming and we didn't request a stop,
                # the remote process likely exited early (error or normal exit).
                if not stop_event.is_set():
                    self.error_reported.emit(
                        f"Stream for {sensor_type} ended unexpectedly (remote process exited)."
                    )

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
