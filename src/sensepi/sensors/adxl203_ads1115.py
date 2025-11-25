"""Utilities for interpreting ADXL203/ADS1115 samples.

The logger streams JSON lines with (at least):

  - timestamp_ns : int   monotonic time in nanoseconds
  - x_lp, y_lp   : float low-pass filtered acceleration in m/s² for the X
                   and Y axes respectively.

`parse_line()` consumes those JSON lines and also supports the older
CSV format "timestamp_ns,x,y" for simple replays.
"""

from dataclasses import dataclass
from typing import Sequence
import json


@dataclass
class AdxlSample:
    timestamp_ns: int
    # Low-pass filtered acceleration components in m/s².
    x: float
    y: float


def _parse_json_line(text: str) -> AdxlSample:
    obj = json.loads(text)

    ts_raw = obj.get("timestamp_ns")
    if ts_raw is None:
        raise ValueError("ADXL203 JSON line missing 'timestamp_ns' field")
    timestamp_ns = int(ts_raw)

    # Prefer filtered fields x_lp/y_lp; fall back to x/y if necessary.
    x_val = obj.get("x_lp", obj.get("x"))
    y_val = obj.get("y_lp", obj.get("y"))

    if x_val is None or y_val is None:
        raise ValueError(
            "ADXL203 JSON line missing 'x_lp'/'y_lp' (or 'x'/'y') fields"
        )

    return AdxlSample(timestamp_ns=timestamp_ns, x=float(x_val), y=float(y_val))


def _parse_csv_line(text: str) -> AdxlSample:
    parts: Sequence[str] = text.split(",")
    if len(parts) < 3:
        raise ValueError(
            f"Expected at least 3 comma-separated values for ADXL203 CSV, "
            f"got {len(parts)}: {text!r}"
        )
    ts, x, y = map(float, parts[:3])
    return AdxlSample(int(ts), x, y)


def parse_line(line: str) -> AdxlSample:
    """
    Parse a single text line from the ADXL203 logger into an :class:`AdxlSample`.

    The function understands both the new JSONL streaming format and the
    legacy CSV format.
    """
    text = line.strip()
    if not text:
        raise ValueError("Empty line passed to parse_line()")

    if text[0] == "{":
        return _parse_json_line(text)

    return _parse_csv_line(text)
