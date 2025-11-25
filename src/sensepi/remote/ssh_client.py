from __future__ import annotations

"""Lightweight SSH client wrapper for Raspberry Pi control.

This module provides the canonical SSH API for the project. It is used by
both the GUI layer and any orchestration code.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import logging
import shlex

import paramiko

logger = logging.getLogger(__name__)


@dataclass
class SSHConfig:
    """Connection details for a remote host."""

    host: str
    username: str
    port: int = 22
    password: Optional[str] = None
    key_filename: Optional[str] = None


class SSHClient:
    """
    Small convenience wrapper around paramiko.SSHClient.

    This keeps a single connection open and exposes:

      * exec()          - run a command and wait for it to finish
      * exec_background - start a long-running command with nohup and get its PID
      * is_running()    - check if a PID is still running
      * kill()          - send SIGTERM to a PID
    """

    def __init__(self, config: SSHConfig) -> None:
        self.config = config
        self._client: Optional[paramiko.SSHClient] = None

    # ----------------------------- connection -----------------------------
    def connect(self) -> None:
        """Open the SSH connection if it is not already open."""
        if self._client is not None:
            return

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        logger.info(
            "Connecting to %s@%s:%s",
            self.config.username,
            self.config.host,
            self.config.port,
        )

        client.connect(
            hostname=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
            key_filename=self.config.key_filename,
            look_for_keys=self.config.key_filename is None,
            allow_agent=True,
            timeout=10.0,
        )

        self._client = client

    def close(self) -> None:
        """Close the SSH connection if open."""
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    # ------------------------------ helpers -------------------------------
    def _ensure_connected(self) -> paramiko.SSHClient:
        if self._client is None:
            self.connect()
        assert self._client is not None
        return self._client

    # ----------------------------- commands -------------------------------
    def exec(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[int, str, str]:
        """
        Run a command and wait for it to complete.

        Returns: (exit_status, stdout, stderr)
        """
        client = self._ensure_connected()

        full_cmd = command
        if cwd:
            full_cmd = f"cd {shlex.quote(cwd)} && {command}"

        logger.debug("SSH exec: %s", full_cmd)

        stdin, stdout, stderr = client.exec_command(full_cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="ignore")
        err = stderr.read().decode("utf-8", errors="ignore")
        exit_status = stdout.channel.recv_exit_status()

        logger.debug(
            "SSH exit status=%s, stdout=%r, stderr=%r", exit_status, out, err
        )

        return exit_status, out, err

    def exec_background(self, command: str, cwd: Optional[str] = None) -> int:
        """
        Start a long-running command with nohup and return its PID.

        The command will keep running after the SSH session that started it ends.
        """
        client = self._ensure_connected()

        base_cmd = command
        if cwd:
            base_cmd = f"cd {shlex.quote(cwd)} && {command}"

        # Redirect all output so the process is fully detached from the SSH channel.
        full_cmd = f"nohup {base_cmd} > /dev/null 2>&1 & echo $!"

        logger.debug("SSH exec_background: %s", full_cmd)

        stdin, stdout, stderr = client.exec_command(full_cmd)
        out = stdout.read().decode("utf-8", errors="ignore")
        err = stderr.read().decode("utf-8", errors="ignore")
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            raise RuntimeError(
                f"Failed to start background command: {full_cmd}\n"
                f"stdout: {out}\n"
                f"stderr: {err}"
            )

        # The PID should be the last non-empty line of stdout
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError(
                "No PID returned when starting background command:\n"
                f"cmd: {full_cmd}\nstdout: {out}"
            )

        pid_str = lines[-1]
        try:
            pid = int(pid_str)
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid PID returned from background command: {pid_str!r}"
            ) from exc

        logger.info("Started background command with PID %s", pid)
        return pid

    def is_running(self, pid: int) -> bool:
        """
        Check if a process with this PID is still running on the remote host.
        """
        cmd = f"ps -p {pid} -o pid="
        status, out, _ = self.exec(cmd)
        return status == 0 and out.strip() != ""

    def kill(self, pid: int) -> None:
        """
        Send SIGTERM to a PID on the remote host.
        """
        cmd = f"kill {pid}"
        status, _, err = self.exec(cmd)
        if status != 0:
            raise RuntimeError(f"Failed to kill PID {pid}: {err}")
