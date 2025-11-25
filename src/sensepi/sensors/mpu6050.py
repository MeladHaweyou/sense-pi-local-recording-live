"""Utilities for interpreting MPU6050 samples."""

from dataclasses import dataclass
from typing import Sequence


@dataclass
class MpuSample:
    timestamp_ns: int
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float


def parse_line(line: str) -> MpuSample:
    """Parse a CSV line emitted by the Pi logger into an :class:`MpuSample`."""
    parts: Sequence[str] = line.strip().split(",")
    ts, ax, ay, az, gx, gy, gz = map(float, parts)
    return MpuSample(int(ts), ax, ay, az, gx, gy, gz)
