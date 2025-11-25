from __future__ import annotations

import ast
import json
import shlex
import threading
import time
from typing import Optional

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QDoubleSpinBox, QPushButton,
    QComboBox, QLabel, QMessageBox, QFileDialog, QCheckBox,
    QInputDialog, QStackedWidget, QPlainTextEdit,
)

from ..core.state import AppState
from ..data.ssh_stream_source import SSHStreamSource
from ssh_client.download_worker import (
    AutoDownloadWorker,
    DownloadNewestWorker,
    RemoteRunContextQt,
)
from ssh_client.ssh_manager import SSHClientManager


class PresetStore:
    """
    Lightweight wrapper around QSettings that stores presets as a JSON blob.
    Each preset is keyed by a human-readable name.
    """

    KEY = "ssh_presets"

    def __init__(self) -> None:
        self._settings = QSettings("SensePi", "QtSSH")
        self._presets: dict[str, dict] = {}
        self.load()
        self._seed_defaults_if_empty()

    @property
    def presets(self) -> dict[str, dict]:
        return self._presets

    def load(self) -> None:
        raw = self._settings.value(self.KEY, "{}", str)
        try:
            self._presets = json.loads(raw)
        except Exception:
            self._presets = {}

    def save(self) -> None:
        self._settings.setValue(self.KEY, json.dumps(self._presets, indent=2))

    def upsert(self, name: str, payload: dict) -> None:
        self._presets[name] = payload
        self.save()

    def delete(self, name: str) -> None:
        if name in self._presets:
            del self._presets[name]
            self.save()

    def _seed_defaults_if_empty(self) -> None:
        if self._presets:
            return
        self._presets = {
            "Quick ADXL test (10 s @ 100 Hz)": {
                "sensor_type": "adxl",
                "rate_hz": 100.0,
                "duration_s": 10.0,
                "channels": "both",
                "out": "/home/pi/logs/adxl",
                "addr": "0x48",
                "map": "x:P0,y:P1",
                "calibrate": 300,
                "lp_cut": 15.0,
            },
            "3×MPU6050 full sensors (60 s @ 200 Hz)": {
                "sensor_type": "mpu",
                "rate_hz": 200.0,
                "duration_s": 60.0,
                "sensors": "1,2,3",
                "channels": "both",
                "out": "/home/pi/logs/mpu",
                "format": "csv",
                "prefix": "mpu",
                "dlpf": 3,
                "temp": True,
            },
        }
        self.save()


class SSHTab(QWidget):
    """
    Simple SSH configuration + run-control panel.

    - Edits AppState.ssh (connection + run config).
    - Uses AppState.ensure_source() / AppState.start_source() so the shared
    SSHStreamSource instance is used by Signals/FFT tabs.
    - No plotting here; this is purely control/UI.
    """

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

        # SSH manager for SFTP operations (auto/manual downloads)
        self.ssh_manager = SSHClientManager()
        self._current_run_ctx: Optional[RemoteRunContextQt] = None
        self._last_auto_worker: Optional[AutoDownloadWorker] = None
        self._last_manual_worker: Optional[DownloadNewestWorker] = None

        self._settings = QSettings("SensePi", "QtSSH")
        self._adxl_zero_g_offsets: Optional[dict] = self._load_saved_zero_g_offsets()
        self._preset_store = PresetStore()
        self._rate_syncing = False
        self._stream_samples = 0
        self._stream_window_start = time.monotonic()
        self._stream_expected_hz = 0.0
        self._last_sample_time: float | None = None
        self._stream_lock = threading.Lock()
        self._stream_timer = QTimer(self)
        self._stream_timer.setInterval(1000)
        self._stream_timer.timeout.connect(self._check_stream_idle)
        self._run_active = False

        self._build_ui()
        self._update_zero_g_display(self._adxl_zero_g_offsets)
        self._load_from_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # --- Connection form ---
        conn_form = QFormLayout()

        self.edit_host = QLineEdit()
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)

        self.edit_user = QLineEdit()
        self.edit_password = QLineEdit()
        self.edit_password.setEchoMode(QLineEdit.Password)

        key_row = QHBoxLayout()
        self.edit_key = QLineEdit()
        btn_browse_key = QPushButton("Browse…")
        btn_browse_key.clicked.connect(self._choose_key_file)
        key_row.addWidget(self.edit_key)
        key_row.addWidget(btn_browse_key)

        conn_form.addRow("Host", self.edit_host)
        conn_form.addRow("Port", self.spin_port)
        conn_form.addRow("Username", self.edit_user)
        conn_form.addRow("Password", self.edit_password)
        # Use a container widget to hold the key_row layout
        key_container = QWidget()
        key_container.setLayout(key_row)
        conn_form.addRow("Key file", key_container)

        root.addLayout(conn_form)

        # --- Presets row ---
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox(self)
        self.btn_apply_preset = QPushButton("Apply preset", self)
        self.btn_save_preset = QPushButton("Save current as preset…", self)
        self.btn_delete_preset = QPushButton("Delete preset", self)

        self.btn_apply_preset.clicked.connect(self._on_apply_preset_clicked)
        self.btn_save_preset.clicked.connect(self._on_save_preset_clicked)
        self.btn_delete_preset.clicked.connect(self._on_delete_preset_clicked)

        preset_row.addWidget(self.preset_combo, 2)
        preset_row.addWidget(self.btn_apply_preset)
        preset_row.addWidget(self.btn_save_preset)
        preset_row.addWidget(self.btn_delete_preset)
        root.addLayout(preset_row)

        # --- Scripts / output ---
        paths_form = QFormLayout()
        self.edit_mpu_script = QLineEdit()
        self.edit_adxl_script = QLineEdit()
        self.edit_out_dir = QLineEdit()

        paths_form.addRow("MPU script", self.edit_mpu_script)
        paths_form.addRow("ADXL script", self.edit_adxl_script)
        paths_form.addRow("Remote out dir", self.edit_out_dir)
        root.addLayout(paths_form)

        # --- Run config ---
        run_form = QFormLayout()

        self.combo_sensor = QComboBox()
        self.combo_sensor.addItems(["MPU6050 (multi)", "ADXL203 (ADS1115)"])

        self.combo_run_mode = QComboBox()
        self.combo_run_mode.addItems(["Record only", "Record + live", "Live only"])

        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(0.1, 5000.0)
        self.spin_rate.setDecimals(2)
        self.spin_rate.setValue(100.0)

        self.spin_stream_every = QSpinBox()
        self.spin_stream_every.setRange(1, 1000000)
        self.spin_stream_every.setValue(5)

        run_form.addRow("Sensor", self.combo_sensor)
        run_form.addRow("Run mode", self.combo_run_mode)
        run_form.addRow("Rate (Hz)", self.spin_rate)
        run_form.addRow("Stream every N", self.spin_stream_every)
        root.addLayout(run_form)

        # Sensor-specific fields (stacked by sensor selection)
        self.sensor_stack = QStackedWidget(self)
        self.sensor_stack.addWidget(self._build_mpu_form())
        self.sensor_stack.addWidget(self._build_adxl_form())
        root.addWidget(self.sensor_stack)

        # --- Download options ---
        download_remote_row = QHBoxLayout()
        download_remote_row.addWidget(QLabel("Remote output dir:"))
        self.edit_remote_out = QLineEdit()
        download_remote_row.addWidget(self.edit_remote_out)

        self.btn_use_run_out = QPushButton("Use run --out")
        self.btn_use_run_out.clicked.connect(self._copy_out_from_run_settings)
        download_remote_row.addWidget(self.btn_use_run_out)
        root.addLayout(download_remote_row)

        local_row = QHBoxLayout()
        local_row.addWidget(QLabel("Local download folder:"))
        self.edit_local_download = QLineEdit()
        local_row.addWidget(self.edit_local_download)

        btn_browse_local = QPushButton("Browse…")
        btn_browse_local.clicked.connect(self._choose_local_folder)
        local_row.addWidget(btn_browse_local)

        self.btn_download_newest = QPushButton("Download newest manually")
        self.btn_download_newest.clicked.connect(self.on_download_newest_clicked)
        local_row.addWidget(self.btn_download_newest)
        root.addLayout(local_row)

        self.lbl_last_download = QLabel("Last download: n/a")
        root.addWidget(self.lbl_last_download)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_start_run = QPushButton("Start run")
        self.btn_stop_run = QPushButton("Stop run")

        self.btn_connect.clicked.connect(self.on_connect)
        self.btn_disconnect.clicked.connect(self.on_disconnect)
        self.btn_start_run.clicked.connect(self.on_start_run)
        self.btn_stop_run.clicked.connect(self.on_stop_run)

        btn_row.addWidget(self.btn_connect)
        btn_row.addWidget(self.btn_disconnect)
        btn_row.addWidget(self.btn_start_run)
        btn_row.addWidget(self.btn_stop_run)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        # Log output (remote stdout/stderr and local status)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Remote log output will appear here...")
        root.addWidget(self.log_output)

        # Status label (general text)
        self.lbl_status = QLabel("Disconnected")
        root.addWidget(self.lbl_status)

        # Mini status row
        self.lbl_ssh = QLabel("SSH: Disconnected")
        self.lbl_run = QLabel("Run: Idle")
        self.lbl_stream = QLabel("Stream: —")

        row = QHBoxLayout()
        row.addWidget(self.lbl_ssh)
        row.addWidget(self.lbl_run)
        row.addWidget(self.lbl_stream)
        row.addStretch(1)
        root.addLayout(row)
        self._set_indicator(self.lbl_ssh, "SSH: Disconnected", ok=False)
        self._set_indicator(self.lbl_run, "Run: Idle", ok=None)
        self._set_indicator(self.lbl_stream, "Stream: —", ok=None)

        self.setLayout(root)
        self._refresh_preset_combo()
        self.combo_sensor.currentIndexChanged.connect(self._on_sensor_changed)
        self.spin_rate.valueChanged.connect(self._on_common_rate_changed)
        self._update_sensor_type_ui()

    def _load_from_state(self) -> None:
        s = self.state.ssh
        self.edit_host.setText(s.host)
        self.spin_port.setValue(int(s.port))
        self.edit_user.setText(s.username)
        self.edit_password.setText(s.password)
        self.edit_key.setText(s.key_path)
        self.edit_mpu_script.setText(s.mpu_script)
        self.edit_adxl_script.setText(s.adxl_script)
        self.edit_out_dir.setText(s.remote_out_dir)
        self.edit_remote_out.setText(s.remote_out_dir)
        self.edit_local_download.setText(s.local_download_dir)
        self.spin_rate.setValue(float(s.rate_hz))
        self.spin_stream_every.setValue(int(s.stream_every))
        self.combo_sensor.setCurrentIndex(0 if s.run_sensor == "mpu" else 1)
        mode_index = {"record": 0, "record+live": 1, "live": 2}.get(s.run_mode, 1)
        self.combo_run_mode.setCurrentIndex(mode_index)
        self.mpu_rate_spin.setValue(float(s.rate_hz))
        self.adxl_rate_spin.setValue(float(s.rate_hz))
        self._on_sensor_changed(self.combo_sensor.currentIndex())

    def _save_to_state(self) -> None:
        s = self.state.ssh
        s.host = self.edit_host.text().strip()
        s.port = int(self.spin_port.value())
        s.username = self.edit_user.text().strip()
        s.password = self.edit_password.text()
        s.key_path = self.edit_key.text().strip()
        s.mpu_script = self.edit_mpu_script.text().strip()
        s.adxl_script = self.edit_adxl_script.text().strip()
        remote_out = self.edit_out_dir.text().strip()
        if not remote_out:
            remote_out = self.edit_remote_out.text().strip()
        s.remote_out_dir = remote_out
        self.edit_remote_out.setText(remote_out)
        s.local_download_dir = self.edit_local_download.text().strip()
        s.rate_hz = float(self.spin_rate.value())
        s.stream_every = int(self.spin_stream_every.value())
        s.run_sensor = "mpu" if self.combo_sensor.currentIndex() == 0 else "adxl"
        idx_mode = self.combo_run_mode.currentIndex()
        s.run_mode = ["record", "record+live", "live"][idx_mode]
        self.state.data_source = "ssh"

    def _copy_out_from_run_settings(self) -> None:
        out_dir = self._current_remote_out_dir_from_run_config()
        if out_dir:
            self.edit_remote_out.setText(out_dir)

    def _choose_local_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose local download folder")
        if folder:
            self.edit_local_download.setText(folder)

    def _current_remote_out_dir_from_run_config(self) -> str:
        return self.edit_out_dir.text().strip()

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def _append_log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}"
        if hasattr(self, "log_output"):
            self.log_output.appendPlainText(line)
            self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())
        else:
            print(f"[SSH] {line}")

    def _choose_key_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select private key", "", "Key files (*)")
        if path:
            self.edit_key.setText(path)

    def _ensure_ssh_source(self) -> SSHStreamSource:
        # Persist UI values to state and force backend to ssh
        self._save_to_state()

        # Stop any existing source (MQTT or previous SSH)
        try:
            self.state.stop_source()
        except Exception:
            pass

        self.state.data_source = "ssh"
        self.state.source = None

        src = self.state.ensure_source()
        if not isinstance(src, SSHStreamSource):
            raise RuntimeError("Expected SSHStreamSource when data_source == 'ssh'")
        return src

    def on_connect(self) -> None:
        self._save_to_state()
        self._append_log("Connecting...")
        self._set_indicator(self.lbl_ssh, "SSH: Connecting...", ok=None)
        thread = threading.Thread(target=self._connect_worker, daemon=True)
        thread.start()

    def on_disconnect(self) -> None:
        self._append_log("Disconnecting...")
        thread = threading.Thread(target=self._disconnect_worker, daemon=True)
        thread.start()

    def _connect_worker(self) -> None:
        try:
            src = self._ensure_ssh_source()
            s = self.state.ssh
            self.ssh_manager.connect(
                host=s.host,
                port=s.port,
                username=s.username,
                password=s.password,
                pkey_path=s.key_path or None,
            )
            src.connect()
        except Exception as exc:
            self._append_log(f"Connection error: {exc}")
            self._invoke_in_main(
                lambda: self._set_indicator(self.lbl_ssh, "SSH: Disconnected", ok=False)
            )
            self._invoke_in_main(lambda: QMessageBox.critical(self, "SSH connect failed", str(exc)))
            self._set_status("Connect failed")
            return

        def _on_ok() -> None:
            text = f"SSH: Connected to {self.state.ssh.username}@{self.state.ssh.host}:{self.state.ssh.port}"
            self._set_indicator(self.lbl_ssh, text, ok=True)
            self._set_status("Connected")

        self._append_log("Connected.")
        self._invoke_in_main(_on_ok)

    def _disconnect_worker(self) -> None:
        try:
            src = self.state.source
            if isinstance(src, SSHStreamSource):
                src.disconnect()
            self.ssh_manager.disconnect()
            self._current_run_ctx = None
            self._run_active = False
            self._stop_stream_monitor()
            self._invoke_in_main(lambda: self._set_indicator(self.lbl_run, "Run: Idle", ok=None))
            self._invoke_in_main(lambda: self._set_indicator(self.lbl_stream, "Stream: —", ok=None))
            self._invoke_in_main(lambda: self._set_indicator(self.lbl_ssh, "SSH: Disconnected", ok=False))
            self._set_status("Disconnected")
        except Exception as exc:
            self._append_log(f"Disconnect error: {exc}")
            self._invoke_in_main(lambda: QMessageBox.warning(self, "SSH disconnect", str(exc)))
    def on_start_run(self) -> None:
        try:
            src = self._ensure_ssh_source()
            s = self.state.ssh

            if not self.ssh_manager.is_connected():
                self._show_error("Not connected", "Connect to the Pi first.")
                self._set_indicator(self.lbl_ssh, "SSH: Disconnected", ok=False)
                return

            remote_out = self.edit_remote_out.text().strip() or self._current_remote_out_dir_from_run_config()
            local_out = self.edit_local_download.text().strip()
            if not remote_out:
                self._show_error("Missing remote dir", "Remote --out folder cannot be empty.")
                return
            if not local_out:
                self._show_error("Missing local folder", "Local download folder cannot be empty.")
                return

            try:
                start_snapshot = self.ssh_manager.listdir_with_mtime(remote_out)
            except Exception as exc:  # pragma: no cover - network dependent
                self._show_error("Cannot start run", f"Failed to list remote output folder: {exc}")
                return

            self._current_run_ctx = RemoteRunContextQt(
                remote_out_dir=remote_out,
                local_out_dir=local_out,
                start_snapshot=start_snapshot,
            )

            # Ensure internal threads are running if needed
            self.state.start_source()

            mode = s.run_mode
            record = (mode in ("record", "record+live"))
            live = (mode in ("record+live", "live"))

            sensor_label = "ADXL" if self.current_sensor_type() == "adxl" else "MPU6050"
            self._run_active = True
            self._stream_expected_hz = (float(s.rate_hz) / max(1, int(s.stream_every))) if s.stream_every else 0.0
            self._reset_stream_counters()
            self._start_stream_monitor()

            if isinstance(src, SSHStreamSource):
                try:
                    src.set_log_callback(self._on_remote_log)
                except Exception:
                    pass
                try:
                    src.set_sample_callback(self._on_stream_sample)
                except Exception:
                    pass
                try:
                    src.set_exit_callback(self._on_stream_exit)
                except Exception:
                    pass

            if s.run_sensor == "mpu":
                src.start_mpu_stream(
                    rate_hz=s.rate_hz,
                    record=record,
                    live=live,
                    stream_every=s.stream_every,
                )
            else:
                src.start_adxl_stream(
                    rate_hz=s.rate_hz,
                    record=record,
                    live=live,
                    stream_every=s.stream_every,
                )
            self._append_log(f"Run started ({sensor_label}, rate={s.rate_hz} Hz, stream_every={s.stream_every})")
            self._set_indicator(self.lbl_run, f"Run: Running {sensor_label}", ok=True)
            self._set_indicator(self.lbl_stream, "Stream: warming up…", ok=None)
            self._set_status("Run active")
        except Exception as exc:
            QMessageBox.critical(self, "Start run failed", str(exc))
            self._append_log(f"Run start error: {exc}")
            self._set_indicator(self.lbl_run, "Run: Error (see log)", ok=False)
            self._set_status("Run error")
            self._current_run_ctx = None
            self._run_active = False
            self._stop_stream_monitor()

    def on_stop_run(self) -> None:
        try:
            self._run_active = False
            src = self.state.source
            if isinstance(src, SSHStreamSource):
                if hasattr(src, "stop_run"):
                    src.stop_run()
                else:
                    src.stop()
            script_name = ""
            if isinstance(src, SSHStreamSource):
                script_name = self.state.ssh.adxl_script if self.current_sensor_type() == "adxl" else self.state.ssh.mpu_script
            pattern = script_name or ("adxl203_ads1115_logger.py" if self.current_sensor_type() == "adxl" else "mpu6050_multi_logger.py")
            try:
                _, err, status = self.ssh_manager.exec_quick(f"pkill -f {pattern}")
                self._append_log(f"Stop command sent (pkill status {status}).")
                if err.strip():
                    self._append_log(f"pkill stderr: {err.strip()}")
                if status != 0:
                    self._set_indicator(self.lbl_run, "Run: pkill error", ok=False)
            except Exception as exc_stop:
                self._append_log(f"Stop error: {exc_stop}")
                self._set_indicator(self.lbl_run, "Run: pkill error", ok=False)

            self._set_indicator(self.lbl_run, "Run: Idle", ok=None)
            self._set_status("Run stopped")
            self._start_auto_download()
            self._stop_stream_monitor()
            self._set_indicator(self.lbl_stream, "Stream: —", ok=None)
        except Exception as exc:
            QMessageBox.warning(self, "Stop run", str(exc))
            self._append_log(f"Stop run error: {exc}")

    def _start_auto_download(self) -> None:
        """Kick off background download for files created during the last run."""
        if not self._current_run_ctx:
            return
        if not self.ssh_manager.is_connected():
            self._show_error("Not connected", "Cannot download; SSH disconnected.")
            return
        worker = AutoDownloadWorker(self.ssh_manager, self._current_run_ctx, parent=self)
        worker.signals.log.connect(self._append_log)
        worker.signals.result.connect(self._on_auto_download_result)
        worker.start()
        self._last_auto_worker = worker

    def _on_auto_download_result(self, n_files: int, ts: str, ok: bool, err: str) -> None:
        if ok:
            text = f"Last run: {n_files} file(s) downloaded at {ts}" if n_files else f"Last run: no new files ({ts})"
        else:
            text = f"Last run: download failed at {ts}"
        self.lbl_last_download.setText(text)
        if not ok and err:
            self._show_error("Auto-download failed", err)
        self._current_run_ctx = None
        if ok:
            self._append_log(text)
        elif err:
            self._append_log(f"Auto-download failed: {err}")

    def on_download_newest_clicked(self) -> None:
        if not self.ssh_manager.is_connected():
            self._show_error("Not connected", "Connect to the Pi first.")
            return

        remote_dir = self.edit_remote_out.text().strip() or self._current_remote_out_dir_from_run_config()
        local_dir = self.edit_local_download.text().strip()
        if not remote_dir:
            self._show_error("Missing remote dir", "Remote output directory is empty.")
            return
        if not local_dir:
            self._show_error("Missing local folder", "Local download folder is empty.")
            return

        worker = DownloadNewestWorker(
            self.ssh_manager,
            remote_dir=remote_dir,
            local_dir=local_dir,
            max_files=5,
            parent=self,
        )
        worker.signals.log.connect(self._append_log)
        worker.signals.result.connect(self._on_manual_download_result)
        worker.start()
        self._last_manual_worker = worker

    def _on_manual_download_result(self, n_files: int, ts: str, ok: bool, err: str) -> None:
        if ok:
            text = f"Manual download: {n_files} file(s) at {ts}"
        else:
            text = f"Manual download failed at {ts}"
        self.lbl_last_download.setText(text)
        if not ok and err:
            self._show_error("Download failed", err)
        self._append_log(text if ok else f"[ERROR] {text}: {err}")

    # ---- Stream + log callbacks ----
    def _on_remote_log(self, line: str) -> None:
        self._append_log(line)

    def _reset_stream_counters(self) -> None:
        with self._stream_lock:
            self._stream_samples = 0
            self._stream_window_start = time.monotonic()
            self._last_sample_time = None

    def _start_stream_monitor(self) -> None:
        self._stream_timer.start()

    def _stop_stream_monitor(self) -> None:
        self._stream_timer.stop()
        self._reset_stream_counters()
        self._stream_expected_hz = 0.0

    def _on_stream_sample(self, mode: str | None = None) -> None:
        if not self._run_active:
            return
        now = time.monotonic()
        with self._stream_lock:
            self._stream_samples += 1
            if self._stream_window_start <= 0:
                self._stream_window_start = now
            self._last_sample_time = now
            self._maybe_update_stream_label_locked(now)

    def _maybe_update_stream_label_locked(self, now: float) -> None:
        dt = now - self._stream_window_start
        if dt < 1.0:
            return
        rate = self._stream_samples / dt if dt > 0 else 0.0
        expected = self._stream_expected_hz or 0.0
        ok_flag = None
        text = f"Stream: {rate:.1f} pkt/s"
        if expected > 0:
            ok_flag = rate > 0.5 * expected
            text = f"Stream: {rate:.1f} pkt/s (expected ~{expected:.1f})"
        self._stream_samples = 0
        self._stream_window_start = now
        self._invoke_in_main(lambda: self._set_indicator(self.lbl_stream, text, ok=ok_flag))

    def _check_stream_idle(self) -> None:
        if not self._run_active:
            return
        now = time.monotonic()
        with self._stream_lock:
            last = self._last_sample_time
        if last is None:
            return
        if now - last > 2.0:
            self._invoke_in_main(lambda: self._set_indicator(self.lbl_stream, "Stream: no data", ok=False))

    def _on_stream_exit(self, status: int | None) -> None:
        self._run_active = False
        self._stop_stream_monitor()
        self._invoke_in_main(lambda: self._set_indicator(self.lbl_stream, "Stream: —", ok=None))
        if status is None or status == 0:
            self._set_indicator(self.lbl_run, "Run: Idle", ok=None)
            self._append_log("Run finished.")
        else:
            self._set_indicator(self.lbl_run, "Run: Error (see log)", ok=False)
            self._append_log(f"Run exited with status {status}")
        self._set_status("Run finished")
        self._invoke_in_main(self._start_auto_download)

    # ---- Preset helpers ----
    def _refresh_preset_combo(self, select_name: str | None = None) -> None:
        current = select_name or self.preset_combo.currentText()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("<No preset>")
        for name in sorted(self._preset_store.presets.keys()):
            self.preset_combo.addItem(name)
        if current and current in self._preset_store.presets:
            self.preset_combo.setCurrentText(current)
        else:
            self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)

    def _on_apply_preset_clicked(self) -> None:
        name = self.preset_combo.currentText()
        if not name or name == "<No preset>":
            return
        preset = self._preset_store.presets.get(name)
        if not preset:
            return
        self._apply_preset_dict(preset)

    def _on_save_preset_clicked(self) -> None:
        name, ok = QInputDialog.getText(self, "Preset name", "Enter a preset name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        preset = self._current_form_as_preset_dict()
        self._preset_store.upsert(name, preset)
        self._refresh_preset_combo(select_name=name)
        self.preset_combo.setCurrentText(name)

    def _on_delete_preset_clicked(self) -> None:
        name = self.preset_combo.currentText()
        if not name or name == "<No preset>":
            return
        self._preset_store.delete(name)
        self._refresh_preset_combo()

    def _current_form_as_preset_dict(self) -> dict:
        sensor_type = "mpu" if self.combo_sensor.currentIndex() == 0 else "adxl"
        out_dir = self.edit_out_dir.text().strip()
        if sensor_type == "adxl":
            return {
                "sensor_type": "adxl",
                "rate_hz": float(self.adxl_rate_spin.value()),
                "duration_s": float(self.adxl_duration_spin.value()),
                "channels": self.adxl_channels_combo.currentText(),
                "out": out_dir,
                "addr": self.adxl_addr_edit.text().strip(),
                "map": self.adxl_map_edit.text().strip(),
                "calibrate": int(self.adxl_calibrate_spin.value()),
                "lp_cut": float(self.adxl_lp_cut_spin.value()),
            }
        return {
            "sensor_type": "mpu",
            "rate_hz": float(self.mpu_rate_spin.value()),
            "duration_s": float(self.mpu_duration_spin.value()),
            "sensors": self.mpu_sensors_edit.text().strip(),
            "channels": self.mpu_channels_combo.currentText(),
            "out": out_dir,
            "format": self.mpu_format_combo.currentText(),
            "prefix": self.mpu_prefix_edit.text().strip(),
            "dlpf": int(self.mpu_dlpf_spin.value()),
            "temp": bool(self.mpu_temp_checkbox.isChecked()),
        }

    def _apply_preset_dict(self, preset: dict) -> None:
        def _get(key: str, fallback: str | None = None):
            return preset.get(key, preset.get(fallback, None) if fallback else None)

        sensor_type = preset.get("sensor_type", "mpu")
        rate = _get("rate_hz", "rate")
        duration = _get("duration_s", "duration")
        out = preset.get("out")

        if sensor_type == "adxl":
            self.combo_sensor.setCurrentIndex(1)
            if rate is not None:
                self.adxl_rate_spin.setValue(float(rate))
            if duration is not None:
                self.adxl_duration_spin.setValue(float(duration))
            if "channels" in preset:
                self.adxl_channels_combo.setCurrentText(str(preset["channels"]))
            if out:
                self.edit_out_dir.setText(str(out))
            if "addr" in preset:
                self.adxl_addr_edit.setText(str(preset["addr"]))
            if "map" in preset:
                self.adxl_map_edit.setText(str(preset["map"]))
            if "calibrate" in preset:
                self.adxl_calibrate_spin.setValue(int(preset["calibrate"]))
            if "lp_cut" in preset:
                self.adxl_lp_cut_spin.setValue(float(preset["lp_cut"]))
        else:
            self.combo_sensor.setCurrentIndex(0)
            if rate is not None:
                self.mpu_rate_spin.setValue(float(rate))
            if duration is not None:
                self.mpu_duration_spin.setValue(float(duration))
            if "sensors" in preset:
                self.mpu_sensors_edit.setText(str(preset["sensors"]))
            if "channels" in preset:
                self.mpu_channels_combo.setCurrentText(str(preset["channels"]))
            if out:
                self.edit_out_dir.setText(str(out))
            if "format" in preset:
                self.mpu_format_combo.setCurrentText(str(preset["format"]))
            if "prefix" in preset:
                self.mpu_prefix_edit.setText(str(preset["prefix"]))
            if "dlpf" in preset:
                self.mpu_dlpf_spin.setValue(int(preset["dlpf"]))
            if "temp" in preset:
                self.mpu_temp_checkbox.setChecked(bool(preset.get("temp")))

        if rate is not None:
            self.spin_rate.setValue(float(rate))
        if out:
            self.edit_remote_out.setText(str(out))
        self._on_sensor_changed(self.combo_sensor.currentIndex())

    # ---- UI helpers ----
    def _build_mpu_form(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        self.mpu_rate_spin = QDoubleSpinBox()
        self.mpu_rate_spin.setRange(0.1, 5000.0)
        self.mpu_rate_spin.setDecimals(2)
        self.mpu_rate_spin.setValue(100.0)

        self.mpu_duration_spin = QDoubleSpinBox()
        self.mpu_duration_spin.setRange(0.0, 1_000_000.0)
        self.mpu_duration_spin.setDecimals(2)

        self.mpu_sensors_edit = QLineEdit("1,2,3")
        self.mpu_channels_combo = QComboBox()
        self.mpu_channels_combo.addItems(["acc", "gyro", "both", "default"])
        self.mpu_out_edit = self.edit_out_dir
        self.mpu_format_combo = QComboBox()
        self.mpu_format_combo.addItems(["csv", "jsonl"])
        self.mpu_prefix_edit = QLineEdit("mpu")
        self.mpu_dlpf_spin = QSpinBox()
        self.mpu_dlpf_spin.setRange(0, 10)
        self.mpu_dlpf_spin.setValue(3)
        self.mpu_temp_checkbox = QCheckBox("Include temp")

        form.addRow("MPU rate (Hz)", self.mpu_rate_spin)
        form.addRow("Duration (s)", self.mpu_duration_spin)
        form.addRow("Sensors", self.mpu_sensors_edit)
        form.addRow("Channels", self.mpu_channels_combo)
        form.addRow("Format", self.mpu_format_combo)
        form.addRow("Prefix", self.mpu_prefix_edit)
        form.addRow("DLPF", self.mpu_dlpf_spin)
        form.addRow(self.mpu_temp_checkbox)

        self.mpu_rate_spin.valueChanged.connect(lambda v: self._on_sensor_rate_changed(v, "mpu"))

        return page

    def _build_adxl_form(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        self.adxl_rate_spin = QDoubleSpinBox()
        self.adxl_rate_spin.setRange(0.1, 5000.0)
        self.adxl_rate_spin.setDecimals(2)
        self.adxl_rate_spin.setValue(100.0)

        self.adxl_duration_spin = QDoubleSpinBox()
        self.adxl_duration_spin.setRange(0.0, 1_000_000.0)
        self.adxl_duration_spin.setDecimals(2)

        self.adxl_channels_combo = QComboBox()
        self.adxl_channels_combo.addItems(["x", "y", "both"])
        self.adxl_addr_edit = QLineEdit("0x48")
        self.adxl_map_edit = QLineEdit("x:P0,y:P1")
        self.adxl_calibrate_spin = QSpinBox()
        self.adxl_calibrate_spin.setRange(0, 1_000_000)
        self.adxl_calibrate_spin.setValue(300)
        self.adxl_lp_cut_spin = QDoubleSpinBox()
        self.adxl_lp_cut_spin.setRange(0.0, 10_000.0)
        self.adxl_lp_cut_spin.setDecimals(2)
        self.adxl_lp_cut_spin.setValue(15.0)

        self.btn_calibrate_adxl = QPushButton("Calibrate ADXL")
        self.btn_calibrate_adxl.clicked.connect(self.on_calibrate_adxl_clicked)
        self.adxl_zero_g_display = QLineEdit()
        self.adxl_zero_g_display.setReadOnly(True)
        self.adxl_zero_g_display.setPlaceholderText("Zero-g offsets (after calibration)")
        calib_row = QHBoxLayout()
        calib_row.addWidget(self.btn_calibrate_adxl)
        calib_row.addWidget(QLabel("Offsets:"))
        calib_row.addWidget(self.adxl_zero_g_display)
        calib_row.addStretch(1)
        calib_container = QWidget(self)
        calib_container.setLayout(calib_row)

        form.addRow("ADXL rate (Hz)", self.adxl_rate_spin)
        form.addRow("Duration (s)", self.adxl_duration_spin)
        form.addRow("Channels", self.adxl_channels_combo)
        form.addRow("Addr", self.adxl_addr_edit)
        form.addRow("Map", self.adxl_map_edit)
        form.addRow("Calibrate", self.adxl_calibrate_spin)
        form.addRow("LP cut", self.adxl_lp_cut_spin)
        form.addRow("Zero-g", calib_container)

        self.adxl_rate_spin.valueChanged.connect(lambda v: self._on_sensor_rate_changed(v, "adxl"))

        return page

    def _on_sensor_changed(self, idx: int) -> None:
        self.sensor_stack.setCurrentIndex(idx)
        if idx == 0:
            self.spin_rate.setValue(float(self.mpu_rate_spin.value()))
        else:
            self.spin_rate.setValue(float(self.adxl_rate_spin.value()))
        self._update_sensor_type_ui()

    def _on_common_rate_changed(self, value: float) -> None:
        if self._rate_syncing:
            return
        self._rate_syncing = True
        if self.combo_sensor.currentIndex() == 0:
            self.mpu_rate_spin.setValue(float(value))
        else:
            self.adxl_rate_spin.setValue(float(value))
        self._rate_syncing = False

    def _on_sensor_rate_changed(self, value: float, sensor: str) -> None:
        if self._rate_syncing:
            return
        if (sensor == "mpu" and self.combo_sensor.currentIndex() == 0) or (
            sensor == "adxl" and self.combo_sensor.currentIndex() == 1
        ):
            self._rate_syncing = True
            self.spin_rate.setValue(float(value))
            self._rate_syncing = False

    def current_sensor_type(self) -> str:
        return "adxl" if self.combo_sensor.currentIndex() == 1 else "mpu"

    def _update_sensor_type_ui(self) -> None:
        is_adxl = (self.current_sensor_type() == "adxl")
        if hasattr(self, "btn_calibrate_adxl"):
            self.btn_calibrate_adxl.setEnabled(is_adxl)

    def _set_indicator(self, label: QLabel, text: str, ok: bool | None) -> None:
        """Set status text + color for mini indicators."""
        label.setText(text)
        if ok is True:
            color = "#2e8b57"
        elif ok is False:
            color = "#b22222"
        else:
            color = "#444444"
        label.setStyleSheet(f"QLabel {{ color: {color}; font-weight: bold; }}")

    def _invoke_in_main(self, fn) -> None:
        """Schedule fn to run on the Qt main thread."""
        QTimer.singleShot(0, fn)

    def _set_status(self, text: str) -> None:
        self._invoke_in_main(lambda: self.lbl_status.setText(text))

    def build_adxl_calibration_command(self) -> str:
        script_path = self.edit_adxl_script.text().strip() or "/home/verwalter/sensor/adxl203_ads1115_logger.py"
        rate = float(self.adxl_rate_spin.value())
        channels = self.adxl_channels_combo.currentText()
        duration = float(self.adxl_duration_spin.value())
        if duration <= 0:
            duration = 5.0
        duration = max(1.0, min(duration, 30.0))
        out_dir = self.edit_out_dir.text().strip() or self.edit_remote_out.text().strip() or "/home/verwalter/sensor/logs"
        addr = self.adxl_addr_edit.text().strip()
        channel_map = self.adxl_map_edit.text().strip()
        calibrate_samples = max(1, int(self.adxl_calibrate_spin.value()))
        lp_cut = float(self.adxl_lp_cut_spin.value())

        parts = [
            "python3",
            shlex.quote(script_path),
            "--rate",
            str(rate),
            "--channels",
            shlex.quote(channels),
            "--duration",
            str(duration),
            "--calibrate",
            str(calibrate_samples),
            "--no-record",
            "--out",
            shlex.quote(out_dir),
            "--lp-cut",
            str(lp_cut),
        ]
        if addr:
            parts += ["--addr", shlex.quote(addr)]
        if channel_map:
            parts += ["--map", shlex.quote(channel_map)]

        return " ".join(parts)

    def _parse_zero_g_offsets(self, stdout: str) -> Optional[dict]:
        for line in stdout.splitlines():
            if "Zero-g offsets (V)" in line:
                _, _, tail = line.partition(":")
                try:
                    offsets = ast.literal_eval(tail.strip())
                except Exception:
                    return None
                return offsets if isinstance(offsets, dict) else None
        return None

    def _load_saved_zero_g_offsets(self) -> Optional[dict]:
        raw = self._settings.value("adxl_zero_g_offsets", "", str)
        if not raw:
            return None
        try:
            offsets = ast.literal_eval(str(raw))
        except Exception:
            return None
        return offsets if isinstance(offsets, dict) else None

    def _update_zero_g_display(self, offsets: Optional[dict]) -> None:
        if not hasattr(self, "adxl_zero_g_display"):
            return
        if offsets:
            self.adxl_zero_g_display.setText(str(offsets))
        else:
            self.adxl_zero_g_display.clear()

    def on_calibrate_adxl_clicked(self) -> None:
        if self.current_sensor_type() != "adxl":
            return
        if not self.ssh_manager.is_connected():
            QMessageBox.warning(self, "SSH", "Connect to the Pi first.")
            return

        cmd = self.build_adxl_calibration_command()
        self._set_status("Calibrating ADXL... keep the sensor still")
        try:
            stdout, stderr, status = self.ssh_manager.exec_quick(cmd)
        except Exception as exc:
            QMessageBox.critical(self, "Calibration failed", str(exc))
            self._set_status("Calibration failed")
            return

        if status != 0:
            detail = stderr.strip() or f"Logger exited with status {status}"
            QMessageBox.warning(self, "Calibration failed", detail)
            self._set_status("Calibration failed")
            return

        offsets = self._parse_zero_g_offsets(stdout)
        if not isinstance(offsets, dict):
            QMessageBox.warning(self, "Calibration", "Could not parse zero-g offsets from logger output.")
            self._set_status("Calibration: parse error")
            return

        self._adxl_zero_g_offsets = offsets
        self._settings.setValue("adxl_zero_g_offsets", str(offsets))
        self._update_zero_g_display(offsets)
        self._set_status(f"ADXL calibrated. Zero-g offsets (V): {offsets}")
