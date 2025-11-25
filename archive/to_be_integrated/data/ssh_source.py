from __future__ import annotations

import json
import shlex
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .base import DataSource
from util.ringbuf import RingBuffer
from util.ssh_client import SSHClientManager
from ..core.models import SSHSettings


@dataclass
class RateInfo:
    """Lightweight container mimicking MQTTSource.get_rate() result."""

    hz_effective: float = 0.0


@dataclass
class MPUStreamConfig:
    """
    Configuration for starting mpu6050_multi_logger.py over SSH.

    Command shape:

      python3 <script_path> --rate <rate_hz> --sensors <sensors> --channels <channels>           --out <out_dir> --format <format> [--no-record]           --stream-stdout --stream-every <stream_every> --stream-fields ax,ay,gz
    """

    script_path: str = "/home/verwalter/sensor/mpu6050_multi_logger.py"
    rate_hz: float = 100.0
    sensors: str = "1,2,3"
    channels: str = "default"
    out_dir: str = "/home/verwalter/sensor/logs"
    format: str = "csv"
    stream_every: int = 1
    no_record: bool = True
    extra_args: List[str] = field(default_factory=list)


@dataclass
class ADXLStreamConfig:
    """
    Configuration for starting adxl203_ads1115_logger.py over SSH.

    Command shape:

      python3 <script_path> --rate <rate_hz> --channels <channels> --out <out_dir>           --addr <addr> --map <chan_map> --calibrate <calibrate> --lp-cut <lp_cut>           [--no-record] --stream-stdout --stream-every <stream_every>           --stream-fields x_lp,y_lp
    """

    script_path: str = "/home/verwalter/sensor/adxl203_ads1115_logger.py"
    rate_hz: float = 100.0
    channels: str = "both"
    out_dir: str = "/home/verwalter/sensor/logs"
    addr: str = "0x48"
    chan_map: str = "x:P0,y:P1"
    calibrate: int = 300
    lp_cut: float = 15.0
    stream_every: int = 1
    no_record: bool = True
    extra_args: List[str] = field(default_factory=list)


def build_mpu_command(cfg: MPUStreamConfig) -> str:
    """Return a shell command string to start the MPU6050 logger with streaming."""
    parts: List[str] = [
        "python3",
        shlex.quote(cfg.script_path),
        "--rate",
        str(cfg.rate_hz),
        "--sensors",
        shlex.quote(cfg.sensors),
        "--channels",
        shlex.quote(cfg.channels),
        "--out",
        shlex.quote(cfg.out_dir),
        "--format",
        shlex.quote(cfg.format),
    ]

    if cfg.no_record:
        parts.append("--no-record")

    parts.extend(
        [
            "--stream-stdout",
            "--stream-every",
            str(max(1, int(cfg.stream_every))),
            "--stream-fields",
            "ax,ay,gz",
        ]
    )

    parts.extend(cfg.extra_args)
    return " ".join(parts)


def build_adxl_command(cfg: ADXLStreamConfig) -> str:
    """Return a shell command string to start the ADXL logger with streaming."""
    parts: List[str] = [
        "python3",
        shlex.quote(cfg.script_path),
        "--rate",
        str(cfg.rate_hz),
        "--channels",
        shlex.quote(cfg.channels),
        "--out",
        shlex.quote(cfg.out_dir),
        "--addr",
        shlex.quote(cfg.addr),
        "--map",
        shlex.quote(cfg.chan_map),
        "--calibrate",
        str(cfg.calibrate),
        "--lp-cut",
        str(cfg.lp_cut),
    ]

    if cfg.no_record:
        parts.append("--no-record")

    parts.extend(
        [
            "--stream-stdout",
            "--stream-every",
            str(max(1, int(cfg.stream_every))),
            "--stream-fields",
            "x_lp,y_lp",
        ]
    )

    parts.extend(cfg.extra_args)
    return " ".join(parts)


class SSHStreamSource(DataSource):
    """
    DataSource implementation backed by SSH JSON streaming.

    It reads JSON lines from remote loggers (MPU6050 or ADXL203) via
    SSHClientManager.exec_command_stream(), and exposes a 9-slot interface:

      slot_0..slot_8      -> values (numpy array)
      slot_ts_0..slot_ts_8 -> timestamps in seconds (numpy array)
    """

    def __init__(
        self,
        ssh_manager: SSHClientManager,
        *,
        maxlen: int = 20000,
        rate_window_samples: int = 512,
    ) -> None:
        self.ssh = ssh_manager
        self._maxlen = int(maxlen)
        self._rate_window_samples = int(max(2, rate_window_samples))

        self._values: List[RingBuffer] = [RingBuffer(self._maxlen) for _ in range(9)]
        self._times: List[RingBuffer] = [RingBuffer(self._maxlen) for _ in range(9)]

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._channel = None
        self._stdout = None
        self._stderr = None
        self._mode: Optional[str] = None  # "mpu" or "adxl"
        self._stderr_thread: Optional[threading.Thread] = None

        self._t0_ns: Optional[int] = None
        self._t0_mono_ns: int = time.monotonic_ns()

        self._hz_estimate: float = 0.0
        self._rate_info = RateInfo(0.0)

        # For compatibility with MQTT-style helpers
        self._last_apply_status: str = "idle"
        self._last_apply_hz: float = 0.0
        self._last_apply_time: float = 0.0
        self._log_callback: Optional[Callable[[str], None]] = None
        self._sample_callback: Optional[Callable[[Optional[str]], None]] = None
        self._exit_callback: Optional[Callable[[Optional[int]], None]] = None

    # ------------------------------------------------------------------ DataSource API
    def set_log_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """Register a callback that receives stderr/stdout lines for logging."""
        self._log_callback = callback

    def set_sample_callback(self, callback: Optional[Callable[[Optional[str]], None]]) -> None:
        """Register a callback that fires when a sample is processed."""
        self._sample_callback = callback

    def set_exit_callback(self, callback: Optional[Callable[[Optional[int]], None]]) -> None:
        """Register a callback fired when the remote command exits."""
        self._exit_callback = callback

    def start(self) -> None:
        """No-op: use start_mpu_stream() / start_adxl_stream() to begin streaming."""
        return

    def stop(self) -> None:
        """Stop any active SSH stream and reset buffers."""
        with self._lock:
            self._stop_event.set()
            channel = self._channel
            thread = self._thread
            err_thread = self._stderr_thread
            self._channel = None
            self._stdout = None
            self._stderr = None
            self._thread = None
            self._stderr_thread = None

        if channel is not None:
            try:
                channel.close()
            except Exception:
                pass

        if thread is not None and thread.is_alive():
            try:
                thread.join(timeout=1.0)
            except Exception:
                pass
        if err_thread is not None and err_thread.is_alive():
            try:
                err_thread.join(timeout=1.0)
            except Exception:
                pass

        with self._lock:
            for rb in self._values + self._times:
                rb.clear()
            self._hz_estimate = 0.0
            self._rate_info.hz_effective = 0.0
            self._mode = None
            self._t0_ns = None

    def read(self, last_seconds: float) -> Dict[str, np.ndarray]:
        """
        Return the most recent data for each slot over the given time window.

        Keys:
          - slot_i      : values
          - slot_ts_i   : timestamps in seconds
        """
        window = max(0.0, float(last_seconds))
        out: Dict[str, np.ndarray] = {}

        with self._lock:
            for idx in range(9):
                ts_rb = self._times[idx]
                val_rb = self._values[idx]

                ts_all = ts_rb.get_last(ts_rb.size)
                val_all = val_rb.get_last(val_rb.size)

                if ts_all.size == 0 or val_all.size == 0:
                    ts_arr = np.empty(0, dtype=float)
                    val_arr = np.empty(0, dtype=float)
                else:
                    if window <= 0.0:
                        ts_arr = ts_all
                        val_arr = val_all
                    else:
                        cutoff = ts_all[-1] - window
                        mask = ts_all >= cutoff
                        ts_arr = ts_all[mask]
                        if val_all.shape[0] == ts_all.shape[0]:
                            val_arr = val_all[mask]
                        else:
                            n = ts_arr.size
                            val_arr = val_all[-n:] if n > 0 else np.empty(0, dtype=float)

                out[f"slot_{idx}"] = np.asarray(val_arr, dtype=float)
                out[f"slot_ts_{idx}"] = np.asarray(ts_arr, dtype=float)

        return out

    # ------------------------------------------------------------------ Rate helpers
    @property
    def estimated_hz(self) -> float:
        """Estimated sampling frequency (Hz), based on slot 0 timestamps."""
        return float(self._hz_estimate or 0.0)

    def get_rate(self) -> RateInfo:
        """Return a small object mimicking MQTTSource.get_rate()."""
        return self._rate_info

    def switch_frequency(self, hz: float) -> None:
        """
        MQTT-compatible stub.

        For SSH we do not (yet) send any command to the device; instead we just
        record the request so that get_rate_apply_result() has something to return.
        """
        self._last_apply_status = "unsupported"
        self._last_apply_hz = float(hz)
        self._last_apply_time = time.monotonic()

    def get_rate_apply_result(self) -> Tuple[str, float, float]:
        """
        MQTT-compatible stub returning (status, requested_hz, monotonic_time_s).

        For SSH you will typically see status == "unsupported".
        """
        return self._last_apply_status, self._last_apply_hz, self._last_apply_time

    # ------------------------------------------------------------------ Public SSH start helpers
    def start_mpu_stream(self, config: MPUStreamConfig) -> None:
        """Start streaming from mpu6050_multi_logger.py."""
        command = build_mpu_command(config)
        self._start_stream(command, mode="mpu")

    def start_adxl_stream(self, config: ADXLStreamConfig) -> None:
        """Start streaming from adxl203_ads1115_logger.py."""
        command = build_adxl_command(config)
        self._start_stream(command, mode="adxl")

    # ------------------------------------------------------------------ Internal helpers
    def _start_stream(self, command: str, mode: str) -> None:
        if not self.ssh.is_connected():
            raise RuntimeError("SSHStreamSource: SSH client is not connected")

        self.stop()  # reset previous

        with self._lock:
            self._stop_event.clear()
            self._mode = mode
            self._t0_ns = None
            self._t0_mono_ns = time.monotonic_ns()

            channel, stdout, stderr = self.ssh.exec_command_stream(command)
            self._channel = channel
            self._stdout = stdout
            self._stderr = stderr

            self._thread = threading.Thread(
                target=self._reader_loop,
                name=f"SSHStreamSource-{mode}",
                daemon=True,
            )
            self._thread.start()

            if stderr is not None:
                self._stderr_thread = threading.Thread(
                    target=self._stderr_loop,
                    name=f"SSHStreamSource-stderr-{mode}",
                    daemon=True,
                )
                self._stderr_thread.start()

    def _reader_loop(self) -> None:
        """Background thread: read JSON lines from stdout and dispatch to handlers."""
        stdout = self._stdout
        if stdout is None:
            return

        while not self._stop_event.is_set():
            try:
                line = stdout.readline()
            except Exception:
                break

            if not line:
                break

            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(obj, dict):
                continue

            mode = self._mode
            if mode == "mpu":
                self._handle_mpu_sample(obj)
            elif mode == "adxl":
                self._handle_adxl_sample(obj)
            self._notify_sample(mode)

        status: Optional[int] = None
        channel = self._channel
        if channel is not None:
            try:
                if channel.exit_status_ready() or self._stop_event.is_set():
                    status = channel.recv_exit_status()
            except Exception:
                status = -1
        self._stop_event.set()
        self._notify_exit(status)

    def _stderr_loop(self) -> None:
        """Background thread: drain stderr and forward to log callback."""
        stderr = self._stderr
        if stderr is None:
            return
        for raw_line in iter(stderr.readline, ""):
            if not raw_line:
                break
            line = raw_line.rstrip("\n")
            self._notify_log(f"ERR: {line}")
            if self._stop_event.is_set():
                break
        self._stop_event.set()

    # --------------------------- parsing helpers -----------------------
    def _extract_time_s(self, obj: Dict) -> float:
        """
        Return a time in seconds for this sample.
        Prefer t_s if present; else derive from timestamp_ns; else use local monotonic.
        """
        if "t_s" in obj:
            try:
                return float(obj["t_s"])
            except (TypeError, ValueError):
                pass

        ts_ns = obj.get("timestamp_ns")
        if ts_ns is not None:
            try:
                ts_ns_int = int(ts_ns)
            except Exception:
                ts_ns_int = None
            if ts_ns_int is not None:
                if self._t0_ns is None:
                    self._t0_ns = ts_ns_int
                return (ts_ns_int - self._t0_ns) / 1e9

        if self._t0_mono_ns is None:
            self._t0_mono_ns = time.monotonic_ns()
        return (time.monotonic_ns() - self._t0_mono_ns) / 1e9

    def _update_rate_estimate_locked(self) -> None:
        """Recompute hz_estimate from recent slot 0 timestamps (call with self._lock held)."""
        rb = self._times[0]
        ts = rb.get_last(min(self._rate_window_samples, rb.size))
        if ts.size < 2:
            return
        span = float(ts[-1] - ts[0])
        if span <= 0.0:
            return
        hz = (ts.size - 1) / span
        self._hz_estimate = hz
        self._rate_info.hz_effective = hz

    def _handle_mpu_sample(self, obj: Dict) -> None:
        """Handle one JSON object from mpu6050_multi_logger.py."""
        t_s = self._extract_time_s(obj)
        try:
            sensor_id = int(obj.get("sensor_id", 1))
        except Exception:
            sensor_id = 1

        if sensor_id < 1 or sensor_id > 3:
            return

        base = (sensor_id - 1) * 3  # (0, 3, 6)
        axes = ("ax", "ay", "gz")

        with self._lock:
            for axis_idx, key in enumerate(axes):
                if key not in obj:
                    continue
                try:
                    val = float(obj[key])
                except (TypeError, ValueError):
                    continue

                slot_idx = base + axis_idx
                self._times[slot_idx].push([t_s])
                self._values[slot_idx].push([val])

            if base == 0 and "ax" in obj:
                self._update_rate_estimate_locked()

    def _handle_adxl_sample(self, obj: Dict) -> None:
        """Handle one JSON object from adxl203_ads1115_logger.py."""
        t_s = self._extract_time_s(obj)

        with self._lock:
            if "x_lp" in obj:
                try:
                    vx = float(obj["x_lp"])
                except (TypeError, ValueError):
                    vx = None
                if vx is not None:
                    self._times[0].push([t_s])
                    self._values[0].push([vx])

            if "y_lp" in obj:
                try:
                    vy = float(obj["y_lp"])
                except (TypeError, ValueError):
                    vy = None
                if vy is not None:
                    self._times[1].push([t_s])
                    self._values[1].push([vy])

            if "x_lp" in obj:
                self._update_rate_estimate_locked()

    def _notify_log(self, line: str) -> None:
        callback = self._log_callback
        if callback is None:
            return
        try:
            callback(line)
        except Exception:
            # Avoid breaking the reader thread on UI callback failures.
            pass

    def _notify_sample(self, mode: Optional[str]) -> None:
        callback = self._sample_callback
        if callback is None:
            return
        try:
            callback(mode)
        except Exception:
            pass

    def _notify_exit(self, status: Optional[int]) -> None:
        callback = self._exit_callback
        if callback is None:
            return
        try:
            callback(status)
        except Exception:
            pass


class SSHSource(SSHStreamSource):
    """
    Higher-level DataSource that owns its own SSH client and builds logger commands
    from :class:`SSHSettings`.  It reuses the streaming implementation above so the
    GUI can switch between MQTT and SSH via the same AppState abstraction.
    """

    def __init__(
        self,
        ssh_config: SSHSettings,
        manager_factory=SSHClientManager,
        *,
        maxlen: int = 20000,
        rate_window_samples: int = 512,
    ) -> None:
        self.settings = ssh_config
        self._manager_factory = manager_factory
        mgr = manager_factory() if callable(manager_factory) else SSHClientManager()
        super().__init__(mgr, maxlen=maxlen, rate_window_samples=rate_window_samples)

    # --------------------------- connection helpers -------------------------
    def connect(self) -> None:
        """Ensure the underlying SSH client is connected."""
        if self.ssh.is_connected():
            return
        self.ssh.connect(
            host=self.settings.host,
            port=int(self.settings.port),
            username=self.settings.username,
            password=self.settings.password,
        )

    def disconnect(self) -> None:
        """Close SSH + SFTP connections."""
        self.ssh.disconnect()

    def stop_run(self) -> None:
        """Alias used by SSHTab."""
        self.stop()

    # ------------------------------ DataSource API --------------------------
    def start(self) -> None:
        """
        Connect and start the default stream based on SSHSettings.run_sensor.

        For MQTT parity, repeated calls are idempotent.
        """
        # If a thread is already draining stdout, do nothing.
        if self._thread is not None and self._thread.is_alive():
            return

        self.connect()

        # Decide which logger to launch
        if (self.settings.run_sensor or "").lower() == "adxl":
            self.start_adxl_stream(
                rate_hz=self.settings.rate_hz,
                record=self._record_enabled(),
                live=True,
                stream_every=self.settings.stream_every,
            )
        else:
            self.start_mpu_stream(
                rate_hz=self.settings.rate_hz,
                record=self._record_enabled(),
                live=True,
                stream_every=self.settings.stream_every,
            )

    def stop(self) -> None:
        super().stop()
        # Keep connection open for quick restarts; callers may explicitly disconnect().

    # ---------------------------- public stream helpers ---------------------
    def start_mpu_stream(
        self,
        rate_hz: float | None = None,
        *,
        record: bool = True,
        live: bool = True,
        stream_every: int | None = None,
        sensors: str | None = None,
        channels: str | None = None,
    ) -> None:
        """Start the MPU logger with streaming enabled."""
        self.connect()

        cfg = MPUStreamConfig(
            script_path=self.settings.mpu_script,
            rate_hz=float(rate_hz or self.settings.rate_hz),
            sensors=sensors or "1,2,3",
            channels=channels or "default",
            out_dir=self.settings.remote_out_dir,
            format="csv",
            stream_every=int(stream_every or self.settings.stream_every or 1),
            no_record=not bool(record),
        )

        # Ensure stdout streaming is on even if live=False (the GUI needs it)
        super().start_mpu_stream(cfg)

    def start_adxl_stream(
        self,
        rate_hz: float | None = None,
        *,
        record: bool = True,
        live: bool = True,
        stream_every: int | None = None,
        channels: str | None = None,
        addr: str | None = None,
        chan_map: str | None = None,
        calibrate: int | None = None,
        lp_cut: float | None = None,
    ) -> None:
        """Start the ADXL logger with streaming enabled."""
        self.connect()

        cfg = ADXLStreamConfig(
            script_path=self.settings.adxl_script,
            rate_hz=float(rate_hz or self.settings.rate_hz),
            channels=channels or "both",
            out_dir=self.settings.remote_out_dir,
            addr=addr or "0x48",
            chan_map=chan_map or "x:P0,y:P1",
            calibrate=int(calibrate) if calibrate is not None else 300,
            lp_cut=float(lp_cut) if lp_cut is not None else 15.0,
            stream_every=int(stream_every or self.settings.stream_every or 1),
            no_record=not bool(record),
        )

        super().start_adxl_stream(cfg)

    # ---------------------------- helpers -----------------------------------
    def _record_enabled(self) -> bool:
        mode = (self.settings.run_mode or "").lower()
        return mode in ("record", "record+live")
