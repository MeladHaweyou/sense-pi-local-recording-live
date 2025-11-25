"""Helpers for consuming live data from remote loggers."""

from typing import Any, Callable, Iterable

from ..sensors.adxl203_ads1115 import parse_line as parse_adxl
from ..sensors.mpu6050 import parse_line as parse_mpu


def stream_lines(
    lines: Iterable[str],
    parser: Callable[[str], Any],
    callback: Callable[[Any], None],
) -> None:
    """Parse incoming lines and forward decoded samples to a callback."""
    for line in lines:
        if not line:
            continue
        sample = parser(line)
        if sample is None:
            continue
        callback(sample)


def select_parser(sensor_type: str) -> Callable[[str], Any]:
    """
    Select the appropriate line parser for a given sensor type name.

    The ``sensor_type`` should match the identifiers used elsewhere in the
    app (e.g. in ``sensors.yaml``).
    """
    st = sensor_type.strip().lower()
    if st in {"adxl203_ads1115", "adxl203", "adxl203-ads1115"}:
        return parse_adxl
    if st in {"mpu6050", "mpu-6050"}:
        return parse_mpu
    raise ValueError(f"Unknown sensor_type {sensor_type!r}")
