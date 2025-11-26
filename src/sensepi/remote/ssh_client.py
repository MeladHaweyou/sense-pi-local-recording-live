"""Lightweight SSH client wrapper for Raspberry Pi control."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

import logging
import paramiko
import shlex
import threading


logger = logging.getLogger(__name__)


@dataclass
class SSHConfig:
    """Simple SSH connection settings for password-based auth only."""

    host: str
    username: str
    port: int = 22
    password: Optional[str] = None


@dataclass
class Host:
    """Connection details for a Raspberry Pi host (password-based auth only)."""

    name: str
    host: str
    user: str
    password: Optional[str] = None
    port: int = 22


class SSHClient:
    """Simple wrapper around ``paramiko`` for running remote commands."""

    def __init__(self, host: Host) -> None:
        self.host = host
        self._client: paramiko.SSHClient = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # ------------------------------------------------------------------ internals
    def _ensure_client(self) -> paramiko.SSHClient:
        transport = self._client.get_transport()
        if not (transport and transport.is_active()):
            self.connect()
        return self._client

    # ------------------------------------------------------------------ connection
    def connect(self) -> None:
        transport = self._client.get_transport()
        if transport and transport.is_active():
            return

        logger.info(
            "Connecting to %s@%s:%s", self.host.user, self.host.host, self.host.port
        )

        self._client.connect(
            hostname=self.host.host,
            username=self.host.user,
            port=self.host.port,
            password=self.host.password,
            look_for_keys=False,
            allow_agent=False,
            timeout=10.0,
        )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ commands
    def run(self, command: str):
        """
        Execute a command over SSH and return stdin, stdout, stderr.

        This is a thin wrapper around :meth:`paramiko.SSHClient.exec_command`.
        """
        client = self._ensure_client()
        return client.exec_command(command)

    @contextmanager
    def sftp(self) -> Iterator[paramiko.SFTPClient]:
        """Context manager that yields an SFTP client."""

        client = self._ensure_client()
        sftp = client.open_sftp()
        try:
            yield sftp
        finally:
            try:
                sftp.close()
            except Exception:
                pass

    def path_exists(self, remote_path: str) -> bool:
        """Return True if *remote_path* exists on the Pi."""

        with self.sftp() as sftp:
            try:
                sftp.stat(remote_path)
            except IOError:
                return False
            else:
                return True

    def exec_stream(
        self,
        command: str,
        cwd: Optional[str] = None,
        encoding: str = "utf-8",
        errors: str = "ignore",
        stderr_callback: Optional[callable] = None,
    ) -> Iterable[str]:
        """
        Run a long-lived command and yield stdout lines as they arrive.

        If stderr_callback is provided, stderr lines are forwarded to it.
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
            # Optional stderr watcher in a background thread
            if stderr_callback is not None:
                def _watch_stderr():
                    try:
                        for raw_err in iter(lambda: stderr.readline(), ""):
                            if not raw_err:
                                break
                            if isinstance(raw_err, bytes):
                                text_err = raw_err.decode(encoding, errors=errors)
                            else:
                                text_err = raw_err
                            text_err = text_err.rstrip("\r\n")
                            if text_err:
                                stderr_callback(text_err)
                    except Exception:
                        # Don't crash on stderr issues
                        logger.exception("Error reading remote stderr")

                threading.Thread(target=_watch_stderr, daemon=True).start()

            try:
                for raw in iter(lambda: stdout.readline(), ""):
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
