from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import os
import threading

import paramiko  # ensure paramiko is installed (already in requirements.txt)


@dataclass
class RemoteRunContext:
    """
    Holds info about a remote sensor run and its outputs.

    This is UI-agnostic and can be used from Tk, Qt, or console scripts.
    """

    command: str
    script_name: str
    sensor_type: str  # "adxl" or "mpu"
    remote_out_dir: str
    local_out_dir: str
    start_snapshot: Dict[str, float] = field(default_factory=dict)


@dataclass
class AdxlParams:
    script_path: str
    rate: float
    channels: str = "both"
    out_dir: str = "/home/verwalter/sensor/logs"
    duration: Optional[float] = None
    addr: Optional[str] = "0x48"
    channel_map: Optional[str] = "x:P0,y:P1"
    calibrate: Optional[int] = 300
    lp_cut: Optional[float] = 15.0


@dataclass
class MpuParams:
    script_path: str
    rate: float
    sensors: str = "1,2,3"
    channels: str = "default"
    out_dir: str = "/home/verwalter/sensor/logs"
    duration: Optional[float] = None
    samples: Optional[int] = None
    fmt: str = "csv"
    prefix: str = "mpu"
    dlpf: Optional[str] = "3"
    temp: bool = False
    flush_every: Optional[int] = 2000
    flush_seconds: Optional[float] = 2.0
    fsync_each_flush: bool = False


RUN_MODE_RECORD_ONLY = "Record only"
RUN_MODE_RECORD_AND_LIVE = "Record + live plot"
RUN_MODE_LIVE_ONLY = "Live plot only (no-record)"


class SSHClientManager:
    """Encapsulates SSH and SFTP connections to the Raspberry Pi."""

    def __init__(self) -> None:
        self.client: Optional[paramiko.SSHClient] = None
        self.sftp: Optional[paramiko.SFTPClient] = None
        self._lock = threading.Lock()

    # ---- connection handling ----
    def connect(
        self,
        host: str,
        port: int,
        username: str,
        password: str = "",
        timeout: float = 10.0,
    ) -> None:
        """Establish SSH + SFTP connections."""
        with self._lock:
            if self.client:
                self.disconnect()

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            ssh.connect(
                hostname=host,
                port=int(port),
                username=username,
                password=password,
                look_for_keys=False,
                allow_agent=False,
                timeout=timeout,
            )
            self.client = ssh
            self.sftp = ssh.open_sftp()

    def disconnect(self) -> None:
        with self._lock:
            if self.sftp:
                try:
                    self.sftp.close()
                except Exception:
                    pass
                self.sftp = None
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None

    def is_connected(self) -> bool:
        return self.client is not None

    # ---- command helpers ----
    def exec_command_stream(self, command: str) -> Tuple[paramiko.Channel, any, any]:
        """
        Execute a command and return (channel, stdout_file, stderr_file)
        so the caller can stream lines as they arrive.
        """
        if not self.client:
            raise RuntimeError("SSH not connected")
        transport = self.client.get_transport()
        if not transport:
            raise RuntimeError("SSH transport not available")
        channel = transport.open_session()
        channel.exec_command(command)
        stdout = channel.makefile("r")
        stderr = channel.makefile_stderr("r")
        return channel, stdout, stderr

    def exec_quick(self, command: str) -> Tuple[str, str, int]:
        """
        Run a short command and return (stdout_str, stderr_str, exit_status).
        """
        if not self.client:
            raise RuntimeError("SSH not connected")
        stdin, stdout, stderr = self.client.exec_command(command)
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        status = stdout.channel.recv_exit_status()
        return out, err, status

    # ---- SFTP helpers ----
    def list_dir(self, remote_dir: str):
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        return self.sftp.listdir_attr(remote_dir)

    def listdir_with_mtime(self, remote_dir: str) -> Dict[str, float]:
        """Return {filename: mtime} for a remote directory."""
        entries = self.list_dir(remote_dir)
        return {entry.filename: float(entry.st_mtime) for entry in entries}

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download one file via SFTP."""
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        local_dir = os.path.dirname(os.path.abspath(local_path))
        os.makedirs(local_dir, exist_ok=True)
        self.sftp.get(remote_path, local_path)


def build_adxl_command(
    params: AdxlParams,
    run_mode: str = RUN_MODE_RECORD_ONLY,
    stream_every: int = 1,
) -> Tuple[str, str]:
    """
    Build the python3 command line for an ADXL203 logger run.

    Returns (command_str, script_name).
    """
    remote_path = params.script_path.strip() or "/home/verwalter/sensor/adxl203_ads1115_logger.py"
    cmd_parts = [
        "python3",
        remote_path,
        "--rate",
        str(params.rate),
        "--channels",
        params.channels,
        "--out",
        params.out_dir,
    ]

    if params.duration is not None:
        cmd_parts += ["--duration", str(params.duration)]
    if params.addr:
        cmd_parts += ["--addr", str(params.addr)]
    if params.channel_map:
        cmd_parts += ["--map", params.channel_map]
    if params.calibrate is not None:
        cmd_parts += ["--calibrate", str(params.calibrate)]
    if params.lp_cut is not None:
        cmd_parts += ["--lp-cut", str(params.lp_cut)]

    if run_mode in (RUN_MODE_RECORD_AND_LIVE, RUN_MODE_LIVE_ONLY):
        if run_mode == RUN_MODE_LIVE_ONLY:
            cmd_parts.append("--no-record")
        cmd_parts.append("--stream-stdout")
        cmd_parts += ["--stream-every", str(int(max(1, stream_every)))]
        cmd_parts += ["--stream-fields", "x_lp,y_lp"]

    script_name = os.path.basename(remote_path) or "adxl203_ads1115_logger.py"
    return " ".join(cmd_parts), script_name


def build_mpu_command(
    params: MpuParams,
    run_mode: str = RUN_MODE_RECORD_ONLY,
    stream_every: int = 1,
) -> Tuple[str, str]:
    """
    Build the python3 command line for an MPU6050 multi-sensor logger run.

    Returns (command_str, script_name).
    """
    remote_path = params.script_path.strip() or "/home/verwalter/sensor/mpu6050_multi_logger.py"
    cmd_parts = [
        "python3",
        remote_path,
        "--rate",
        str(params.rate),
        "--sensors",
        params.sensors,
        "--channels",
        params.channels,
        "--out",
        params.out_dir,
        "--format",
        params.fmt,
    ]

    if params.duration is not None:
        cmd_parts += ["--duration", str(params.duration)]
    if params.samples is not None:
        cmd_parts += ["--samples", str(params.samples)]
    if params.prefix:
        cmd_parts += ["--prefix", params.prefix]
    if params.dlpf:
        cmd_parts += ["--dlpf", str(params.dlpf)]
    if params.temp:
        cmd_parts.append("--temp")
    if params.flush_every is not None:
        cmd_parts += ["--flush-every", str(params.flush_every)]
    if params.flush_seconds is not None:
        cmd_parts += ["--flush-seconds", str(params.flush_seconds)]
    if params.fsync_each_flush:
        cmd_parts.append("--fsync-each-flush")

    if run_mode in (RUN_MODE_RECORD_AND_LIVE, RUN_MODE_LIVE_ONLY):
        if run_mode == RUN_MODE_LIVE_ONLY:
            cmd_parts.append("--no-record")
        cmd_parts.append("--stream-stdout")
        cmd_parts += ["--stream-every", str(int(max(1, stream_every)))]
        cmd_parts += ["--stream-fields", "ax,ay,gz"]

    script_name = os.path.basename(remote_path) or "mpu6050_multi_logger.py"
    return " ".join(cmd_parts), script_name
