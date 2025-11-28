"""Recorder tab for starting/stopping Raspberry Pi loggers."""

from __future__ import annotations

import logging
import queue
from dataclasses import dataclass
from pathlib import Path
import shlex
from typing import Dict, Iterable, Mapping, Optional

from PySide6.QtCore import QMetaObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
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

from ..widgets import AcquisitionSettings, CollapsibleSection
from ...analysis.rate import RateController
from ...config.app_config import HostConfig, HostInventory, SensorDefaults
from ...core.live_stream import select_parser
from ...data import BufferConfig, StreamingDataBuffer
from ...remote.pi_recorder import PiRecorder
from ...remote.sensor_ingest_worker import SensorIngestWorker
from ...remote.ssh_client import Host
from ...sensors.mpu6050 import MpuSample


logger = logging.getLogger(__name__)


@dataclass
class MpuGuiConfig:
    enabled: bool = True
    rate_hz: float = 100.0
    sensors: str = "1,2,3"
    channels: str = "default"
    include_temp: bool = False
    limit_duration: bool = False
    duration_s: float = 0.0


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
    recording_started = Signal()
    recording_stopped = Signal()
    recording_error = Signal(str)

    def __init__(
        self,
        host_inventory: HostInventory | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._host_inventory = host_inventory or HostInventory()
        self._sensor_defaults = SensorDefaults()

        self._hosts: Dict[str, Dict[str, object]] = {}
        self._pi_recorder: Optional[PiRecorder] = None

        self._ingest_thread: Optional[QThread] = None
        self._ingest_worker: Optional[SensorIngestWorker] = None
        self._rate_controllers: Dict[str, RateController] = {
            "mpu6050": RateController(window_size=500, default_hz=0.0),
        }
        self._recording_mode: bool = False
        self._stop_requested: bool = False
        self._ingest_batch_size = 50
        self._ingest_max_latency_ms = 100
        self._ingest_had_error = False
        self._last_session_name: str = ""
        self._data_buffer = StreamingDataBuffer(
            BufferConfig(
                max_seconds=6.0,
                sample_rate_hz=self._get_default_mpu_sample_rate(),
            )
        )
        self._active_stream: Iterable[str] | None = None
        self._sample_queue: queue.Queue[object] = queue.Queue(maxsize=10_000)

        self._build_ui()
        self._load_hosts()
        self._update_recording_rate_from_defaults()

        self.error_reported.connect(self._show_error)
        self.rate_updated.connect(self._on_rate_updated)

    # --------------------------------------------------------------- UI setup
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Host selection
        self.host_group = QGroupBox("Raspberry Pi host", self)
        host_form = QFormLayout(self.host_group)

        self.host_combo = QComboBox(self.host_group)
        host_form.addRow("Host:", self.host_combo)

        self.host_status_label = QLabel("No hosts configured.", self.host_group)
        host_form.addRow("Status:", self.host_status_label)

        host_section = CollapsibleSection("Raspberry Pi host", self)
        host_layout = QVBoxLayout()
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.addWidget(self.host_group)
        host_section.setContentLayout(host_layout)
        layout.addWidget(host_section)

        # MPU6050 settings
        self.mpu_group = QGroupBox("MPU6050 settings", self)
        mpu_layout = QHBoxLayout(self.mpu_group)

        self.mpu_enable_chk = QCheckBox("Enable MPU6050", self.mpu_group)
        self.mpu_enable_chk.setChecked(True)
        mpu_layout.addWidget(self.mpu_enable_chk)

        # Recording/sample rate is read from sensors.yaml and shown read-only
        mpu_layout.addWidget(QLabel("Recording rate [Hz]:", self.mpu_group))
        self.mpu_recording_rate_label = QLabel("—", self.mpu_group)
        self.mpu_recording_rate_label.setToolTip(
            "Sample rate configured in Settings → Sensor defaults. "
            "This is the rate used for recording on the Pi."
        )
        mpu_layout.addWidget(self.mpu_recording_rate_label)

        mpu_layout.addWidget(QLabel("Sensors:", self.mpu_group))
        self.mpu_sensors_edit = QLineEdit("1,2,3", self.mpu_group)
        self.mpu_sensors_edit.setToolTip("Comma-separated sensor IDs (1..3)")
        mpu_layout.addWidget(self.mpu_sensors_edit)

        mpu_layout.addWidget(QLabel("Channels:", self.mpu_group))
        self.mpu_channels_combo = QComboBox(self.mpu_group)
        self.mpu_channels_combo.addItem("Default (AX, AY, GZ)", userData="default")
        self.mpu_channels_combo.addItem("Accel only (AX, AY, AZ)", userData="acc")
        self.mpu_channels_combo.addItem("Gyro only (GX, GY, GZ)", userData="gyro")
        self.mpu_channels_combo.addItem("Both (acc + gyro)", userData="both")
        self.mpu_channels_combo.setToolTip(
            "Select which axes are streamed from the MPU6050.\n"
            "Default (AX, AY, GZ): streams only AX, AY and GZ (no AZ, GX, GY).\n"
            "Both (acc + gyro): streams all six axes (AX, AY, AZ, GX, GY, GZ), "
            "so the Signals page can show every axis."
        )
        mpu_layout.addWidget(self.mpu_channels_combo)

        self.mpu_temp_chk = QCheckBox("Include temperature", self.mpu_group)
        self.mpu_temp_chk.setChecked(False)
        mpu_layout.addWidget(self.mpu_temp_chk)

        stream_row = QHBoxLayout()
        stream_row.addWidget(QLabel("Target GUI stream [Hz]:", self.mpu_group))
        self.mpu_target_stream_rate = QDoubleSpinBox(self.mpu_group)
        self.mpu_target_stream_rate.setRange(1.0, 200.0)
        self.mpu_target_stream_rate.setDecimals(1)

        self.mpu_target_stream_rate.setSingleStep(0.5)
        self.mpu_target_stream_rate.setValue(25.0)
        self.mpu_target_stream_rate.setToolTip(
            "Desired rate of samples arriving in the GUI (after decimation). "
            "The logger's --stream-every is derived from this value."
        )
        stream_row.addWidget(self.mpu_target_stream_rate)

        self.mpu_manual_stream_every_chk = QCheckBox(
            "Manual stream every", self.mpu_group
        )
        self.mpu_manual_stream_every_chk.setToolTip(
            "Enable to override the derived decimation and pass an explicit "
            "--stream-every N to the Pi logger."
        )
        stream_row.addWidget(self.mpu_manual_stream_every_chk)

        self.mpu_stream_every_spin = QSpinBox(self.mpu_group)
        self.mpu_stream_every_spin.setRange(1, 1000)
        self.mpu_stream_every_spin.setSingleStep(1)
        self.mpu_stream_every_spin.setValue(5)
        self.mpu_stream_every_spin.setEnabled(False)
        self.mpu_stream_every_spin.setToolTip(
            "Number of samples skipped between streamed points. Only used when "
            "'Manual stream every' is enabled."
        )
        self.mpu_manual_stream_every_chk.toggled.connect(
            self.mpu_stream_every_spin.setEnabled
        )
        stream_row.addWidget(self.mpu_stream_every_spin)
        stream_row.addStretch(1)
        mpu_layout.addLayout(stream_row)

        duration_row = QHBoxLayout()
        self.mpu_limit_duration_chk = QCheckBox(
            "Limit duration (s):", self.mpu_group
        )
        self.mpu_duration_spin = QDoubleSpinBox(self.mpu_group)
        self.mpu_duration_spin.setRange(0.1, 3600.0)
        self.mpu_duration_spin.setDecimals(1)
        self.mpu_duration_spin.setSingleStep(1.0)
        self.mpu_duration_spin.setValue(10.0)
        self.mpu_duration_spin.setEnabled(False)
        self.mpu_limit_duration_chk.toggled.connect(
            self.mpu_duration_spin.setEnabled
        )
        duration_row.addWidget(self.mpu_limit_duration_chk)
        duration_row.addWidget(self.mpu_duration_spin)
        duration_row.addStretch(1)
        mpu_layout.addLayout(duration_row)

        mpu_section = CollapsibleSection("MPU6050 settings", self)
        mpu_container = QVBoxLayout()
        mpu_container.setContentsMargins(0, 0, 0, 0)
        mpu_container.addWidget(self.mpu_group)
        mpu_section.setContentLayout(mpu_container)
        mpu_section.setCollapsed(True)
        layout.addWidget(mpu_section)

        # Status + rate
        self.overall_status = QLabel("Idle.", self)
        layout.addWidget(self.overall_status)

        self.mpu_rate_label = QLabel("GUI stream rate: --", self)
        self.mpu_rate_label.setToolTip(
            "Estimated sample rate of data arriving in this GUI tab."
        )
        layout.addWidget(self.mpu_rate_label)

        layout.addStretch()

        # Hidden start/stop buttons (driven programmatically by MainWindow)
        button_box = QGroupBox(self)
        button_box.setVisible(False)
        btn_row = QHBoxLayout()
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

        entries = inventory.get("pis") or []
        self._apply_host_entries(entries, preserve_selection=False)

    def _apply_host_entries(
        self,
        host_entries: Iterable[Mapping[str, object]],
        *,
        preserve_selection: bool,
    ) -> None:
        previous = self.host_combo.currentText() if preserve_selection else None

        self._hosts.clear()
        self.host_combo.clear()

        for entry in host_entries:
            if not isinstance(entry, Mapping):
                logger.warning("Skipping invalid host entry (not a mapping): %r", entry)
                continue
            try:
                host_cfg = self._host_inventory.to_host_config(entry)
            except Exception as exc:
                logger.warning("Skipping invalid host entry %r: %s", entry, exc)
                continue

            host = Host(
                name=host_cfg.name,
                host=host_cfg.host,
                user=host_cfg.user,
                password=host_cfg.password,
                port=host_cfg.port,
            )
            self._hosts[host_cfg.name] = {
                "host": host,
                "config": host_cfg,
            }
            self.host_combo.addItem(host_cfg.name)

        if previous and previous in self._hosts:
            idx = self.host_combo.findText(previous)
            if idx >= 0:
                self.host_combo.setCurrentIndex(idx)
        elif self.host_combo.count():
            self.host_combo.setCurrentIndex(0)

        if self._hosts:
            self.host_status_label.setText("Ready.")
        else:
            self.host_status_label.setText(
                "No hosts configured. Add one in Settings → Raspberry Pi hosts."
            )

    # --------------------------------------------------------------- helpers
    def _ensure_recorder(self) -> PiRecorder:
        if self._pi_recorder is not None:
            return self._pi_recorder

        details = self.current_host_details()
        if details is None:
            raise RuntimeError("No Raspberry Pi host selected.")

        host, cfg = details
        recorder = PiRecorder(host, cfg.base_path)
        recorder.connect()

        self._pi_recorder = recorder
        self.host_status_label.setText(f"Connected to {host.name}")
        return recorder

    def current_host_details(self) -> tuple[Host, HostConfig] | None:
        """Return the active host credentials and config if available."""
        name = self.host_combo.currentText()
        if not name:
            return None
        entry = self._hosts.get(name)
        if not entry:
            return None
        host = entry.get("host")
        cfg = entry.get("config")
        if not isinstance(host, Host) or not isinstance(cfg, HostConfig):
            return None
        return host, cfg

    def current_remote_data_dir(self) -> Path | None:
        """Remote filesystem root used for recording on the selected Pi."""
        details = self.current_host_details()
        if details is None:
            return None
        _, cfg = details
        return cfg.data_dir

    def last_session_name(self) -> str:
        """Return the last session label requested by the user."""
        return self._last_session_name

    def _get_default_mpu_sample_rate(self) -> float:
        """Return the MPU6050 sample rate from sensors.yaml (Hz)."""
        try:
            config = self._sensor_defaults.load()
        except Exception:
            return 200.0
        mpu_cfg = dict(config.get("mpu6050", {}) or {})
        rate = mpu_cfg.get("sample_rate_hz", 200)
        try:
            return float(rate)
        except (TypeError, ValueError):
            return 200.0

    def _get_default_mpu_dlpf(self) -> int | None:
        """Return the MPU6050 DLPF setting from sensors.yaml."""
        try:
            config = self._sensor_defaults.load()
        except Exception:
            return 3
        mpu_cfg = dict(config.get("mpu6050", {}) or {})
        dlpf = mpu_cfg.get("dlpf")
        try:
            return int(dlpf)
        except (TypeError, ValueError):
            return None

    def _target_stream_rate_hz(self) -> float:
        widget = getattr(self, "mpu_target_stream_rate", None)
        if widget is None:
            return 0.0
        try:
            return float(widget.value())
        except (TypeError, ValueError):
            return 0.0

    def target_stream_rate_hz(self) -> float:
        """Expose the current GUI target stream rate for other tabs."""
        return float(self._target_stream_rate_hz())

    def _manual_stream_every_enabled(self) -> bool:
        chk = getattr(self, "mpu_manual_stream_every_chk", None)
        if chk is None:
            return False
        return chk.isChecked()

    def _manual_stream_every_value(self) -> int:
        spin = getattr(self, "mpu_stream_every_spin", None)
        if spin is None:
            return 1
        try:
            return max(1, int(spin.value()))
        except (TypeError, ValueError):
            return 1

    def compute_stream_every(
        self,
        sample_rate_hz: float | None,
        *,
        recording: bool | None = None,
        fallback_every: int | None = None,
    ) -> int:
        """
        Return the decimation factor (--stream-every) derived from the target GUI rate.

        ``sample_rate_hz`` is the Pi recording rate. When manual override is enabled,
        that value is ignored and the explicit spin-box value is returned instead.
        """

        rate = 0.0
        if sample_rate_hz is not None:
            try:
                rate = max(0.0, float(sample_rate_hz))
            except (TypeError, ValueError):
                rate = 0.0

        if self._manual_stream_every_enabled():
            stream_every = self._manual_stream_every_value()
        else:
            target = self._target_stream_rate_hz()
            stream_every = 1
            if rate > 0.0 and target > 0.0:
                stream_every = max(1, int(round(rate / target)))
            elif fallback_every is not None:
                try:
                    stream_every = max(1, int(fallback_every))
                except (TypeError, ValueError):
                    stream_every = 1

        if recording is None:
            recording = self._recording_mode
        if recording:
            # Keep GUI load manageable when recording at high rates.
            stream_every = max(stream_every, 5)
        return stream_every

    def request_coarser_streaming(self) -> None:
        """
        Respond to adaptive tuning by reducing the GUI stream rate target.

        Changes are applied to the spin boxes only; the next stream start will
        inherit the more conservative settings.
        """
        changed = self._adjust_stream_every(coarser=True)
        self._nudge_target_stream_rate(scale=0.8)
        if changed:
            spin = getattr(self, "mpu_stream_every_spin", None)
            value = spin.value() if spin is not None else "?"
            logger.info(
                "RecorderTab: requested coarser GUI stream (stream_every now %s)",
                value,
            )

    def request_finer_streaming(self) -> None:
        """
        Allow the adaptive controller to cautiously raise the GUI stream rate.
        """
        changed = self._adjust_stream_every(coarser=False)
        self._nudge_target_stream_rate(scale=1.1)
        if changed:
            spin = getattr(self, "mpu_stream_every_spin", None)
            value = spin.value() if spin is not None else "?"
            logger.info(
                "RecorderTab: requested finer GUI stream (stream_every now %s)",
                value,
            )

    def _adjust_stream_every(self, *, coarser: bool) -> bool:
        spin = getattr(self, "mpu_stream_every_spin", None)
        if spin is None:
            return False
        try:
            current = max(1, int(spin.value()))
        except (TypeError, ValueError):
            return False
        if coarser:
            new_value = min(spin.maximum(), max(current + 1, current * 2))
        else:
            new_value = max(spin.minimum(), max(1, current // 2))
        if new_value == current:
            return False
        spin.setValue(int(new_value))
        return True

    def _nudge_target_stream_rate(self, *, scale: float) -> bool:
        widget = getattr(self, "mpu_target_stream_rate", None)
        if widget is None:
            return False
        try:
            current = float(widget.value())
        except (TypeError, ValueError):
            return False
        minimum = float(widget.minimum()) if hasattr(widget, "minimum") else 1.0
        maximum = float(widget.maximum()) if hasattr(widget, "maximum") else max(1.0, current)
        new_value = max(minimum, min(maximum, current * scale))
        if abs(new_value - current) < 0.05:
            return False
        widget.setValue(float(new_value))
        return True

    def _update_recording_rate_from_defaults(self) -> None:
        rate = self._get_default_mpu_sample_rate()
        if hasattr(self, "mpu_recording_rate_label"):
            self.mpu_recording_rate_label.setText(f"{rate:.0f} Hz")

    def current_mpu_gui_config(self) -> MpuGuiConfig:
        return MpuGuiConfig(
            enabled=self.mpu_enable_chk.isChecked(),
            rate_hz=self._get_default_mpu_sample_rate(),
            sensors=self.mpu_sensors_edit.text().strip() or "1,2,3",
            channels=self.mpu_channels_combo.currentData(),
            include_temp=self.mpu_temp_chk.isChecked(),
            limit_duration=self.mpu_limit_duration_chk.isChecked(),
            duration_s=float(self.mpu_duration_spin.value())
            if self.mpu_limit_duration_chk.isChecked()
            else 0.0,
        )

    def _build_mpu_extra_args(
        self,
        acquisition: AcquisitionSettings | None = None,
        *,
        session_name: str | None = None,
    ) -> list[str]:
        """Construct CLI flags passed to ``mpu6050_multi_logger.py``.

        The logger always samples/records on the Pi at the configured
        ``--sample-rate-hz`` even if the GUI only consumes every N-th sample
        defined by ``--stream-every``. This helper keeps those pieces in sync
        so recording mode still captures every sample on-disk while the GUI
        receives a decimated stream that is less likely to overwhelm Qt.
        """

        args: list[str] = []

        rate = self._get_default_mpu_sample_rate()
        if acquisition is not None and acquisition.sample_rate_hz > 0:
            rate = float(acquisition.sample_rate_hz)
        if rate > 0:
            args += ["--sample-rate-hz", f"{int(rate)}"]

        sensors = self.mpu_sensors_edit.text().strip()
        if sensors:
            args += ["--sensors", sensors]

        channels = self.mpu_channels_combo.currentData() or "default"
        args += ["--channels", channels]

        if self.mpu_temp_chk.isChecked():
            args.append("--temp")

        dlpf = self._get_default_mpu_dlpf()
        if dlpf is not None:
            args += ["--dlpf", str(dlpf)]

        fallback_stream_every: int | None = None
        if acquisition is not None:
            try:
                fallback_stream_every = int(acquisition.stream_every)
            except (TypeError, ValueError):
                fallback_stream_every = None
        stream_every = self.compute_stream_every(
            rate,
            fallback_every=fallback_stream_every,
        )
        args += ["--stream-every", str(stream_every)]

        if self.mpu_limit_duration_chk.isChecked():
            duration_s = float(self.mpu_duration_spin.value())
            if duration_s > 0:
                args += ["--duration", f"{duration_s:.3f}"]

        if session_name:
            args += ["--session-name", session_name]

        return args

    # --------------------------------------------------------------- slots
    @Slot()
    def _on_start_clicked(self) -> None:
        try:
            self.start_live_stream(recording=False)
        except Exception as exc:
            self._emit_error(str(exc))

    @Slot()
    def _on_stop_clicked(self) -> None:
        self.stop_live_stream()

    def start_live_stream(
        self,
        recording: bool,
        acquisition: AcquisitionSettings | None = None,
        *,
        session_name: str | None = None,
    ) -> None:
        """
        Called by MainWindow when the live stream should start.

        Uses the current GUI configuration and forwards `recording` down to
        the Pi logger.
        """
        self._recording_mode = bool(recording)
        normalized_session = (session_name or "").strip()
        self._last_session_name = normalized_session

        mpu_cfg = self.current_mpu_gui_config()

        if not mpu_cfg.enabled:
            raise RuntimeError("Enable the MPU6050 sensor to start streaming.")

        recorder = self._ensure_recorder()

        if self._ingest_worker is not None:
            raise RuntimeError("MPU6050 streaming is already running.")

        mpu_args_list = self._build_mpu_extra_args(
            acquisition, session_name=normalized_session or None
        )
        mpu_extra_args = " ".join(shlex.quote(a) for a in mpu_args_list)

        self._start_stream(recorder, sensor_type="mpu6050", extra_args=mpu_extra_args)

    def stop_live_stream(
        self,
        *,
        wait: bool = False,
        wait_timeout_ms: int | None = 5000,
    ) -> None:
        """Called by MainWindow when the Signals tab requests stop."""

        thread = self._ingest_thread
        self._stop_stream()

        if wait and thread is not None:
            if wait_timeout_ms is None:
                thread.wait()
            else:
                thread.wait(max(0, int(wait_timeout_ms)))

    def _stop_stream(self) -> None:
        worker = self._ingest_worker
        if worker is not None:
            self._stop_requested = True
            QMetaObject.invokeMethod(worker, "stop", Qt.QueuedConnection)
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.overall_status.setText("Stopping stream.")
            self.streaming_stopped.emit()
            self.recording_stopped.emit()
            self.mpu_rate_label.setText("MPU6050 rate: --")
            self._close_active_stream()
        else:
            # No worker running; ensure recorder is closed.
            self._stop_requested = False
            self._close_active_stream()
            if self._pi_recorder is not None:
                try:
                    self._pi_recorder.close()
                except Exception:
                    pass
                self._pi_recorder = None
                self.host_status_label.setText("Disconnected.")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.overall_status.setText("Idle.")
            self._clear_sample_queue()

    def _close_active_stream(self) -> None:
        stream = self._active_stream
        self._active_stream = None
        if stream is None:
            return

        close = getattr(stream, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                logger.exception("Failed to close active stream")

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

        self._close_active_stream()
        self._clear_sample_queue()
        parser = select_parser(sensor_type)
        self._stop_requested = False
        rc = self._rate_controllers[sensor_type]
        rc.reset()

        def _stderr_callback(line: str) -> None:
            self._emit_error(f"{sensor_type} stderr: {line}")

        try:
            stream = recorder.stream_mpu6050(
                extra_args=extra_args,
                recording=self._recording_mode,
                on_stderr=_stderr_callback,
            )
        except Exception as exc:
            self._emit_error(f"Failed to start sensor stream: {exc}")
            return

        self._active_stream = stream

        def _stream_factory():
            return stream

        thread = QThread(self)
        worker = SensorIngestWorker(
            recorder=recorder,
            stream_factory=_stream_factory,
            parser=parser,
            batch_size=self._ingest_batch_size,
            max_latency_ms=self._ingest_max_latency_ms,
            stream_label=sensor_type,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.samples_batch.connect(self._on_samples_batch)
        worker.error.connect(self._on_ingest_error)
        worker.finished.connect(self._on_ingest_finished)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.start()

        self._ingest_thread = thread
        self._ingest_worker = worker

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.overall_status.setText("Streaming.")
        self.recording_started.emit()
        self.streaming_started.emit()

    @Slot(list)
    def _on_samples_batch(self, samples: list[MpuSample]) -> None:
        if not samples:
            return

        self._data_buffer.add_samples(samples)

        rc = self._rate_controllers.get("mpu6050")
        updated_rate = False

        for sample in samples:
            if sample is None:
                continue
            if rc is not None:
                t = self._sample_time_seconds(sample)
                if t is not None:
                    rc.add_sample_time(t)
                    updated_rate = True
            self._enqueue_sample(sample)

        if rc is not None and updated_rate:
            self.rate_updated.emit("mpu6050", rc.estimated_hz)

    @Slot(str)
    def _on_ingest_error(self, message: str) -> None:
        self._ingest_had_error = True
        if message:
            self._emit_error(message)

    @Slot()
    def _on_ingest_finished(self) -> None:
        self._ingest_worker = None
        self._ingest_thread = None
        self._close_active_stream()

        if self._pi_recorder is not None:
            try:
                self._pi_recorder.close()
            except Exception:
                pass
            self._pi_recorder = None
            self.host_status_label.setText("Disconnected.")

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if self._stop_requested:
            self.overall_status.setText("Idle.")
        else:
            if not self._ingest_had_error:
                self._emit_error(
                    "Stream for mpu6050 ended unexpectedly (remote process exited)."
                )
            self.overall_status.setText("Stream ended.")
            self.streaming_stopped.emit()
            self.recording_stopped.emit()
            self.mpu_rate_label.setText("MPU6050 rate: --")

        self._stop_requested = False
        self._ingest_had_error = False
        self._clear_sample_queue()

    def _sample_time_seconds(self, sample: object) -> Optional[float]:
        if isinstance(sample, MpuSample):
            if sample.t_s is not None:
                return float(sample.t_s)
            return sample.timestamp_ns * 1e-9
        return None

    def report_error(self, message: str) -> None:
        """Expose the error-reporting pipeline to other widgets."""
        self._emit_error(message)

    def _emit_error(self, message: str) -> None:
        if not message:
            return
        self.error_reported.emit(message)
        self.recording_error.emit(message)

    @Slot(str)
    def _show_error(self, message: str) -> None:
        # Always reflect the latest remote message in the status bar
        self.overall_status.setText(message)

    @Slot(str, float)
    def _on_rate_updated(self, sensor_type: str, hz: float) -> None:
        if sensor_type == "mpu6050":
            self.mpu_rate_label.setText(f"GUI stream rate: {hz:.1f} Hz")

    @Slot(dict)
    def on_sensors_updated(self, sensors: dict) -> None:
        """
        Slot connected from SettingsTab.sensorsUpdated to keep the
        'Recording rate' label in sync with sensors.yaml.
        """
        mpu_cfg = dict(sensors.get("mpu6050", {}) or {})
        rate = mpu_cfg.get("sample_rate_hz")
        if rate is None:
            self._update_recording_rate_from_defaults()
            return
        try:
            rate_f = float(rate)
        except (TypeError, ValueError):
            self._update_recording_rate_from_defaults()
            return
        self.mpu_recording_rate_label.setText(f"{rate_f:.0f} Hz")

    @Slot(list)
    def on_hosts_updated(self, host_list: list[dict]) -> None:
        """
        Slot connected from SettingsTab.hostsUpdated to refresh the host combo.

        Parameters
        ----------
        host_list:
            Sequence of dictionaries mirroring hosts.yaml["pis"] entries.
        """
        entries: Iterable[Mapping[str, object]] = list(host_list or [])
        self._apply_host_entries(entries, preserve_selection=True)

    def data_buffer(self) -> StreamingDataBuffer:
        """Return the streaming data buffer for other tabs to query."""
        return self._data_buffer

    @property
    def sample_queue(self) -> queue.Queue[object]:
        """Return the queue carrying recent samples for GUI ingestion."""
        return self._sample_queue

    def _enqueue_sample(self, sample: object) -> None:
        """Push a parsed sample into the GUI queue without blocking."""
        try:
            self._sample_queue.put_nowait(sample)
        except queue.Full:
            logger.warning("Sample queue is full; dropping sample.")

    def _clear_sample_queue(self) -> None:
        """Best-effort drain of the GUI-facing sample queue."""
        try:
            while True:
                self._sample_queue.get_nowait()
        except queue.Empty:
            pass
