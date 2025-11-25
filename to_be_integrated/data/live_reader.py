# data/live_reader.py
from __future__ import annotations

import numpy as np
from .mqtt_source import MQTTSource

def get_slot_data(source: MQTTSource, seconds: float, slot_index: int) -> np.ndarray:
    """
    Read last `seconds` from the shared source, return 1-D numpy array
    for the requested slot. Never raises; returns empty array on any issue.
    """
    try:
        i = int(slot_index)
        d = source.read(float(seconds))
        y = d.get(f"slot_{i}", None)
        if y is None:
            return np.array([], dtype=float)
        return np.asarray(y, dtype=float).ravel()
    except Exception:
        return np.array([], dtype=float)
