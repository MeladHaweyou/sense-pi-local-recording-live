from __future__ import annotations

"""
Legacy shim module.

The canonical SSH client now lives in :mod:`sensepi.remote.ssh_client`.
This module simply re-exports :class:`SSHConfig` and :class:`SSHClient`
so older imports (``from ssh_client import SSHClient``) keep working.
"""

from pathlib import Path
import sys

try:
    from sensepi.remote.ssh_client import SSHClient, SSHConfig
except ImportError:  # pragma: no cover - fallback for running from source without installation
    # Ensure the 'src' directory is on sys.path so ``sensepi`` can be imported.
    repo_root = Path(__file__).resolve().parent
    src_dir = repo_root / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    from sensepi.remote.ssh_client import SSHClient, SSHConfig  # type: ignore[no-redef]

__all__ = ["SSHClient", "SSHConfig"]
