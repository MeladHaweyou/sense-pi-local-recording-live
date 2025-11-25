# util/resample.py
from __future__ import annotations

from typing import Tuple, Optional
import numpy as np


def resample_to_fixed_rate(
    t: np.ndarray,
    y: np.ndarray,
    target_hz: float,
    last_out_t: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, Optional[float]]:
    """
    Simple linear resampler used by the recorder.

    Parameters mirror the original implementation closely enough for the
    existing tests and UI code paths in this shell.
    """
    t = np.asarray(t, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    if t.size == 0 or y.size == 0 or target_hz <= 0:
        return np.array([]), np.array([]), last_out_t

    step = 1.0 / float(target_hz)
    start = float(t[0]) if last_out_t is None else float(last_out_t + step)
    t_end = float(t[-1])
    if start >= t_end:
        return np.array([]), np.array([]), last_out_t

    t_out = np.arange(start, t_end + step / 2.0, step, dtype=float)
    y_out = np.interp(t_out, t, y)
    new_last = float(t_out[-1]) if t_out.size else last_out_t
    return t_out, y_out, new_last
