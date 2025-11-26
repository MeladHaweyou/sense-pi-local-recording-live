from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from ...config.app_config import AppPaths
from ...tools import plotter


class OfflineTab(QWidget):
    """Offline log viewer built on the shared plotter helpers."""

    def __init__(self, app_paths: AppPaths, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._paths = app_paths
        self._paths.ensure()

        self._canvas: FigureCanvasQTAgg | None = None

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Recent logs:"))
        self.btn_refresh = QPushButton("Refresh")
        self.btn_browse = QPushButton("Browse…")
        top_row.addWidget(self.btn_refresh)
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
        self.file_list.itemDoubleClicked.connect(self._on_open_selected)

        self._populate_files()

    def _populate_files(self) -> None:
        self.file_list.clear()
        for path in self._candidate_logs():
            self.file_list.addItem(str(path))

    def _candidate_logs(self) -> Iterable[Path]:
        roots = [
            self._paths.raw_data,
            self._paths.processed_data,
            self._paths.logs,
        ]
        seen = set()
        for root in roots:
            if not root.exists():
                continue
            for pattern in ("*.csv", "*.jsonl"):
                for path in sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True):
                    if path in seen:
                        continue
                    seen.add(path)
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
