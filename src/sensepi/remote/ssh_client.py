"""Lightweight SSH client wrapper for Raspberry Pi control."""

from dataclasses import dataclass
from typing import Optional

import paramiko


@dataclass
class Host:
    """Connection details for a Raspberry Pi host."""

    name: str
    host: str
    user: str
    ssh_key: Optional[str] = None
    port: int = 22


class SSHClient:
    """Simple wrapper around ``paramiko`` for running remote commands."""

    def __init__(self, host: Host) -> None:
        self.host = host
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    def connect(self) -> None:
        key = paramiko.RSAKey.from_private_key_file(self.host.ssh_key) if self.host.ssh_key else None
        self._client.connect(
            hostname=self.host.host,
            username=self.host.user,
            port=self.host.port,
            pkey=key,
        )

    def run(self, command: str):
        """Execute a command over SSH and return stdin, stdout, stderr."""
        return self._client.exec_command(command)

    def close(self) -> None:
        self._client.close()
