"""Entry point for the SensePi PySide6 desktop application."""

from sensepi.gui.application import create_app


def main() -> int:
    """Launch the GUI application."""
    app, _ = create_app()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
