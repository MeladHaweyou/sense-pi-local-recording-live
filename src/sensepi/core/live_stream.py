"""Helpers for consuming live data from remote loggers."""

from typing import Any, Callable, Iterable

from ..sensors.adxl203_ads1115 import parse_line as parse_adxl
from ..sensors.mpu6050 import parse_line as parse_mpu


def stream_lines(lines: Iterable[str], parser: Callable[[str], Any], callback: Callable[[Any], None]):
    """Parse incoming lines and forward samples to a callback."""
    for line in lines:
        if not line:
            continue
        sample = parser(line)
        callback(sample)


def select_parser(sensor_type: str) -> Callable[[str], Any]:
    if sensor_type == "adxl203_ads1115":
        return parse_adxl
    return parse_mpu
