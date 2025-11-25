from __future__ import annotations
import os, sys, atexit

# Keep these if you like, they don't hurt:
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

try:
    import sdl3
    sdl3.SDL_Init(sdl3.SDL_INIT_AUDIO)
    def _quit_sdl():
        try:
            sdl3.SDL_Quit()
        except Exception:
            pass
    atexit.register(_quit_sdl)
except Exception:
    pass

from PySide6.QtWidgets import QApplication
from .ui.main_window import MainWindow   # <-- RELATIVE import

def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
