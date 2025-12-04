"""Unified sampling configuration and helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class RecordingMode:
    """User-facing presets (labels only; sampling is single-rate)."""

    key: str
    label: str
    target_record_hz: Optional[float]  # kept for backwards compatibility
    target_stream_hz: Optional[float]  # kept for backwards compatibility


RECORDING_MODES: Dict[str, RecordingMode] = {
    "low_fidelity": RecordingMode(
        key="low_fidelity",
        label="Low fidelity (single-rate)",
        target_record_hz=None,
        target_stream_hz=None,
    ),
    "high_fidelity": RecordingMode(
        key="high_fidelity",
        label="High fidelity (single-rate)",
        target_record_hz=None,
        target_stream_hz=None,
    ),
    "raw": RecordingMode(
        key="raw",
        label="Raw (device rate)",
        target_record_hz=None,
        target_stream_hz=None,
    ),
}


@dataclass
class SamplingConfig:
    """
    Single source of truth for sampling.

    device_rate_hz: what the sensor is *actually* sampled at on the Pi.
    mode_key: selects a RecordingMode from RECORDING_MODES.
    """

    device_rate_hz: float
    mode_key: str = "high_fidelity"

    @property
    def mode(self) -> RecordingMode:
        """Return the resolved recording mode (defaults to high_fidelity)."""
        return RECORDING_MODES.get(self.mode_key, RECORDING_MODES["high_fidelity"])

    @property
    def record_decimate(self) -> int:
        """Recording decimation is fixed to 1 (single sampling rate)."""

        return 1

    @property
    def stream_decimate(self) -> int:
        """Streaming decimation is fixed to 1 (single sampling rate)."""

        return 1

    @property
    def record_rate_hz(self) -> float:
        """Alias for the single sampling rate used for recording."""

        return float(self.device_rate_hz)

    @property
    def stream_rate_hz(self) -> float:
        """Alias for the single sampling rate used for streaming."""

        return float(self.device_rate_hz)

    def compute_decimation(self) -> dict:
        """
        Legacy helper returning decimation/rate info.

        All decimations are forced to 1 so recording and streaming use the
        same physical sampling rate as the device.
        """

        return {
            "record_decimate": self.record_decimate,
            "record_rate_hz": self.record_rate_hz,
            "stream_decimate": self.stream_decimate,
            "stream_rate_hz": self.stream_rate_hz,
        }

    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping[str, Any] | None,
        *,
        default_device_rate: float = 200.0,
        default_mode: str = "high_fidelity",
    ) -> "SamplingConfig":
        """
        Construct a SamplingConfig from a mapping such as sensors.yaml.

        Supported shape::

            sampling:
              device_rate_hz: 200
              mode: high_fidelity
        """
        sampling_block = mapping.get("sampling") if isinstance(mapping, Mapping) else None
        device_rate = default_device_rate
        mode_key = default_mode

        if isinstance(sampling_block, Mapping):
            device_rate = sampling_block.get("device_rate_hz", device_rate)  # type: ignore[arg-type]
            mode_key = sampling_block.get("mode", mode_key)  # type: ignore[arg-type]

        # legacy fallback: look for a per-sensor sample rate if the sampling block is
        # missing. This smooths upgrades from the old sensors.yaml structure.
        sensors = mapping.get("sensors") if isinstance(mapping, Mapping) else None
        if isinstance(sensors, Mapping) and not isinstance(sampling_block, Mapping):
            mpu_cfg = sensors.get("mpu6050") if isinstance(sensors.get("mpu6050"), Mapping) else None
            if isinstance(mpu_cfg, Mapping):
                device_rate = mpu_cfg.get("sample_rate_hz", device_rate)  # type: ignore[arg-type]

        try:
            rate = float(device_rate)
        except (TypeError, ValueError):
            rate = float(default_device_rate)

        mode_key_str = str(mode_key or default_mode)
        if mode_key_str not in RECORDING_MODES:
            mode_key_str = default_mode
        return cls(device_rate_hz=rate, mode_key=mode_key_str)

    def to_mapping(self) -> dict:
        """
        Serialize the sampling config back into a mapping suitable for YAML.
        """
        return {
            "sampling": {
                "device_rate_hz": float(self.device_rate_hz),
                "mode": self.mode.key,
            }
        }


@dataclass
class GuiSamplingDisplay:
    device_rate_hz: float
    record_rate_hz: float
    stream_rate_hz: float
    mode_label: str

    @classmethod
    def from_sampling(cls, sampling: SamplingConfig) -> "GuiSamplingDisplay":
        return cls(
            device_rate_hz=sampling.device_rate_hz,
            record_rate_hz=sampling.record_rate_hz,
            stream_rate_hz=sampling.stream_rate_hz,
            mode_label=sampling.mode.label,
        )
