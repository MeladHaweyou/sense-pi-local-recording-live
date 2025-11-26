"""Recorder tab for starting/stopping Raspberry Pi loggers."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from ...sensors.mpu6050 import MpuSample


@dataclass
class MpuGuiConfig:
    enabled: bool
    rate_hz: float
    sensors: str
    channels: str
    include_temp: bool
    stream_every: int


class _StopStreaming(Exception):
    """Internal exception to break out of streaming loops."""


class RecorderTab(QWidget):
    """
    Recorder tab for starting/stopping Raspberry Pi loggers.

    It emits parsed sample objects to other tabs (e.g. Signals and FFT).
    """

    #: Emitted for every parsed sample object (MpuSample, generic LiveSample, ...).
    sample_received = Signal(object)
    streaming_started = Signal()
    streaming_stopped = Signal()
    error_reported = Signal(str)
    rate_updated = Signal(str, float)

    def __init__(
        self,
        host_inventory: HostInventory | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._host_inventory = host_inventory or HostInventory()

        self._hosts: Dict[str, Dict[str, object]] = {}
        self._pi_recorder: Optional[PiRecorder] = None

        self._mpu_thread: Optional[threading.Thread] = None
        self._stop_flags: Dict[str, threading.Event] = {
            "mpu6050": threading.Event(),
        }
        self._rate_controllers: Dict[str, RateController] = {
            "mpu6050": RateController(window_size=500, default_hz=0.0),
        }
        self._recording_mode: bool = False

        self._build_ui()
        self._load_hosts()

        self.error_reported.connect(self._show_error)
        self.rate_updated.connect(self._on_rate_updated)

    # --------------------------------------------------------------- UI setup
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Host selection
        host_group = QGroupBox("Raspberry Pi host", self)
        host_form = QFormLayout(host_group)

        self.host_combo = QComboBox(host_group)
        host_form.addRow("Host:", self.host_combo)

        self.host_status_label = QLabel("No hosts configured.", host_group)
        host_form.addRow("Status:", self.host_status_label)

        layout.addWidget(host_group)

        # MPU6050 settings
        mpu_group = QGroupBox("MPU6050 settings", self)
        mpu_layout = QHBoxLayout(mpu_group)

        self.mpu_enable_chk = QCheckBox("Enable MPU6050", mpu_group)
        self.mpu_enable_chk.setChecked(True)
        mpu_layout.addWidget(self.mpu_enable_chk)

        mpu_layout.addWidget(QLabel("Rate (Hz):", mpu_group))
        self.mpu_rate_spin = QSpinBox(mpu_group)
        self.mpu_rate_spin.setRange(4, 1000)
        self.mpu_rate_spin.setValue(100)
        mpu_layout.addWidget(self.mpu_rate_spin)

        mpu_layout.addWidget(QLabel("Sensors:", mpu_group))
        self.mpu_sensors_edit = QLineEdit("1,2,3", mpu_group)
        self.mpu_sensors_edit.setToolTip("Comma-separated sensor IDs (1..3)")
        mpu_layout.addWidget(self.mpu_sensors_edit)

        mpu_layout.addWidget(QLabel("Channels:", mpu_group))
        self.mpu_channels_combo = QComboBox(mpu_group)
        self.mpu_channels_combo.addItem("Default (AX, AY, GZ)", userData="default")
        self.mpu_channels_combo.addItem("Accel only (AX, AY, AZ)", userData="acc")
        self.mpu_channels_combo.addItem("Gyro only (GX, GY, GZ)", userData="gyro")
        self.mpu_channels_combo.addItem("Both (acc + gyro)", userData="both")
        mpu_layout.addWidget(self.mpu_channels_combo)

        self.mpu_temp_chk = QCheckBox("Include temperature", mpu_group)
        self.mpu_temp_chk.setChecked(False)
        mpu_layout.addWidget(self.mpu_temp_chk)

        mpu_layout.addWidget(QLabel("Stream every:", mpu_group))
        self.mpu_stream_every_spin = QSpinBox(mpu_group)
        self.mpu_stream_every_spin.setRange(1, 1000)
        self.mpu_stream_every_spin.setValue(1)
        self.mpu_stream_every_spin.setToolTip(
            "Send every N-th sample over SSH (recording mode can use a larger value)."
        )
        mpu_layout.addWidget(self.mpu_stream_every_spin)

        layout.addWidget(mpu_group)

        # Status + rate
        self.overall_status = QLabel("Idle.", self)
        layout.addWidget(self.overall_status)

        self.mpu_rate_label = QLabel("MPU6050 rate: --", self)
        layout.addWidget(self.mpu_rate_label)

        # Hidden start/stop buttons (driven programmatically by MainWindow)
        button_box = QGroupBox(self)
        button_box.setVisible(False)
        btn_row = QHBoxLayout(button_box)
        self.start_btn = QPushButton("Start streaming", button_box)
        self.stop_btn = QPushButton("Stop", button_box)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        button_box.setLayout(btn_row)
        layout.addWidget(button_box)

        # Signal wiring
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.stop_btn.clicked.connect(self._on_stop_clicked)

    def _load_hosts(self) -> None:
        """Populate the host combo from config/hosts.yaml."""
        try:
            inventory = self._host_inventory.load()
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
            base_path = Path(entry.get("base_path", "/home/verwalter/sensor"))

            host = Host(
                name=name,
                host=host_addr,
                user=user,
                password=password,
                port=port,
            )
            self._hosts[name] = {"host": host, "base_path": base_path}
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

        host_entry = self._hosts[name]
        host = host_entry["host"]
        base_path = host_entry["base_path"]
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

    # --------------------------------------------------------------- slots
    @Slot()
    def _on_start_clicked(self) -> None:
        try:
            self.start_live_stream(recording=False)
        except Exception as exc:
            self.error_reported.emit(str(exc))

    @Slot()
    def _on_stop_clicked(self) -> None:
        self.stop_live_stream()

    def start_live_stream(self, recording: bool) -> None:
        """
        Called by MainWindow when the live stream should start.

        Uses the current GUI configuration and forwards `recording` down to
        the Pi logger.
        """
        self._recording_mode = bool(recording)

        mpu_cfg = self.current_mpu_gui_config()

        if not mpu_cfg.enabled:
            raise RuntimeError("Enable the MPU6050 sensor to start streaming.")

        recorder = self._ensure_recorder()

        if self._mpu_thread is not None:
            raise RuntimeError("MPU6050 streaming is already running.")

        mpu_args: list[str] = ["--rate", f"{mpu_cfg.rate_hz:.3f}"]
        mpu_args.extend(["--sensors", mpu_cfg.sensors])
        mpu_args.extend(["--channels", mpu_cfg.channels])
        if mpu_cfg.include_temp:
            mpu_args.append("--temp")

        stream_every = mpu_cfg.stream_every
        if recording:
            # In recording mode we can decimate the live stream slightly.
            stream_every = max(stream_every, 5)
        mpu_args.extend(["--stream-every", str(stream_every)])

        self._start_stream(
            recorder,
            sensor_type="mpu6050",
            extra_args=" ".join(mpu_args),
        )

    def stop_live_stream(self) -> None:
        """Called by MainWindow when the Signals tab requests stop."""

        self._stop_stream()

    def _stop_stream(self) -> None:
        # Signal the worker thread to stop
        self._stop_flags["mpu6050"].set()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.overall_status.setText("Stopping stream.")
        self.streaming_stopped.emit()

        self.mpu_rate_label.setText("MPU6050 rate: --")

        # Close SSH connection
        if self._pi_recorder is not None:
            try:
                self._pi_recorder.close()
            except Exception:
                pass
            self._pi_recorder = None
            self.host_status_label.setText("Disconnected.")

    def _start_stream(
        self,
        recorder: PiRecorder,
        sensor_type: str,
        extra_args: str,
    ) -> None:
        if sensor_type != "mpu6050":
            raise ValueError(
                f"RecorderTab only supports 'mpu6050' streams, got {sensor_type!r}"
            )

        parser = select_parser(sensor_type)
        stop_event = self._stop_flags[sensor_type]
        stop_event.clear()

        def _stderr_callback(line: str) -> None:
            self.error_reported.emit(f"{sensor_type} stderr: {line}")

        def _iter_lines():
            return recorder.stream_mpu6050(
                extra_args=extra_args,
                recording=self._recording_mode,
                on_stderr=_stderr_callback,
            )

        def _worker() -> None:
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

                if not stop_event.is_set():
                    self.error_reported.emit(
                        f"Stream for {sensor_type} ended unexpectedly (remote process exited)."
                    )

            except _StopStreaming:
                pass
            except Exception as exc:
                self.error_reported.emit(f"Stream error ({sensor_type}): {exc}")
            finally:
                self._mpu_thread = None

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.overall_status.setText("Streaming.")
        self.streaming_started.emit()

        t = threading.Thread(target=_worker, daemon=True)
        self._mpu_thread = t
        t.start()

    def _sample_time_seconds(self, sample: object) -> Optional[float]:
        if isinstance(sample, MpuSample):
            if sample.t_s is not None:
                return float(sample.t_s)
            return sample.timestamp_ns * 1e-9
        return None

    @Slot(str)
    def _show_error(self, message: str) -> None:
        # Always reflect the latest remote message in the status bar
        self.overall_status.setText(message)

    @Slot(str, float)
    def _on_rate_updated(self, sensor_type: str, hz: float) -> None:
        if sensor_type == "mpu6050":
            self.mpu_rate_label.setText(f"MPU6050 rate: {hz:.1f} Hz")
