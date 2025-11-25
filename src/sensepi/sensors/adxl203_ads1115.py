"""
The ADXL203/ADS1115 logger streams JSON lines with fields such as::

  - timestamp_ns : int   monotonic time in nanoseconds
  - x_lp, y_lp   : float low-pass filtered acceleration components

``parse_line()`` consumes those JSON lines and also supports the older
CSV format "timestamp_ns,x,y" for simple replays.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)


@dataclass
class AdxlSample:
    timestamp_ns: int
    # Low-pass filtered acceleration components in m/s².
    x: float
    y: float


def _parse_json_line(text: str) -> AdxlSample | None:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Bad JSON from sensor stream: %r (%s)", text, exc)
        return None

    ts_raw = obj.get("timestamp_ns")
    if ts_raw is None:
        logger.warning("Missing field %s in sensor line: %r", "timestamp_ns", obj)
        return None
    timestamp_ns = int(ts_raw)

    try:
        x_val = obj.get("x_lp", obj.get("x"))
        y_val = obj.get("y_lp", obj.get("y"))
        if x_val is None or y_val is None:
            raise KeyError("x_lp/y_lp")
        x = float(x_val)
        y = float(y_val)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Bad field value in sensor line %r (%s)", obj, exc)
        return None

    return AdxlSample(timestamp_ns=timestamp_ns, x=x, y=y)


def _parse_csv_line(text: str) -> AdxlSample | None:
    parts: Sequence[str] = text.split(",")
    if len(parts) < 3:
        logger.warning(
            "Expected at least 3 comma-separated values for ADXL203 CSV, got %d: %r",
            len(parts),
            text,
        )
        return None
    try:
        ts, x, y = map(float, parts[:3])
    except ValueError as exc:
        logger.warning("Bad CSV field in sensor line %r (%s)", text, exc)
        return None
    return AdxlSample(int(ts), x, y)


def parse_line(line: str) -> AdxlSample | None:
    """
    Parse a single text line from the ADXL203 logger into an :class:`AdxlSample`.

    The function understands both the new JSONL streaming format and the
    legacy CSV format. Invalid lines return ``None`` so callers can skip them
    without raising exceptions.
    """
    text = line.strip()
    if not text:
        return None

    if text[0] == "{":
        return _parse_json_line(text)

    return _parse_csv_line(text)
