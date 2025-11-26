from __future__ import annotations

import sys
from pathlib import Path

# Make sure the 'src' directory is on sys.path so 'sensepi' can be imported
REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))



from sensepi.gui.application import create_app


def main() -> None:
    app, win = create_app()
    win.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
