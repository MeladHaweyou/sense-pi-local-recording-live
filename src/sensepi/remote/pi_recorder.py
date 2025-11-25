"""High-level helpers for starting and streaming logger scripts on the Pi."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Optional

from .ssh_client import Host, SSHClient


class PiRecorder:
    """Launches Raspberry Pi logger scripts over SSH."""

    def __init__(self, host: Host, base_path: Optional[Path] = None) -> None:
        self.host = host
        self.base_path = base_path or Path("/home/pi/raspberrypi_scripts")
        self.client = SSHClient(host)

    # ------------------------------------------------------------------ connection
    def connect(self) -> None:
        """Ensure an SSH connection is open."""
        self.client.connect()

    def close(self) -> None:
        """Close the SSH connection (does not kill remote loggers)."""
        self.client.close()

    # ------------------------------------------------------------------ simple runner
    def start_logger(
        self, script_name: str, args: Optional[Iterable[str]] = None
    ):
        """
        Run a logger script and return (stdout, stderr) file-like objects.

        This is mainly useful for short-lived commands or testing; for live
        streaming use :meth:`stream_mpu6050` / :meth:`stream_adxl203`.
        """
        command = f"python3 {self.base_path / script_name}"
        if args:
            command = " ".join([command, *args])

        self.connect()
        _, stdout, stderr = self.client.run(command)
        return stdout, stderr

    # ------------------------------------------------------------------ streaming
    def _stream_logger(
        self,
        script_name: str,
        extra_args: str = "",
        on_stderr: Optional[Callable[[str], None]] = None,
    ):
        """
        Internal helper: start a logger in ``--stream-stdout`` mode.

        ``extra_args`` is a free-form CLI string; this helper will append
        ``--stream-stdout`` and ``--no-record`` if they are not already present.
        """
        self.connect()

        parts = extra_args.strip().split() if extra_args.strip() else []

        if "--stream-stdout" not in parts:
            parts.append("--stream-stdout")
        if "--no-record" not in parts:
            parts.append("--no-record")

        cmd = f"python3 {script_name}"
        if parts:
            cmd = f"{cmd} {' '.join(parts)}"

        # Use cwd so the script can rely on relative paths.
        return self.client.exec_stream(
            cmd,
            cwd=str(self.base_path),
            stderr_callback=on_stderr,
        )

    def stream_mpu6050(
        self,
        extra_args: str = "",
        on_stderr: Optional[Callable[[str], None]] = None,
    ):
        """
        Start the MPU6050 logger in streaming mode.

        Internally builds a command like:

            python3 mpu6050_multi_logger.py --rate ... --stream-stdout --no-record ...

        and returns an iterable of JSON lines.
        """
        return self._stream_logger(
            "mpu6050_multi_logger.py",
            extra_args,
            on_stderr=on_stderr,
        )

    def stream_adxl203(
        self,
        extra_args: str = "",
        on_stderr: Optional[Callable[[str], None]] = None,
    ):
        """
        Start the ADXL203/ADS1115 logger in streaming mode.

        Internally builds a command like:

            python3 adxl203_ads1115_logger.py --rate ... --stream-stdout --no-record ...

        and returns an iterable of JSON lines.
        """
        return self._stream_logger(
            "adxl203_ads1115_logger.py",
            extra_args,
            on_stderr=on_stderr,
        )

    # ------------------------------------------------------------------ convenience
    def stop(self) -> None:
        """Alias for :meth:`close` to match older code."""
        self.close()
