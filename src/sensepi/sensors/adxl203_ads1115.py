"""Utilities for interpreting ADXL203/ADS1115 samples."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass
class AdxlSample:
    """
    Parsed ADXL203 sample.

    Supports both legacy CSV lines:

        timestamp_ns, x, y

    and the JSON streaming format produced by ``adxl203_ads1115_logger.py``:

        {
          "timestamp_ns": ...,
          "x_lp": ...,
          "y_lp": ...
        }
    """

    timestamp_ns: int
    x: Optional[float] = None
    y: Optional[float] = None


def _parse_json_line(line: str) -> AdxlSample:
    data = json.loads(line)

    ts_raw = data.get("timestamp_ns", 0)
    ts = int(ts_raw)

    def _get_float(name: str) -> Optional[float]:
        v = data.get(name)
        if v is None:
            return None
        return float(v)

    # Map low-pass filtered fields x_lp/y_lp into x/y.
    x_val = _get_float("x_lp")
    if x_val is None:
        x_val = _get_float("x")

    y_val = _get_float("y_lp")
    if y_val is None:
        y_val = _get_float("y")

    return AdxlSample(timestamp_ns=ts, x=x_val, y=y_val)


def parse_line(line: str) -> AdxlSample:
    """
    Parse a single line into :class:`AdxlSample`.

    - If the line looks like JSON (starts with ``'{'``), parse the JSON
      streaming format produced by the Pi logger.
    - Otherwise, assume a simple CSV format::

        timestamp_ns, x, y
    """
    stripped = line.strip()
    if not stripped:
        raise ValueError("Empty ADXL203 line")

    if stripped[0] == "{":
        return _parse_json_line(stripped)

    # CSV fallback
    parts: Sequence[str] = stripped.split(",")
    if len(parts) < 3:
        raise ValueError(
            f"Expected at least 3 CSV columns for ADXL203, got {len(parts)}: {line!r}"
        )

    ts, x, y = map(float, parts[:3])
    return AdxlSample(timestamp_ns=int(ts), x=x, y=y)
