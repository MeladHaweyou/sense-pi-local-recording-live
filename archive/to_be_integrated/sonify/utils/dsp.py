# File: sonify/utils/dsp.py
from __future__ import annotations

import numpy as np

# (…existing imports and code stay…)

def butter_filter(sig: np.ndarray, fs: float, low_hz: float | None = None, high_hz: float | None = None, order: int = 4) -> np.ndarray:
    # (unchanged)
    …

def smooth_moving_average(sig: np.ndarray, fs: float, win_ms: float) -> np.ndarray:
    # (unchanged)
    …


# ----------------------- NEW: level + mapping helpers -----------------------

def abs_area_level(sig: np.ndarray, fs: float) -> float:
    """
    Return mean absolute amplitude of `sig` (proxy for 'absolute sum of areas' per time).
    If you want physical 'area', it’s sum(|x|)*dt; dividing by duration is equivalent
    and is better for normalization. Returns 0..+inf (typically small).
    """
    x = np.asarray(sig, dtype=float).ravel()
    if x.size == 0 or fs <= 0:
        return 0.0
    # mean(|x|) == (sum(|x|)*dt) / (N*dt) -- duration-normalized "area"
    return float(np.mean(np.abs(x)))


def map_level_to_gain(level: float, min_thr: float, max_cap: float) -> float:
    """
    0 when level <= min_thr, 1 when level >= max_cap, linear in between.
    Clamp and handle bad params gracefully.
    """
    lv = float(level)
    lo = float(min_thr)
    hi = float(max_cap)

    if not np.isfinite(lv):
        lv = 0.0
    if not np.isfinite(lo):
        lo = 0.0
    if not np.isfinite(hi):
        hi = lo + 1.0

    if hi <= lo:
        hi = lo + 1e-4  # nudge to avoid zero division

    t = (lv - lo) / (hi - lo)
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return float(t)


def map_level_to_gain_with_floor(level: float, min_thr: float, max_cap: float, floor_pct: float) -> float:
    """
    Like map_level_to_gain but never below `floor_pct` (0..1).
    """
    floor = float(np.clip(floor_pct, 0.0, 1.0))
    g = map_level_to_gain(float(level), float(min_thr), float(max_cap))
    return float(floor + (1.0 - floor) * g)
