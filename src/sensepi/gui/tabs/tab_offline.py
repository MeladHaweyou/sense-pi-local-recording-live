from __future__ import annotations

import re
import stat
from pathlib import Path
from typing import Iterable, Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from ...config.app_config import AppPaths
from ...remote.ssh_client import SSHClient
from ...tools import plotter

if TYPE_CHECKING:
    from .tab_recorder import RecorderTab


class OfflineTab(QWidget):
    """Offline log viewer built on the shared plotter helpers."""

    def __init__(
        self,
        app_paths: AppPaths,
        recorder_tab: "RecorderTab | None" = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._paths = app_paths
        self._paths.ensure()
        self._recorder_tab = recorder_tab

        self._canvas: FigureCanvasQTAgg | None = None

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Recent logs:"))
        self.btn_refresh = QPushButton("Refresh")
        self.btn_sync = QPushButton("Sync logs from Pi")
        self.btn_browse = QPushButton("Browse…")
        top_row.addWidget(self.btn_refresh)
        top_row.addWidget(self.btn_sync)
        top_row.addWidget(self.btn_browse)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.file_list = QListWidget(self)
        layout.addWidget(self.file_list)

        self.status_label = QLabel("Select a log file to view.", self)
        layout.addWidget(self.status_label)

        self.setLayout(layout)

        self.btn_refresh.clicked.connect(self._populate_files)
        self.btn_browse.clicked.connect(self._on_browse)
        self.btn_sync.clicked.connect(self._on_sync_from_pi_clicked)
        self.file_list.itemDoubleClicked.connect(self._on_open_selected)

        self._populate_files()

    def _populate_files(self) -> None:
        self.file_list.clear()
        for path in self._candidate_logs():
            self.file_list.addItem(str(path))

    def _session_slug(self) -> str:
        recorder = getattr(self, "_recorder_tab", None)
        if recorder is None:
            return ""
        try:
            session = recorder.last_session_name()
        except AttributeError:
            return ""
        session = (session or "").strip()
        if not session:
            return ""
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", session)
        slug = slug.strip("-_.")
        return slug[:64]

    def _local_sync_root(self, host_label: str) -> Path:
        base = self._paths.raw_data
        slug = self._session_slug()
        if slug:
            return base / slug
        if host_label:
            return base / host_label
        return base

    def _resolve_remote_context(self):
        recorder = getattr(self, "_recorder_tab", None)
        if recorder is None:
            return None
        try:
            details = recorder.current_host_details()
        except AttributeError:
            return None
        if not details:
            return None
        host, cfg = details
        remote_dir = cfg.data_dir.expanduser().as_posix()
        return host, remote_dir, cfg.name

    def _download_remote_logs(
        self, client: SSHClient, remote_root: str, local_root: Path
    ) -> int:
        remote_root = remote_root.rstrip("/") or "/"
        allowed_ext = {".csv", ".jsonl", ".json"}
        downloaded = 0
        stack: list[tuple[str, Path]] = [(remote_root, local_root)]
        with client.sftp() as sftp:
            try:
                sftp.listdir(remote_root)
            except IOError as exc:
                raise RuntimeError(
                    f"Remote directory {remote_root} not found"
                ) from exc
            while stack:
                remote_dir, local_dir = stack.pop()
                try:
                    entries = sftp.listdir_attr(remote_dir)
                except IOError:
                    continue
                for entry in entries:
                    remote_path = f"{remote_dir.rstrip('/')}/{entry.filename}" if remote_dir != "/" else f"/{entry.filename}"
                    local_path = local_dir / entry.filename
                    mode = entry.st_mode
                    if stat.S_ISDIR(mode):
                        local_path.mkdir(parents=True, exist_ok=True)
                        stack.append((remote_path, local_path))
                        continue
                    if not stat.S_ISREG(mode):
                        continue
                    if local_path.suffix.lower() not in allowed_ext:
                        continue
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    should_skip = False
                    if local_path.exists():
                        try:
                            should_skip = local_path.stat().st_size == entry.st_size
                        except FileNotFoundError:
                            should_skip = False
                    if should_skip:
                        continue
                    sftp.get(remote_path, str(local_path))
                    downloaded += 1
        return downloaded

    def _candidate_logs(self) -> Iterable[Path]:
        roots = [
            self._paths.raw_data,
            self._paths.processed_data,
            self._paths.logs,
        ]
        candidates: dict[Path, float] = {}
        patterns = ("*.csv", "*.jsonl")
        for root in roots:
            if not root.exists():
                continue
            for pattern in patterns:
                for path in root.glob(pattern):
                    try:
                        candidates[path] = path.stat().st_mtime
                    except FileNotFoundError:
                        continue
        for path in sorted(candidates, key=candidates.get, reverse=True):
            yield path

    @Slot()
    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select log file",
            str(self._paths.raw_data),
            "Logs (*.csv *.jsonl)",
        )
        if path:
            self.load_file(Path(path))

    @Slot()
    def _on_open_selected(self) -> None:
        item = self.file_list.currentItem()
        if not item:
            return
        self.load_file(Path(item.text()))

    @Slot()
    def _on_sync_from_pi_clicked(self) -> None:
        context = self._resolve_remote_context()
        if context is None:
            QMessageBox.information(
                self,
                "Sync logs",
                "Select a Raspberry Pi host in the Signals tab first.",
            )
            return
        host, remote_dir, host_label = context
        if not remote_dir:
            QMessageBox.warning(
                self,
                "Sync logs",
                "The selected host does not define a data directory.",
            )
            return

        client = SSHClient(host)
        target_root = self._local_sync_root(host_label)
        target_root.mkdir(parents=True, exist_ok=True)
        self.status_label.setText(f"Syncing logs from {remote_dir} …")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            downloaded = self._download_remote_logs(
                client, remote_dir, target_root
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Sync failed",
                f"Unable to sync logs from {remote_dir}: {exc}",
            )
            self.status_label.setText(f"Sync failed: {exc}")
        else:
            if downloaded:
                self.status_label.setText(
                    f"Downloaded {downloaded} file(s) to {target_root}."
                )
            else:
                self.status_label.setText(
                    f"No new files found under {remote_dir}."
                )
            self._populate_files()
        finally:
            QApplication.restoreOverrideCursor()
            try:
                client.close()
            except Exception:
                pass

    def load_file(self, path: Path) -> None:
        if not path.exists():
            self.status_label.setText(f"File does not exist: {path}")
            return

        try:
            fig, _axes, _lines = plotter.build_plot_for_file(path)
        except Exception as exc:
            self.status_label.setText(f"Failed to load {path.name}: {exc}")
            return

        if self._canvas is not None:
            self.layout().removeWidget(self._canvas)
            self._canvas.setParent(None)
            self._canvas.deleteLater()

        self._canvas = FigureCanvasQTAgg(fig)
        self.layout().addWidget(self._canvas)
        fig.canvas.manager.set_window_title(f"SensePi offline — {path.name}")
        self.status_label.setText(f"Loaded {path}")
