from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable


@dataclass
class RateEstimate:
    hz_effective: float
    hz_raw_status: float | None
    hz_ts_window: float | None
    quality: str


class RateController:
    """Estimate streaming rate from sample timestamps."""

    def __init__(self, window_size: int = 100, default_hz: float = 0.0) -> None:
        if window_size <= 1:
            raise ValueError("window_size must be > 1")
        self._times: Deque[float] = deque(maxlen=window_size)
        self.default_hz = float(default_hz)
        self._hz_status: float | None = None

    def add_sample_time(self, t: float) -> None:
        self._times.append(float(t))

    def update_from_status(self, hz: float | None = None) -> RateEstimate:
        if hz is None:
            hz = self.default_hz
        self._hz_status = float(hz)
        return RateEstimate(hz_effective=float(hz), hz_raw_status=float(hz), hz_ts_window=None, quality="status_only")

    @property
    def estimated_hz(self) -> float:
        if len(self._times) < 2:
            return self.default_hz
        t0 = self._times[0]
        t1 = self._times[-1]
        if t1 <= t0:
            return self.default_hz
        span = t1 - t0
        count = len(self._times) - 1
        return count / span if span > 0 else self.default_hz

    def estimate(self) -> RateEstimate:
        hz_ts = self.estimated_hz
        if self._hz_status is not None:
            hz_eff = 0.5 * self._hz_status + 0.5 * hz_ts
            return RateEstimate(hz_effective=hz_eff, hz_raw_status=self._hz_status, hz_ts_window=hz_ts, quality="fused")
        return RateEstimate(hz_effective=hz_ts, hz_raw_status=None, hz_ts_window=hz_ts, quality="ts_only")

    def reset(self) -> None:
        self._times.clear()
        self._hz_status = None

    def feed_times(self, times: Iterable[float]) -> None:
        for t in times:
            self.add_sample_time(t)
