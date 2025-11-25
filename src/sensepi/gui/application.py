"""Application bootstrap for the PySide6 GUI."""

import sys
from typing import Tuple

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def create_app(argv: list[str] | None = None) -> Tuple[QApplication, MainWindow]:
    """Create and show the main application window."""
    qt_args = argv if argv is not None else sys.argv
    app = QApplication(qt_args)
    window = MainWindow()
    window.show()
    return app, window


if __name__ == "__main__":
    app, _ = create_app()
    sys.exit(app.exec())
