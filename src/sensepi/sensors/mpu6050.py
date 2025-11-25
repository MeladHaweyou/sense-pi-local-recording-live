"""
The Raspberry Pi logger streams JSON lines with (at least):

  - timestamp_ns : int   monotonic time in nanoseconds
  - t_s          : float seconds since the run started
  - sensor_id    : int   logical sensor index (1, 2, or 3)
  - ax, ay, az   : float linear acceleration in m/s²
  - gx, gy, gz   : float angular rate in deg/s

``parse_line()`` accepts those JSON lines and also supports the legacy
comma-separated format "timestamp_ns,ax,ay,az,gx,gy,gz" for older logs.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass
class MpuSample:
    timestamp_ns: int
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    sensor_id: Optional[int] = None
    t_s: Optional[float] = None


def _parse_json_line(text: str) -> MpuSample | None:
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

    sensor_id = obj.get("sensor_id")
    if sensor_id is not None:
        sensor_id = int(sensor_id)

    t_s = obj.get("t_s")
    if t_s is not None:
        t_s = float(t_s)

    def _get_axis(name: str) -> float:
        val = obj.get(name)
        if val is None:
            # Use NaN to indicate "not present" while keeping a float type.
            return math.nan
        return float(val)

    try:
        ax = _get_axis("ax")
        ay = _get_axis("ay")
        az = _get_axis("az")
        gx = float(obj.get("gx", 0.0))
        gy = float(obj.get("gy", 0.0))
        gz = float(obj.get("gz", 0.0))
    except (TypeError, ValueError) as exc:
        logger.warning("Bad field value in sensor line %r (%s)", obj, exc)
        return None

    return MpuSample(
        timestamp_ns=timestamp_ns,
        ax=ax,
        ay=ay,
        az=az,
        gx=gx,
        gy=gy,
        gz=gz,
        sensor_id=sensor_id,
        t_s=t_s,
    )


def _parse_csv_line(text: str) -> MpuSample | None:
    parts: Sequence[str] = text.split(",")
    if len(parts) < 7:
        logger.warning(
            "Expected at least 7 comma-separated values for MPU6050 CSV, got %d: %r",
            len(parts),
            text,
        )
        return None
    try:
        ts, ax, ay, az, gx, gy, gz = map(float, parts[:7])
    except ValueError as exc:
        logger.warning("Bad CSV field in sensor line %r (%s)", text, exc)
        return None
    return MpuSample(
        timestamp_ns=int(ts),
        ax=ax,
        ay=ay,
        az=az,
        gx=gx,
        gy=gy,
        gz=gz,
    )


def parse_line(line: str) -> MpuSample | None:
    """
    Parse a single text line from the MPU6050 logger into an :class:`MpuSample`.

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
