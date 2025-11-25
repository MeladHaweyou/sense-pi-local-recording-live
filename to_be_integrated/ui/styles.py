"""Global styles for the application.

This module defines a function to apply a simple Qt stylesheet to the
application.  You can modify the CSS here to adjust font sizes, colours
and spacing throughout the GUI.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


def apply_styles(widget: QWidget) -> None:
    """Apply a minimal stylesheet to the given widget and its children."""
    widget.setStyleSheet(
        """
        QWidget {
            font-size: 12pt;
        }
        QPushButton {
            padding: 4px 6px;
        }
        QDoubleSpinBox, QSpinBox {
            min-width: 60px;
        }
        QComboBox {
            min-width: 80px;
        }
        QLabel {
            color: #222222;
        }
        """
    )
