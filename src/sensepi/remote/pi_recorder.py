from __future__ import annotations

"""High-level helpers for starting and stopping logger scripts on the Pi."""

from dataclasses import dataclass
from typing import Iterable, Optional

from .ssh_client import SSHClient, SSHConfig


@dataclass
class RecorderStatus:
    """Simple container for the PIDs of running loggers."""

    mpu6050_pid: Optional[int] = None
    adxl203_pid: Optional[int] = None


class PiRecorder:
    """
    High-level helper that knows how to start/stop the sensor logger scripts
    on the Raspberry Pi over SSH.

    It assumes that on the Pi you have the scripts in a single directory, e.g.:

        ~/sense-pi/raspberrypi_scripts/mpu6050_multi_logger.py
        ~/sense-pi/raspberrypi_scripts/adxl203_ads1115_logger.py

    You can point ``scripts_dir`` at whatever path you actually use.
    """

    def __init__(
        self,
        ssh_config: SSHConfig,
        scripts_dir: str = "~/sense-pi/raspberrypi_scripts",
        python_cmd: str = "python3",
    ) -> None:
        self.ssh = SSHClient(ssh_config)
        self.scripts_dir = scripts_dir
        self.python_cmd = python_cmd
        self.status = RecorderStatus()

    # ---------------------------- connection -----------------------------
    def connect(self) -> None:
        """Establish the SSH connection if not already connected."""
        self.ssh.connect()

    def disconnect(self) -> None:
        """Close the SSH connection if open."""
        self.ssh.close()

    # ----------------------------- helpers ------------------------------
    def _build_command(self, script_name: str, extra_args: str = "") -> str:
        cmd = f"{self.python_cmd} {script_name}"
        if extra_args:
            cmd = f"{cmd} {extra_args}"
        return cmd.strip()

    # ------------------------- generic launcher -------------------------
    def start_logger(self, script_name: str, args: Optional[Iterable[str]] = None) -> int:
        """
        Start an arbitrary Python logger script in the background.

        Returns the PID of the spawned process so callers may manage it.
        """
        extra_args = ""
        if args:
            extra_args = " ".join(str(a) for a in args)
        cmd = self._build_command(script_name, extra_args)
        return self.ssh.exec_background(cmd, cwd=self.scripts_dir)

    # ---------------------------- MPU6050 -----------------------------
    def start_mpu6050(self, extra_args: str = "") -> int:
        """
        Start the MPU6050 logger on the Pi.

        `extra_args` lets you pass things like '--log-dir /home/pi/logs/mpu'
        without hard-coding the exact CLI here.
        """
        cmd = self._build_command("mpu6050_multi_logger.py", extra_args)
        pid = self.ssh.exec_background(cmd, cwd=self.scripts_dir)
        self.status.mpu6050_pid = pid
        return pid

    def stop_mpu6050(self) -> bool:
        """
        Stop the MPU6050 logger if it is running.

        Returns True if we *think* we stopped a process, False if there was
        no known PID.
        """
        pid = self.status.mpu6050_pid
        if pid is None:
            return False

        self.ssh.kill(pid)
        self.status.mpu6050_pid = None
        return True

    def is_mpu6050_running(self) -> bool:
        pid = self.status.mpu6050_pid
        if pid is None:
            return False
        return self.ssh.is_running(pid)

    # ---------------------------- ADXL203 -----------------------------
    def start_adxl203(self, extra_args: str = "") -> int:
        """
        Start the ADXL203/ADS1115 logger on the Pi.

        Again, `extra_args` is a free-form CLI string, so you can adjust the
        recording settings without changing this module.
        """
        cmd = self._build_command("adxl203_ads1115_logger.py", extra_args)
        pid = self.ssh.exec_background(cmd, cwd=self.scripts_dir)
        self.status.adxl203_pid = pid
        return pid

    def stop_adxl203(self) -> bool:
        pid = self.status.adxl203_pid
        if pid is None:
            return False

        self.ssh.kill(pid)
        self.status.adxl203_pid = None
        return True

    def is_adxl203_running(self) -> bool:
        pid = self.status.adxl203_pid
        if pid is None:
            return False
        return self.ssh.is_running(pid)
