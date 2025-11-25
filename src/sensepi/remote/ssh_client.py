"""Lightweight SSH client wrapper for Raspberry Pi control."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

import paramiko
import shlex


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
        self._client: Optional[paramiko.SSHClient] = None

    # ------------------------------------------------------------------ internals
    def _ensure_client(self) -> paramiko.SSHClient:
        if self._client is None:
            self.connect()
        assert self._client is not None
        return self._client

    # ------------------------------------------------------------------ connection
    def connect(self) -> None:
        if self._client is not None:
            # Already connected
            return

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        key = (
            paramiko.RSAKey.from_private_key_file(self.host.ssh_key)
            if self.host.ssh_key
            else None
        )

        client.connect(
            hostname=self.host.host,
            username=self.host.user,
            port=self.host.port,
            pkey=key,
        )

        self._client = client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    # ------------------------------------------------------------------ commands
    def run(self, command: str):
        """
        Execute a command over SSH and return stdin, stdout, stderr.

        This is a thin wrapper around :meth:`paramiko.SSHClient.exec_command`.
        """
        client = self._ensure_client()
        return client.exec_command(command)

    def exec_stream(
        self,
        command: str,
        cwd: Optional[str] = None,
        encoding: str = "utf-8",
        errors: str = "ignore",
    ) -> Iterable[str]:
        """
        Run a long-lived command and yield stdout lines as they arrive.

        The caller is responsible for breaking the loop when done.
        When the remote process exits (or the iterable is closed),
        the underlying SSH channel is cleaned up.
        """
        client = self._ensure_client()

        full_cmd = command
        if cwd:
            full_cmd = f"cd {shlex.quote(cwd)} && {command}"

        stdin, stdout, stderr = client.exec_command(full_cmd)

        def _iter_lines() -> Iterator[str]:
            try:
                while True:
                    raw = stdout.readline()
                    if not raw:
                        break
                    if isinstance(raw, bytes):
                        text = raw.decode(encoding, errors=errors)
                    else:
                        text = raw
                    yield text.rstrip("\r\n")
            finally:
                try:
                    stdout.channel.close()
                except Exception:
                    pass
                try:
                    stdin.close()
                except Exception:
                    pass
                try:
                    stderr.close()
                except Exception:
                    pass

        return _iter_lines()
