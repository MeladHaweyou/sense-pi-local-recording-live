from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ssh_client import SSHClient, SSHConfig


@dataclass
class RecorderStatus:
    mpu6050_pid: Optional[int] = None
    adxl203_pid: Optional[int] = None


class PiRecorder:
    """
    High-level helper that knows how to start/stop the sensor logger scripts
    on the Raspberry Pi over SSH.

    It assumes that on the Pi you have the scripts in a single directory, e.g.:

        ~/sense-pi/raspberrypi_scripts/mpu6050_multi_logger.py
        ~/sense-pi/raspberrypi_scripts/adxl203_ads1115_logger.py

    You can point `scripts_dir` at whatever path you actually use.
    """

    def __init__(
        self,
        ssh_config: SSHConfig,
        scripts_dir: str = "~/sense-pi/raspberrypi_scripts",
        python_cmd: str = "python3",
    ):
        self.ssh = SSHClient(ssh_config)
        self.scripts_dir = scripts_dir
        self.python_cmd = python_cmd
        self.status = RecorderStatus()

    # ---------------------------- connection -----------------------------
    def connect(self) -> None:
        self.ssh.connect()

    def disconnect(self) -> None:
        self.ssh.close()

    # ---------------------------- MPU6050 -----------------------------
    def start_mpu6050(self, extra_args: str = "") -> int:
        """
        Start the MPU6050 logger on the Pi.

        `extra_args` lets you pass things like '--log-dir /home/pi/logs/mpu'
        without hard-coding the exact CLI here.
        """
        cmd = f"{self.python_cmd} mpu6050_multi_logger.py {extra_args}".strip()
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
        cmd = f"{self.python_cmd} adxl203_ads1115_logger.py {extra_args}".strip()
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
