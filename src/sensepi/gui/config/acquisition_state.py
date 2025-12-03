from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ...config.sampling import SamplingConfig


@dataclass
class SensorSelectionConfig:
    """
    GUI-level description of which sensors & channels are active.

    - active_sensors: sensor IDs as integers (e.g. [1, 2, 3])
    - active_channels: logical channel names (e.g. ["ax", "ay", "az", "gx", "gy", "gz"])
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
    GUI-level acquisition config that will later drive the backend.

    - sampling: low-level SamplingConfig (device rate + mode)
    - stream_rate_hz: effective stream rate used for GUI/streaming
    - record_only: if True, we will record but NOT stream to live plots
    - sensor_selection: the SensorSelectionConfig above
    """

    sampling: SamplingConfig
    stream_rate_hz: float
    record_only: bool = False
    sensor_selection: SensorSelectionConfig = field(
        default_factory=SensorSelectionConfig
    )

    def summary(self) -> str:
        return (
            f"sampling={self.sampling!r}, "
            f"stream={self.stream_rate_hz:.2f} Hz, "
            f"record_only={self.record_only}, "
            f"{self.sensor_selection.summary()}"
        )
