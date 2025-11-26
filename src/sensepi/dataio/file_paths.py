"""Helpers for constructing standard file paths."""

from datetime import datetime
from pathlib import Path

from ..config.app_config import AppPaths


def session_directory(name: str, base: Path | None = None) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = base or AppPaths().raw_data
    return root / f"{name}_{timestamp}"
