"""Utilities for interpreting MPU6050 samples."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass
class MpuSample:
    """
    Parsed MPU6050 sample.

    Supports both legacy CSV lines (timestamp_ns, ax, ay, az, gx, gy, gz)
    and the JSON streaming format produced by ``mpu6050_multi_logger.py``:

        {
          "timestamp_ns": ...,
          "t_s": ...,
          "sensor_id": ...,
          "ax": ...,
          "ay": ...,
          "gz": ...,
          ...
        }
    """

    timestamp_ns: int
    ax: Optional[float] = None
    ay: Optional[float] = None
    az: Optional[float] = None
    gx: Optional[float] = None
    gy: Optional[float] = None
    gz: Optional[float] = None
    sensor_id: Optional[int] = None
    t_s: Optional[float] = None
    temp_c: Optional[float] = None


def _parse_json_line(line: str) -> MpuSample:
    data = json.loads(line)

    ts_raw = data.get("timestamp_ns", 0)
    ts = int(ts_raw)

    t_s_raw = data.get("t_s")
    t_s = float(t_s_raw) if t_s_raw is not None else None

    sid_raw = data.get("sensor_id")
    sensor_id = int(sid_raw) if sid_raw is not None else None

    def _get_float(name: str) -> Optional[float]:
        v = data.get(name)
        if v is None:
            return None
        return float(v)

    return MpuSample(
        timestamp_ns=ts,
        ax=_get_float("ax"),
        ay=_get_float("ay"),
        az=_get_float("az"),
        gx=_get_float("gx"),
        gy=_get_float("gy"),
        gz=_get_float("gz"),
        sensor_id=sensor_id,
        t_s=t_s,
        temp_c=_get_float("temp_c"),
    )


def parse_line(line: str) -> MpuSample:
    """
    Parse a single line into :class:`MpuSample`.

    - If the line looks like JSON (starts with ``'{'``), parse the JSON
      streaming format produced by the Pi logger.
    - Otherwise, fall back to the legacy CSV format:

        timestamp_ns, ax, ay, az, gx, gy, gz
    """
    stripped = line.strip()
    if not stripped:
        raise ValueError("Empty MPU6050 line")

    if stripped[0] == "{":
        return _parse_json_line(stripped)

    # CSV fallback
    parts: Sequence[str] = stripped.split(",")
    if len(parts) < 7:
        raise ValueError(
            f"Expected at least 7 CSV columns for MPU6050, got {len(parts)}: {line!r}"
        )

    ts, ax, ay, az, gx, gy, gz = map(float, parts[:7])
    return MpuSample(
        timestamp_ns=int(ts),
        ax=ax,
        ay=ay,
        az=az,
        gx=gx,
        gy=gy,
        gz=gz,
    )
