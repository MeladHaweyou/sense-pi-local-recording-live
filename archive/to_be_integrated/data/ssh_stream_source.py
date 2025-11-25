"""Compatibility shim: re-export the real SSH streaming source."""
from __future__ import annotations

from .ssh_source import SSHSource, SSHStreamSource

__all__ = ["SSHSource", "SSHStreamSource"]
