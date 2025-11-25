# util/rate_control.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import numpy as np


@dataclass
class RateEstimate:
    hz_effective: float
    hz_raw_status: Optional[float]
    hz_ts_window: Optional[float]
    quality: str


class RateController:
    """Lightweight rate estimator that fuses status-reported Hz and timestamps."""

    def __init__(self, alpha: float = 0.5, default_hz: float = 20.0) -> None:
        self.alpha = float(alpha)
        self.default_hz = float(default_hz)
        self._hz_status: Optional[float] = None

    def update_from_status(self, interval: Optional[float] = None, hz: Optional[float] = None) -> RateEstimate:
        if hz is None and interval and interval > 0:
            hz = 1.0 / float(interval)
        if hz is None:
            hz = self.default_hz
        self._hz_status = float(hz)
        return RateEstimate(hz_effective=float(hz), hz_raw_status=float(hz), hz_ts_window=None, quality="status_only")

    def update_from_timestamps(self, ts: np.ndarray) -> RateEstimate:
        arr = np.asarray(ts, dtype=float).ravel()
        hz_ts = None
        if arr.size >= 2:
            dt = np.diff(arr)
            valid = dt[dt > 0]
            if valid.size:
                hz_ts = 1.0 / float(np.mean(valid))
        if hz_ts is None:
            hz_ts = self.default_hz

        if self._hz_status is not None:
            hz_eff = self.alpha * float(self._hz_status) + (1.0 - self.alpha) * float(hz_ts)
            quality = "fused"
            hz_status = float(self._hz_status)
        else:
            hz_eff = float(hz_ts)
            hz_status = None
            quality = "ts_only"

        return RateEstimate(hz_effective=hz_eff, hz_raw_status=hz_status, hz_ts_window=float(hz_ts), quality=quality)

    def get(self) -> RateEstimate:
        hz = self._hz_status if self._hz_status is not None else self.default_hz
        return RateEstimate(hz_effective=float(hz), hz_raw_status=self._hz_status, hz_ts_window=None, quality="status_only")
