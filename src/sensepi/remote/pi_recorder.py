"""High-level helpers for starting and streaming logger scripts on the Pi."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Optional

from .ssh_client import Host, SSHClient


class PiRecorder:
    """Launches Raspberry Pi logger scripts over SSH."""

    def __init__(self, host: Host, base_path: Optional[Path] = None) -> None:
        self.host = host
        if base_path is None:
            base_path = Path("/home/verwalter/sensor")

        # Ensure the remote path is always POSIX-style, even on Windows hosts.
        base_path = Path(base_path)
        self.base_path = PurePosixPath(base_path.as_posix())
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
        streaming use :meth:`stream_mpu6050`.
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
        *,
        recording: bool = False,
    ) -> Iterable[str]:
        """
        Internal helper: start a logger in ``--stream-stdout`` mode.

        ``extra_args`` is a free-form CLI string; this helper will append
        ``--stream-stdout`` and optionally ``--no-record`` depending on ``recording``.
        """
        self.connect()

        parts = extra_args.strip().split() if extra_args.strip() else []

        if "--stream-stdout" not in parts:
            parts.append("--stream-stdout")

        wants_recording = recording or ("--record" in parts)

        # Ensure we don't accidentally send both flags
        parts = [p for p in parts if p != "--no-record"]

        if not wants_recording and "--no-record" not in parts:
            parts.append("--no-record")

        cmd = f"python3 {script_name}"
        if parts:
            cmd = f"{cmd} {' '.join(parts)}"

        # Use cwd so the script can rely on relative paths.
        cwd = self.base_path.as_posix()
        return self.client.exec_stream(cmd, cwd=cwd, stderr_callback=on_stderr)

    def stream_mpu6050(
        self,
        extra_args: str = "",
        *,
        recording: bool = False,
        on_stderr: Optional[Callable[[str], None]] = None,
    ) -> Iterable[str]:
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
            recording=recording,
        )

    # ------------------------------------------------------------------ convenience
    def stop(self) -> None:
        """Alias for :meth:`close` to match older code."""
        self.close()
