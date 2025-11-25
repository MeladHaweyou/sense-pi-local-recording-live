"""Helpers for consuming live data from remote loggers."""

from __future__ import annotations

from typing import Any, Callable, Iterable

from ..sensors.adxl203_ads1115 import parse_line as parse_adxl
from ..sensors.mpu6050 import parse_line as parse_mpu


def stream_lines(
    lines: Iterable[str],
    parser: Callable[[str], Any],
    callback: Callable[[Any], None],
) -> None:
    """
    Parse incoming lines and forward samples to a callback.

    The iterable is closed at the end if it exposes a ``close()`` method
    (for example, the generator returned by ``SSHClient.exec_stream``).
    """
    close = getattr(lines, "close", None)

    try:
        for raw in lines:
            if not raw:
                continue
            line = raw.strip()
            if not line:
                continue

            sample = parser(line)
            if sample is None:
                continue

            callback(sample)
    finally:
        if callable(close):
            try:
                close()
            except Exception:
                # Best-effort cleanup; ignore channel-close errors.
                pass


def select_parser(sensor_type: str) -> Callable[[str], Any]:
    """
    Return a parsing function for a given sensor type string.

    The parser must accept JSON streaming lines from the Pi loggers.
    """
    st = (sensor_type or "").lower()
    if "adxl" in st:
        return parse_adxl
    if "mpu" in st or "6050" in st:
        return parse_mpu
    # Default to MPU6050 if unknown
    return parse_mpu
