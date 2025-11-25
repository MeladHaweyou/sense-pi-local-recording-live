"""Application bootstrap for the PySide6 GUI."""

from __future__ import annotations

import sys
from typing import Tuple

from PySide6.QtWidgets import QApplication, QMainWindow

from .main_window import MainWindow


def create_app(argv: list[str] | None = None) -> Tuple[QApplication, QMainWindow]:
    """
    Create the QApplication and main SensePi window.

    Parameters
    ----------
    argv:
        Optional argument list to pass to :class:`QApplication`.

    Returns
    -------
    app:
        The QApplication instance (owned by caller).
    window:
        The main window instance with all tabs set up.
    """
    qt_args = argv if argv is not None else sys.argv
    app = QApplication.instance() or QApplication(qt_args)
    window = MainWindow()
    return app, window


def main() -> None:
    app, win = create_app()
    win.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
