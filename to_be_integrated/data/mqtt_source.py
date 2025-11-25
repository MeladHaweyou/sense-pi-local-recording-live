# data/mqtt_source.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
import time
import numpy as np

from ..core.models import MQTTSettings


class _RateInfo:
    def __init__(self, hz: float) -> None:
        self.hz_effective = float(hz)


@dataclass
class MQTTSource:
    """
    Stub MQTT source used for the Qt shell.

    It does NOT actually connect to a broker; it just synthesizes
    dummy data so that the GUI can run without errors.
    """
    settings: MQTTSettings
    estimated_hz: float = 50.0
    _running: bool = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def switch_frequency(self, hz: int) -> None:
        """Update the estimated sampling frequency (used by UI labels)."""
        self.estimated_hz = float(hz)

    def get_rate(self) -> _RateInfo:
        """Return an object with .hz_effective attribute."""
        return _RateInfo(self.estimated_hz)

    def get_rate_apply_result(self):
        """
        Mimic the real API: return (status, last_requested_hz, timestamp).
        For now, always report 'ok'.
        """
        return ("ok", self.estimated_hz, time.time())

    def read(self, last_seconds: float) -> Dict[str, np.ndarray]:
        """
        Return a dict with slot_0..slot_8 and slot_ts_0..slot_ts_8 arrays.

        Currently returns tiny sine waves (or zeros) so plots have something
        to draw without needing a real broker.
        """
        duration = max(0.1, float(last_seconds))
        n = max(1, int(self.estimated_hz * duration))
        t = np.linspace(0.0, duration, n, endpoint=False, dtype=float)

        out: Dict[str, np.ndarray] = {}
        for i in range(9):
            phase = i * 0.3
            # small sine wave; tweak amplitude later if you like
            y = 0.1 * np.sin(2 * np.pi * 1.0 * t + phase)
            out[f"slot_{i}"] = y
            out[f"slot_ts_{i}"] = t
        return out
