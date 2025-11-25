from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict

from PySide6.QtCore import QObject, QThread, Signal

from .ssh_manager import SSHClientManager


@dataclass
class RemoteRunContextQt:
    """Qt-specific run context for tracking new files after a run."""

    remote_out_dir: str
    local_out_dir: str
    start_snapshot: Dict[str, float]


class DownloadSignals(QObject):
    """Container for worker signals."""

    log = Signal(str)
    result = Signal(int, str, bool, str)  # n_files, timestamp, ok, error_msg


class AutoDownloadWorker(QThread):
    """
    Background worker: diff remote dir vs. start snapshot and download only new files.
    """

    def __init__(
        self,
        manager: SSHClientManager,
        ctx: RemoteRunContextQt,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self.ctx = ctx
        self.signals = DownloadSignals()

    def run(self) -> None:  # noqa: D401
        """Entry point for the QThread."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.signals.log.emit(
                f"Run finished. Scanning {self.ctx.remote_out_dir} for new files..."
            )
            end_snapshot = self.manager.listdir_with_mtime(self.ctx.remote_out_dir)
            new_files: list[tuple[str, float]] = []
            for name, mtime in end_snapshot.items():
                old_mtime = self.ctx.start_snapshot.get(name)
                if old_mtime is None or mtime > old_mtime + 1e-6:
                    new_files.append((name, mtime))

            if not new_files:
                self.signals.log.emit("No new files to download.")
                self.signals.result.emit(0, timestamp, True, "")
                return

            os.makedirs(self.ctx.local_out_dir, exist_ok=True)
            for fname, _ in sorted(new_files, key=lambda x: x[1]):
                remote_path = f"{self.ctx.remote_out_dir.rstrip('/')}/{fname}"
                local_path = os.path.join(self.ctx.local_out_dir, fname)
                self.manager.download_file(remote_path, local_path)
                self.signals.log.emit(f"Downloaded {fname} -> {local_path}")

            self.signals.result.emit(len(new_files), timestamp, True, "")
        except Exception as exc:  # pragma: no cover - defensive
            self.signals.log.emit(f"[ERROR] Auto-download failed: {exc}")
            self.signals.result.emit(0, timestamp, False, str(exc))


class DownloadNewestWorker(QThread):
    """
    Background worker: download the newest N files by mtime.
    """

    def __init__(
        self,
        manager: SSHClientManager,
        remote_dir: str,
        local_dir: str,
        max_files: int = 5,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self.remote_dir = remote_dir
        self.local_dir = local_dir
        self.max_files = max_files
        self.signals = DownloadSignals()

    def run(self) -> None:  # noqa: D401
        """Entry point for the QThread."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            snap = self.manager.listdir_with_mtime(self.remote_dir)
            items = sorted(snap.items(), key=lambda e: e[1], reverse=True)[: self.max_files]
            if not items:
                self.signals.log.emit("No files found to download.")
                self.signals.result.emit(0, timestamp, True, "")
                return

            os.makedirs(self.local_dir, exist_ok=True)
            for name, _ in items:
                remote_path = f"{self.remote_dir.rstrip('/')}/{name}"
                local_path = os.path.join(self.local_dir, name)
                self.manager.download_file(remote_path, local_path)
                self.signals.log.emit(f"Downloaded {name} -> {local_path}")

            self.signals.result.emit(len(items), timestamp, True, "")
        except Exception as exc:  # pragma: no cover - defensive
            self.signals.log.emit(f"[ERROR] Manual download failed: {exc}")
            self.signals.result.emit(0, timestamp, False, str(exc))
