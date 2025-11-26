from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLayout, QSizePolicy, QToolButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    """
    Simple collapsible section: a header with an arrow and a content area.
    Use setContentLayout() to put your real widgets inside.
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._toggle = QToolButton(text=title, checkable=True, checked=True)
        self._toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(Qt.DownArrow)
        self._toggle.toggled.connect(self._on_toggled)

        self._content = QWidget()
        self._content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._content.setVisible(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._toggle)
        layout.addWidget(self._content)

    def setContentLayout(self, layout: QLayout) -> None:
        """Put a layout with your controls inside the collapsible content area."""
        self._content.setLayout(layout)

    def setCollapsed(self, collapsed: bool) -> None:
        """Programmatic collapse/expand (e.g. when Start is pressed)."""
        self._toggle.setChecked(not collapsed)

    def _on_toggled(self, checked: bool) -> None:
        self._content.setVisible(checked)
        self._toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
