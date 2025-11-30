"""Helpers for configuring the Raspberry Pi logger."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from .sampling import SamplingConfig


@dataclass
class PiLoggerConfig:
    device_rate_hz: float
    record_decimate: int
    stream_decimate: int
    extra: Dict[str, Any] | None = None

    @classmethod
    def from_sampling(cls, sampling: SamplingConfig, **kwargs: Any) -> "PiLoggerConfig":
        decimation = sampling.compute_decimation()
        return cls(
            device_rate_hz=sampling.device_rate_hz,
            record_decimate=decimation["record_decimate"],
            stream_decimate=decimation["stream_decimate"],
            extra=kwargs or None,
        )


def _format_extra_flags(extra: Dict[str, Any] | None) -> List[str]:
    if not extra:
        return []

    flags: List[str] = []
    for key, value in extra.items():
        flag = f"--{str(key).replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                flags.append(flag)
        elif value is not None:
            flags.extend([flag, str(value)])
    return flags


def build_logger_args(pi_cfg: PiLoggerConfig) -> List[str]:
    """Build argument list for ``mpu6050_multi_logger.py`` using ``pi_cfg``."""

    args: List[str] = [
        "--sample-rate-hz",
        f"{pi_cfg.device_rate_hz:.0f}",
        "--stream-every",
        str(pi_cfg.stream_decimate),
    ]

    args.extend(_format_extra_flags(pi_cfg.extra))
    return args


def build_logger_command(pi_cfg: PiLoggerConfig) -> str:
    """
    Build the command line for ``mpu6050_multi_logger.py`` using ``PiLoggerConfig``.

    Do NOT reconstruct sample rate or decimation elsewhere – only use ``pi_cfg``.
    """

    parts: Iterable[str] = ["python -u mpu6050_multi_logger.py", *build_logger_args(pi_cfg)]
    return " ".join(parts)
