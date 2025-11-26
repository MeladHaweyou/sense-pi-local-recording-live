from __future__ import annotations

"""
Legacy shim module.

This file exists for backward compatibility only.
New code should import from :mod:`sensepi.remote` instead::

    from sensepi.remote import PiRecorder
"""

from sensepi.remote import PiRecorder

__all__ = ["PiRecorder"]
