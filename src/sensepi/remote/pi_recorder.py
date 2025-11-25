"""High-level helpers for starting and stopping logger scripts on the Pi."""

from pathlib import Path
from typing import Iterable, Optional

from .ssh_client import Host, SSHClient


class PiRecorder:
    """Launches Raspberry Pi logger scripts over SSH."""

    def __init__(self, host: Host, base_path: Optional[Path] = None) -> None:
        self.host = host
        self.base_path = base_path or Path("/home/pi/raspberrypi_scripts")
        self.client = SSHClient(host)

    def start_logger(self, script_name: str, args: Optional[Iterable[str]] = None):
        command = f"python3 {self.base_path / script_name}"
        if args:
            command = " ".join([command, *args])
        self.client.connect()
        _, stdout, stderr = self.client.run(command)
        return stdout, stderr

    def stop(self) -> None:
        self.client.close()
