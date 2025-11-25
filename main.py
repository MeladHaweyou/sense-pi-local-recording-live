from __future__ import annotations

from sensepi.gui.application import create_app


def main() -> None:
    app, win = create_app()
    win.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
