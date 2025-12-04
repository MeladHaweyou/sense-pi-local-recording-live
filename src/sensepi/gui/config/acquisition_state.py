from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Tuple

from sensepi.config.sampling import SamplingConfig

CalibrationKey = Tuple[int, str]  # (sensor_id, channel_name), e.g. (1, "ax")


@dataclass
class CalibrationOffsets:
    """
    Per-sensor, per-channel calibration offsets in physical units.

    Keys are (sensor_id, channel) tuples where channel names match the
    existing MPU6050 fields such as "ax", "ay", "az", "gx", "gy", "gz".
    """

    per_sensor_channel_offset: Dict[CalibrationKey, float] = field(
        default_factory=dict
    )
    description: str | None = None
    timestamp: datetime | None = None

    def offset_for(self, sensor_id: int, channel: str) -> float:
        """Return the stored offset, or 0.0 if none is present."""

        return self.per_sensor_channel_offset.get((int(sensor_id), channel), 0.0)

    def is_empty(self) -> bool:
        return not self.per_sensor_channel_offset


@dataclass
class SensorSelectionConfig:
    """
    GUI-level description of which sensors and channels are active.

    - active_sensors: list of sensor IDs (e.g. [1, 2, 3])
    - active_channels: list of channel names, e.g.:
        ["ax", "ay", "az", "gx", "gy", "gz"]
    """

    active_sensors: List[int] = field(default_factory=list)
    active_channels: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"sensors={self.active_sensors}, "
            f"channels={','.join(self.active_channels) or '(none)'}"
        )


@dataclass
class GuiAcquisitionConfig:
    """
    Full acquisition configuration as seen from the GUI.

    This is what RecorderTab / SignalsTab / FftTab will use to
    configure streaming and recording.
    """

    sampling: SamplingConfig
    stream_rate_hz: float
    record_only: bool = False
    sensor_selection: SensorSelectionConfig = field(
        default_factory=SensorSelectionConfig
    )
    calibration: CalibrationOffsets | None = None

    def summary(self) -> str:
        return (
            f"sampling={self.sampling!r}, "
            f"stream={self.stream_rate_hz:.2f} Hz, "
            f"record_only={self.record_only}, "
            f"{self.sensor_selection.summary()}"
        )
