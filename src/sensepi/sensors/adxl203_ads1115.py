"""Utilities for interpreting ADXL203/ADS1115 samples."""

from dataclasses import dataclass
from typing import Sequence


@dataclass
class AdxlSample:
    timestamp_ns: int
    x: float
    y: float


def parse_line(line: str) -> AdxlSample:
    """Parse a CSV line emitted by the Pi logger into an :class:`AdxlSample`."""
    parts: Sequence[str] = line.strip().split(",")
    ts, x, y = map(float, parts)
    return AdxlSample(int(ts), x, y)
