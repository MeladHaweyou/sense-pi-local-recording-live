from __future__ import annotations

from collections import Counter
from datetime import datetime
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from ...config.app_config import AppPaths
from ...config.log_paths import LOG_SUBDIR_MPU, build_pc_session_root
from ...remote.ssh_client import SSHClient
# Decimation helper used to downsample long recordings for plotting
from ...tools.plotter import Plotter

if TYPE_CHECKING:
    from .tab_recorder import RecorderTab


class OfflineTab(QWidget):
    """
    Recordings browser for reviewing synchronized logs outside live sessions.

    Responsibilities:
    - Sync completed runs from the Raspberry Pi via :class:`RecorderTab` host
      configuration, list available log files, and open them locally.
    - Use the shared plotter utilities to render historical runs without
      affecting live streaming buffers.
    - Serves offline analysis; live monitoring stays within ``Signals`` and
      ``Spectrum`` tabs.
    """

    recordingsImported = Signal(list)

    def __init__(
        self,
        app_paths: AppPaths,
        recorder_tab: "RecorderTab | None" = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._app_paths: AppPaths = app_paths
        self._app_paths.ensure()
        self._recorder_tab = recorder_tab
        self._plotter = Plotter()

        # Holds metadata per recording row
        self._recordings: list[dict] = []

        self._canvas: FigureCanvasQTAgg | None = None

        layout = QVBoxLayout(self)

        # Button row
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Offline log files:"))
        self.refresh_button = QPushButton("Refresh list")
        self.import_button = QPushButton("Import recording…")
        self.btn_sync = QPushButton("Sync logs from Pi")
        self.btn_sync_open = QPushButton("Sync && open latest")
        self.btn_browse = QPushButton("Browse…")
        top_row.addWidget(self.refresh_button)
        top_row.addWidget(self.import_button)
        top_row.addWidget(self.btn_sync)
        top_row.addWidget(self.btn_sync_open)
        top_row.addWidget(self.btn_browse)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.help_label = QLabel(
            "Offline workflow:\n"
            "1. Record data on the Pi via the Device tab.\n"
            "2. Click 'Sync logs from Pi' to download new log files.\n"
            "3. Select a log file below and double-click it to open.",
            self,
        )
        self.help_label.setWordWrap(True)
        layout.addWidget(self.help_label)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Timestamp", "Duration", "Path"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        self.preview_label = QLabel("Select a recording to see details.")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        self.status_label = QLabel(
            "No logs synced yet. Sync from the Pi to download runs, then "
            "select a file to open it.",
            self,
        )
        layout.addWidget(self.status_label)

        self.setLayout(layout)

        self.refresh_button.clicked.connect(self.refresh_recordings_list)
        self.import_button.clicked.connect(self.import_recordings)
        self.btn_browse.clicked.connect(self._on_browse)
        self.btn_sync.clicked.connect(self._on_sync_from_pi_clicked)
        self.btn_sync_open.clicked.connect(self._on_sync_and_open_latest_clicked)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_open_selected)

        self.refresh_recordings_list()

    def _recordings_dir(self) -> Path:
        """
        Return the canonical directory where raw recordings live.
        """

        return Path(self._app_paths.raw_data).expanduser().resolve()

    def refresh_recordings_list(self) -> None:
        """
        Scan the recordings directory and populate the table.
        """

        root = self._recordings_dir()
        root.mkdir(parents=True, exist_ok=True)

        self._recordings.clear()
        self.table.setRowCount(0)

        paths_with_mtime: list[tuple[float, Path]] = []
        for path in root.glob("*.csv"):
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                continue
            paths_with_mtime.append((mtime, path))

        for _, path in sorted(paths_with_mtime, key=lambda pair: pair[0], reverse=True):
            meta = self._build_metadata_for_file(path)
            self._recordings.append(meta)

        self.table.setRowCount(len(self._recordings))
        for row, meta in enumerate(self._recordings):
            self.table.setItem(row, 0, QTableWidgetItem(meta["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(meta["timestamp_str"]))
            self.table.setItem(row, 2, QTableWidgetItem(meta.get("duration_str", "")))
            self.table.setItem(row, 3, QTableWidgetItem(str(meta["path"])))

        self.table.resizeColumnsToContents()

        if self._recordings:
            self.status_label.setText(
                f"Found {len(self._recordings)} recording(s). Select one to preview."
            )
        else:
            self.status_label.setText(
                "No local recordings found. Import files or sync from the Pi."
            )
            self.preview_label.setText("Select a recording to see details.")

    def _build_metadata_for_file(self, path: Path) -> dict:
        """
        Build a metadata dict for a recording file.
        """

        stat_result = path.stat()
        timestamp = stat_result.st_mtime
        ts_dt = datetime.fromtimestamp(timestamp)
        meta = {
            "path": path,
            "name": path.name,
            "timestamp": ts_dt,
            "timestamp_str": ts_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_str": "",
        }

        return meta

    def import_recordings(self) -> None:
        """
        Import external recording files into the project recordings directory.
        """

        paths_str, _ = QFileDialog.getOpenFileNames(
            self,
            "Import recordings",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not paths_str:
            return

        dest_dir = self._recordings_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)

        imported_paths: list[Path] = []

        for p_str in paths_str:
            src = Path(p_str)
            if not src.is_file():
                continue
            dest = dest_dir / src.name
            if dest.exists():
                reply = QMessageBox.question(
                    self,
                    "Overwrite file?",
                    f"{dest.name} already exists. Overwrite?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    continue
            shutil.copy2(src, dest)
            imported_paths.append(dest)

        if imported_paths:
            self.refresh_recordings_list()
            self.recordingsImported.emit(imported_paths)

    def _on_table_selection_changed(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.preview_label.setText("Select a recording to see details.")
            return

        row = selected_rows[0].row()
        if row >= len(self._recordings):
            self.preview_label.setText("Select a recording to see details.")
            return

        meta = self._recordings[row]
        text = (
            f"<b>{meta['name']}</b><br>"
            f"Time: {meta['timestamp_str']}<br>"
            f"Path: {meta['path']}<br>"
        )
        if meta.get("duration_str"):
            text += f"Duration: {meta['duration_str']}<br>"

        self.preview_label.setText(text)

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
        host_label = cfg.name or host.name or host.host
        return host, remote_dir, host_label

    def _download_remote_logs(
        self,
        client: SSHClient,
        remote_root: str,
        host_label: str,
    ) -> tuple[int, Counter[str | None], list[Path]]:
        remote_root = remote_root.rstrip("/") or "/"
        allowed_ext = {".csv", ".jsonl", ".json"}
        sensor_prefix = LOG_SUBDIR_MPU
        downloaded = 0
        per_session: Counter[str | None] = Counter()
        new_files: list[Path] = []
        slug_source = host_label or getattr(client.host, "name", "") or client.host.host

        with client.sftp() as sftp:
            try:
                sftp.listdir(remote_root)
            except IOError as exc:
                raise RuntimeError(
                    f"Remote directory {remote_root} not found"
                ) from exc

            sensor_root = PurePosixPath(remote_root)
            if sensor_root.name != sensor_prefix:
                candidate = sensor_root / sensor_prefix
                try:
                    sftp.listdir(candidate.as_posix())
                except IOError:
                    pass
                else:
                    sensor_root = candidate

            stack: list[tuple[PurePosixPath, PurePosixPath]] = [
                (sensor_root, PurePosixPath())
            ]
            treats_first_part_as_session = sensor_root.name == sensor_prefix

            while stack:
                remote_dir, rel_dir = stack.pop()
                remote_dir_str = remote_dir.as_posix()
                try:
                    entries = sftp.listdir_attr(remote_dir_str)
                except IOError:
                    continue
                for entry in entries:
                    remote_path = remote_dir / entry.filename
                    rel_path = rel_dir / entry.filename
                    mode = entry.st_mode
                    if stat.S_ISDIR(mode):
                        stack.append((remote_path, rel_path))
                        continue
                    if not stat.S_ISREG(mode):
                        continue
                    if Path(entry.filename).suffix.lower() not in allowed_ext:
                        continue

                    rel_parts = rel_path.parts
                    if not rel_parts:
                        continue
                    session_name: str | None = None
                    rel_after_session = rel_parts
                    if treats_first_part_as_session and len(rel_parts) >= 2:
                        session_name = rel_parts[0]
                        rel_after_session = rel_parts[1:]
                    if not rel_after_session:
                        continue

                    local_rel = Path(*rel_after_session)
                    target_root = build_pc_session_root(
                        raw_root=self._app_paths.raw_data,
                        host_slug=slug_source,
                        session_name=session_name,
                        sensor_prefix=sensor_prefix,
                    )
                    local_path = target_root / local_rel
                    local_path.parent.mkdir(parents=True, exist_ok=True)

                    should_skip = False
                    if local_path.exists():
                        try:
                            should_skip = local_path.stat().st_size == entry.st_size
                        except FileNotFoundError:
                            should_skip = False
                    if should_skip:
                        continue

                    sftp.get(remote_path.as_posix(), str(local_path))
                    downloaded += 1
                    per_session[session_name] += 1
                    new_files.append(local_path)

        return downloaded, per_session, new_files

    def _format_sync_message(
        self,
        total: int,
        per_session: Counter[str | None],
        host_label: str,
    ) -> str:
        session_names = sorted(name for name in per_session if name)
        unnamed_count = per_session.get(None, 0)
        host_display = host_label or "host"

        if session_names and not unnamed_count:
            if len(session_names) == 1:
                return f"Synced {total} log file(s) for session '{session_names[0]}'."
            listed = ", ".join(session_names[:3])
            if len(session_names) > 3:
                listed += f", +{len(session_names) - 3} more"
            return (
                f"Synced {total} log file(s) across {len(session_names)} sessions: "
                f"{listed}."
            )

        if unnamed_count and not session_names:
            return f"Synced {total} log file(s) from host '{host_display}'."

        if session_names:
            return (
                f"Synced {total} log file(s) from host '{host_display}' "
                f"(sessions: {', '.join(session_names)})."
            )

        return f"Synced {total} log file(s)."

    @Slot()
    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select log file",
            str(self._app_paths.raw_data),
            "Logs (*.csv *.jsonl)",
        )
        if path:
            self.load_file(Path(path))

    @Slot()
    def _on_open_selected(self, *_args) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if row >= len(self._recordings):
            return
        meta = self._recordings[row]
        self.load_file(meta["path"])

    @Slot()
    def _on_sync_from_pi_clicked(self) -> None:
        """Download new log files from the Pi (offline workflow step 2).

        Workflow reminder:
        1. Record data on the Pi from the Device tab.
        2. Sync logs from the Pi to the laptop (this method).
        3. Open downloaded logs for offline plotting.
        """
        context = self._resolve_remote_context()
        if context is None:
            QMessageBox.information(
                self,
                "Sync logs",
                "Select a Raspberry Pi host in the Device tab first.",
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
        host_display = host_label or host.name or host.host
        self.status_label.setText(f"Syncing logs from {remote_dir} …")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            downloaded, per_session, new_files = self._download_remote_logs(
                client, remote_dir, host_display
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Sync failed",
                f"Unable to sync logs from {remote_dir}: {exc}",
            )
            self.status_label.setText(f"Sync failed: {exc}")
        else:
            self.refresh_recordings_list()
            self._highlight_new_files(new_files)
            if downloaded:
                message = self._format_sync_message(
                    downloaded, per_session, host_display
                )
            else:
                message = "No new log files to sync."
            self.status_label.setText(message)
        finally:
            QApplication.restoreOverrideCursor()
            try:
                client.close()
            except Exception:
                pass

    def _highlight_new_files(self, new_files: Iterable[Path]) -> None:
        """Select the first newly downloaded log to draw attention to it."""
        targets = {str(path) for path in new_files}
        if not targets:
            return
        for row, meta in enumerate(self._recordings):
            if str(meta.get("path")) in targets:
                self.table.selectRow(row)
                break

    @Slot()
    def _on_sync_and_open_latest_clicked(self) -> None:
        """Sync logs and immediately open the newest entry."""
        self._on_sync_from_pi_clicked()

        if not self._recordings:
            return

        newest_meta = self._recordings[0]
        self.table.selectRow(0)
        self._on_open_selected()
        self.status_label.setText(
            f"Synced and opened latest log: {newest_meta['name']}"
        )

    def load_file(self, path: Path) -> None:
        if not path.exists():
            self.status_label.setText(f"File does not exist: {path}")
            return

        try:
            fig, _axes, _lines = self._plotter.build_figure(path)
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
