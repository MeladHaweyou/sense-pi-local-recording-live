from __future__ import annotations

import os
import threading
from typing import Dict, Optional, Tuple

import paramiko


class SSHClientManager:
    """
    Thin wrapper around paramiko.SSHClient for reuse from the Qt data layer.

    Responsibilities:
      - Connect / disconnect to a single remote host.
      - Provide exec_command_stream() for long-running commands (JSON streaming).
      - Provide exec_quick() for short, fire-and-forget commands.
      - Provide simple SFTP helpers (listdir + download_file).

    This class is deliberately GUI-agnostic so it can be reused by both
    Tk and Qt code.
    """

    def __init__(self) -> None:
        self.client: Optional[paramiko.SSHClient] = None
        self.sftp: Optional[paramiko.SFTPClient] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ connection
    def connect(
        self,
        host: str,
        port: int,
        username: str,
        password: str = "",
        pkey_path: Optional[str] = None,
    ) -> None:
        """
        Establish SSH + SFTP connections.

        Either password or pkey_path may be used. If pkey_path is given, it is
        passed to paramiko as key_filename and password is ignored.
        """
        with self._lock:
            if self.client:
                self.disconnect()

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            kwargs = {"hostname": host, "port": int(port), "username": username}
            if pkey_path:
                kwargs["key_filename"] = pkey_path
            else:
                kwargs["password"] = password

            ssh.connect(
                **kwargs,
                look_for_keys=not bool(pkey_path),
                allow_agent=False,
                timeout=10,
            )

            self.client = ssh
            self.sftp = ssh.open_sftp()

    def disconnect(self) -> None:
        """Close SFTP and SSH connections if they are open."""
        with self._lock:
            if self.sftp is not None:
                try:
                    self.sftp.close()
                except Exception:
                    pass
                self.sftp = None

            if self.client is not None:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None

    def is_connected(self) -> bool:
        """Return True if an SSH client is currently connected."""
        return self.client is not None

    # ------------------------------------------------------------------ execution helpers
    def exec_command_stream(self, command: str):
        """
        Execute a long-running command and return (channel, stdout, stderr)
        for streaming.

        stdout / stderr are text file-like objects; the caller typically reads
        stdout line-by-line in a background thread.
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
        Run a short command and return (stdout, stderr, exit_status).

        This is for non-streaming tasks like pkill, ls, etc.
        """
        if not self.client:
            raise RuntimeError("SSH not connected")

        stdin, stdout, stderr = self.client.exec_command(command)
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        status = stdout.channel.recv_exit_status()
        return out, err, status

    # ------------------------------------------------------------------ SFTP helpers
    def list_dir(self, remote_dir: str):
        """Return the raw SFTP attributes for a remote directory."""
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        return self.sftp.listdir_attr(remote_dir)

    def listdir_with_mtime(self, remote_dir: str) -> Dict[str, float]:
        """
        Convenience helper returning {filename: mtime} for a remote directory.
        """
        entries = self.list_dir(remote_dir)
        return {entry.filename: entry.st_mtime for entry in entries}

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a single file via SFTP, creating local directories if needed."""
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        local_dir = os.path.dirname(local_path)
        if local_dir:
            os.makedirs(local_dir, exist_ok=True)
        self.sftp.get(remote_path, local_path)
