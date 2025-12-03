"""Recordings tab wrapper for the existing offline browser."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from .tab_offline import OfflineTab


class RecordingsTab(QWidget):
    """Wrapper around the existing OfflineTab.

    Phase 2: UI only, behavior unchanged.
    """

    def __init__(self, app_paths, recorder_tab, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.offline_tab = OfflineTab(app_paths, recorder_tab)
        layout.addWidget(self.offline_tab)
