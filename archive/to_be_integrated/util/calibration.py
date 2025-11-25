# util/calibration.py
from __future__ import annotations
import numpy as np
from ..core.state import AppState

def apply_global_and_scale(state: AppState, idx: int, y: np.ndarray) -> np.ndarray:
    """
    Uniform calibration used across the app:
      - If global baseline correction is enabled, subtract per-slot offset.
      - Apply per-channel multiplicative scale.
    Returns a 1-D float array (copy-safe for downstream code).
    """
    arr = np.asarray(y, dtype=float).ravel()
    if arr.size == 0:
        return arr
    try:
        if state.global_cal.enabled:
            arr = arr - float(state.global_cal.offsets[idx])
    except Exception:
        # Keep data unmodified on any mishap
        pass
    try:
        arr = float(state.channels[idx].cal.scale) * arr
    except Exception:
        pass
    return arr
