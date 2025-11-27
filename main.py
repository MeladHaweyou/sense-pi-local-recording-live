from __future__ import annotations

import os
import sys
from pathlib import Path

# Make sure the 'src' directory is on sys.path so 'sensepi' can be imported
REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sensepi.gui.application import main as run_gui_main


def main() -> None:
    run_gui_main(sys.argv)


if __name__ == "__main__":
    if os.getenv("SENSEPI_PROFILE", ""):
        import cProfile
        import io
        import pstats

        profiler = cProfile.Profile()
        profiler.enable()
        try:
            main()
        finally:
            profiler.disable()
            buffer = io.StringIO()
            stats = pstats.Stats(profiler, stream=buffer).sort_stats("cumulative")
            stats.print_stats(50)
            print(buffer.getvalue())
    else:
        main()
