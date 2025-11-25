from __future__ import annotations

"""
Legacy shim module.

The canonical Pi recorder API now lives in :mod:`sensepi.remote.pi_recorder`.
This module re-exports :class:`PiRecorder` and :class:`RecorderStatus`
so older imports (``from pi_recorder import PiRecorder``) keep working.
"""

from pathlib import Path
import sys

try:
    from sensepi.remote.pi_recorder import PiRecorder, RecorderStatus
except ImportError:  # pragma: no cover - fallback for running from source without installation
    repo_root = Path(__file__).resolve().parent
    src_dir = repo_root / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    from sensepi.remote.pi_recorder import PiRecorder, RecorderStatus  # type: ignore[no-redef]

__all__ = ["PiRecorder", "RecorderStatus"]
