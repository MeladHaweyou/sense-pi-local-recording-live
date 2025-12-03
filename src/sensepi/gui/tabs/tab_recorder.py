"""Recorder tab for starting/stopping Raspberry Pi loggers."""

from __future__ import annotations

import logging
import math
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
    QVBoxLayout,
    QWidget,
)

from ..config.acquisition_state import SensorSelectionConfig
from ..widgets import AcquisitionSettings, CollapsibleSection
from ...analysis.rate import RateController
from ...config.app_config import HostConfig, HostInventory, SensorDefaults
from ...config.pi_logger_config import (
    PiLoggerConfig,
    build_logger_args,
    build_logger_command,
)
from ...config.sampling import GuiSamplingDisplay, SamplingConfig
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
    Device control panel for connecting to the Raspberry Pi logger.

    Responsibilities:
    - Let the user pick a host, configure MPU6050 options, and start/stop
      live streams or recordings.
    - Emit parsed samples into the shared :class:`StreamingDataBuffer` used by
      :class:`SignalsTab` and :class:`FftTab`.
    - Surface live rate estimates and errors so plotting tabs can adapt their
      refresh cadence.
    """

    #: Emitted for every parsed sample object (MpuSample, generic LiveSample, ...).
    sample_received = Signal(object)
    streaming_started = Signal()
    streaming_stopped = Signal()
    error_reported = Signal(str)
    rate_updated = Signal(str, float)
    sampling_config_changed = Signal(object)
    recording_started = Signal()
    recording_stopped = Signal()
    sensorSelectionChanged = Signal(SensorSelectionConfig)
    recording_error = Signal(str)

    def __init__(
        self,
        host_inventory: HostInventory | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._host_inventory = host_inventory or HostInventory()
        self._sensor_defaults = SensorDefaults()
        self._sampling_config = self._sensor_defaults.load_sampling_config()

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
        decimation = self._sampling_config.compute_decimation()
        self._data_buffer = StreamingDataBuffer(
            BufferConfig(
                max_seconds=6.0,
                sample_rate_hz=decimation["stream_rate_hz"],
            )
        )
        self._active_stream: Iterable[str] | None = None
        self._sample_queue: queue.Queue[object] = queue.Queue(maxsize=10_000)
        self._current_sensor_selection = SensorSelectionConfig()

        self._build_ui()
        self._load_hosts()
        self._refresh_sampling_labels()

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

        rate_form = QFormLayout()
        self.device_rate_label = QLabel("—", self.mpu_group)
        self.record_rate_label = QLabel("—", self.mpu_group)
        self.stream_rate_label = QLabel("—", self.mpu_group)
        self.mode_label = QLabel("—", self.mpu_group)

        rate_form.addRow("Device rate [Hz]:", self.device_rate_label)
        rate_form.addRow("Recording rate [Hz]:", self.record_rate_label)
        rate_form.addRow("GUI stream [Hz]:", self.stream_rate_label)
        rate_form.addRow("Mode:", self.mode_label)

        mpu_layout.addLayout(rate_form)

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
        self.mpu_sensors_edit.textChanged.connect(
            self._emit_sensor_selection_changed
        )
        self.mpu_channels_combo.currentIndexChanged.connect(
            self._emit_sensor_selection_changed
        )

        # Initialize cached sensor selection
        self._emit_sensor_selection_changed()

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

    def current_sensor_selection(self) -> SensorSelectionConfig:
        """
        Parse the sensor list + channel combo into a SensorSelectionConfig.
        """

        text = self.mpu_sensors_edit.text().strip()
        if not text:
            active_sensors: list[int] = []
        else:
            active_sensors = []
            for part in text.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    active_sensors.append(int(part))
                except ValueError:
                    continue

        key = str(self.mpu_channels_combo.currentData() or "default")

        if key in {"accel_only", "acc"}:
            channels = ["ax", "ay", "az"]
        elif key in {"gyro_only", "gyro"}:
            channels = ["gx", "gy", "gz"]
        elif key in {"both", "accel_gyro", "all6"}:
            channels = ["ax", "ay", "az", "gx", "gy", "gz"]
        else:
            channels = ["ax", "ay", "az", "gz"]

        return SensorSelectionConfig(
            active_sensors=active_sensors,
            active_channels=channels,
        )

    def _emit_sensor_selection_changed(self) -> None:
        cfg = self.current_sensor_selection()
        self._current_sensor_selection = cfg
        self.sensorSelectionChanged.emit(cfg)
        print("[RecorderTab] Sensor selection:", cfg.summary())

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

    def _load_sampling_config(self) -> SamplingConfig:
        try:
            config = self._sensor_defaults.load()
            sampling = SamplingConfig.from_mapping(config)
        except Exception:
            sampling = SamplingConfig(device_rate_hz=200.0)
        self._sampling_config = sampling
        return sampling

    def _get_default_mpu_dlpf(self) -> int | None:
        """Return the MPU6050 DLPF setting from sensors.yaml."""
        try:
            config = self._sensor_defaults.load()
        except Exception:
            return 3
        sensors = config.get("sensors", {}) if isinstance(config, dict) else {}
        mpu_cfg = dict(sensors.get("mpu6050", {}) or {})
        dlpf = mpu_cfg.get("dlpf")
        try:
            return int(dlpf)
        except (TypeError, ValueError):
            return None

    def _current_sampling(self) -> SamplingConfig:
        if not isinstance(self._sampling_config, SamplingConfig):
            return self._load_sampling_config()
        return self._sampling_config

    def sampling_config(self) -> SamplingConfig:
        """Return the current SamplingConfig used by the recorder UI."""
        return self._current_sampling()

    def set_sampling_config(self, sampling: SamplingConfig) -> None:
        """Replace the active SamplingConfig and refresh dependent labels."""
        self._apply_sampling_config(sampling, notify=True)

    def _apply_sampling_config(self, sampling: SamplingConfig, *, notify: bool = True) -> None:
        previous = self._current_sampling()
        normalized = SamplingConfig(
            device_rate_hz=float(sampling.device_rate_hz),
            mode_key=str(sampling.mode_key),
        )
        changed = (
            not math.isclose(previous.device_rate_hz, normalized.device_rate_hz, rel_tol=1e-6, abs_tol=1e-6)
            or previous.mode_key != normalized.mode_key
        )
        self._sampling_config = normalized
        self._refresh_sampling_labels()
        if notify and changed:
            self.sampling_config_changed.emit(normalized)

    def _refresh_sampling_labels(self) -> None:
        sampling = self._current_sampling()
        display = GuiSamplingDisplay.from_sampling(sampling)
        self.device_rate_label.setText(f"{display.device_rate_hz:.1f} Hz")
        self.record_rate_label.setText(f"{display.record_rate_hz:.1f} Hz")
        self.stream_rate_label.setText(f"{display.stream_rate_hz:.1f} Hz")
        self.mode_label.setText(display.mode_label)
        if hasattr(self._data_buffer, "config"):
            try:
                self._data_buffer.config.sample_rate_hz = display.stream_rate_hz
            except Exception:
                pass

    def target_stream_rate_hz(self) -> float:
        """Return the expected GUI stream rate derived from SamplingConfig."""
        display = GuiSamplingDisplay.from_sampling(self._current_sampling())
        return float(display.stream_rate_hz)

    def compute_stream_every(
        self,
        sample_rate_hz: float | None = None,
        *,
        fallback_every: int | None = None,
        **_legacy_kwargs: object,
    ) -> int:
        """
        Compatibility shim for older code that expects RecorderTab.compute_stream_every().

        Modern code should call :meth:`SamplingConfig.compute_decimation` directly, but
        this keeps historical call sites working by routing everything through the
        shared SamplingConfig state.
        """
        # Swallow legacy keyword arguments such as "recording".
        if _legacy_kwargs:
            _legacy_kwargs.pop("recording", None)

        sampling = getattr(self, "_sampling_config", None)
        if isinstance(sampling, SamplingConfig):
            try:
                decimation = sampling.compute_decimation()
                stream_every = int(decimation.get("stream_decimate", 0))
            except Exception:
                stream_every = 0
            else:
                stream_every = max(stream_every, 1)
            if stream_every >= 1:
                return stream_every

        if fallback_every is not None and fallback_every >= 1:
            return int(fallback_every)

        if sample_rate_hz and sample_rate_hz > 0:
            return max(1, int(round(float(sample_rate_hz) / 25.0)))

        return 1

    def request_coarser_streaming(self) -> None:
        """Adaptive tuning hook (no-op with unified sampling)."""
        logger.info("RecorderTab: sampling decimation is derived from mode; ignoring request")

    def request_finer_streaming(self) -> None:
        """Adaptive tuning hook (no-op with unified sampling)."""
        logger.info("RecorderTab: sampling decimation is derived from mode; ignoring request")

    def current_mpu_gui_config(self) -> MpuGuiConfig:
        sampling = self._current_sampling()
        return MpuGuiConfig(
            enabled=self.mpu_enable_chk.isChecked(),
            rate_hz=sampling.device_rate_hz,
            sensors=self.mpu_sensors_edit.text().strip() or "1,2,3",
            channels=self.mpu_channels_combo.currentData(),
            include_temp=self.mpu_temp_chk.isChecked(),
            limit_duration=self.mpu_limit_duration_chk.isChecked(),
            duration_s=float(self.mpu_duration_spin.value())
            if self.mpu_limit_duration_chk.isChecked()
            else 0.0,
        )

    def _build_pi_logger_config(
        self,
        acquisition: AcquisitionSettings | None = None,
        *,
        session_name: str | None = None,
    ) -> PiLoggerConfig:
        """
        Construct the PiLoggerConfig passed down to ``mpu6050_multi_logger.py``.

        The logger always uses :class:`SamplingConfig` as the single source of
        truth. Decimation for recording and streaming is derived from the
        selected recording mode; no other code path computes ``--stream-every``.
        """

        sampling = self._current_sampling()
        if acquisition is not None:
            sampling = acquisition.sampling

        extra: dict[str, object] = {}
        sensors = self.mpu_sensors_edit.text().strip()
        if sensors:
            extra["sensors"] = sensors

        channels = self.mpu_channels_combo.currentData() or "default"
        extra["channels"] = channels

        dlpf = self._get_default_mpu_dlpf()
        if dlpf is not None:
            extra["dlpf"] = dlpf

        if self.mpu_temp_chk.isChecked():
            extra["temp"] = True

        if self.mpu_limit_duration_chk.isChecked():
            duration_s = float(self.mpu_duration_spin.value())
            if duration_s > 0:
                extra["duration"] = f"{duration_s:.3f}"

        if session_name:
            extra["session_name"] = session_name

        return PiLoggerConfig.from_sampling(sampling, extra_cli=extra)

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

        if acquisition is not None:
            self._apply_sampling_config(acquisition.sampling, notify=True)

        mpu_cfg = self.current_mpu_gui_config()

        if not mpu_cfg.enabled:
            raise RuntimeError("Enable the MPU6050 sensor to start streaming.")

        recorder = self._ensure_recorder()

        if self._ingest_worker is not None:
            raise RuntimeError("MPU6050 streaming is already running.")

        pi_logger_cfg = self._build_pi_logger_config(
            acquisition, session_name=normalized_session or None
        )
        logger_cmd = build_logger_command(pi_logger_cfg)
        logger.debug("mpu6050 command: %s", shlex.join(logger_cmd))
        if len(logger_cmd) > 3:
            cli_tokens = logger_cmd[3:]
        else:
            cli_tokens = build_logger_args(pi_logger_cfg)
        mpu_extra_args = " ".join(shlex.quote(a) for a in cli_tokens)

        self._start_stream(recorder, sensor_type="mpu6050", extra_args=mpu_extra_args)

    def stop_live_stream(
        self,
        *,
        wait: bool = False,
        wait_timeout_ms: int | None = 5000,
    ) -> None:
        """Called by MainWindow when the Live Signals tab requests stop."""

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
        # Store the batch in the shared StreamingDataBuffer (for Signals/FFT)
        # and also push individual samples into the GUI queue for live plots.

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
        Slot connected from SettingsTab.sensorsUpdated to keep sampling labels
        in sync with sensors.yaml.
        """
        try:
            sampling = SamplingConfig.from_mapping(sensors)
        except Exception:
            return
        self.set_sampling_config(sampling)

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
