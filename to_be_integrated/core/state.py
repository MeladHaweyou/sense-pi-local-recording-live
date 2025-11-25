# core/state.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

from .models import ChannelConfig, MQTTSettings, SSHSettings, GlobalCalibration
from ..data.base import DataSource
from ..data.mqtt_source import MQTTSource
from ..data.ssh_source import SSHSource

_DEFAULT_SLOT_NAMES = [
    "S0 ax (m/s²)", "S0 ay (m/s²)", "S0 gz (deg/s)",
    "S1 ax (m/s²)", "S1 ay (m/s²)", "S1 gz (deg/s)",
    "S2 ax (m/s²)", "S2 ay (m/s²)", "S2 gz (deg/s)",
]

@dataclass
class AppState:
    channels: List[ChannelConfig] = field(
        default_factory=lambda: [ChannelConfig(name=_DEFAULT_SLOT_NAMES[i], enabled=True) for i in range(9)]
    )

    # Which backend to use for live data: "mqtt" or "ssh" (user-switchable)
    data_source: str = "mqtt"

    mqtt: MQTTSettings = field(default_factory=MQTTSettings)
    ssh: SSHSettings = field(default_factory=SSHSettings)
    global_cal: GlobalCalibration = field(default_factory=GlobalCalibration)

    # Shared live source instance (MQTTSource or SSHStreamSource)
    source: DataSource | None = None

    def ensure_source(self) -> DataSource:
        """Return the shared live source instance, constructing it on first use."""
        if self.source is not None:
            return self.source

        if self.data_source == "ssh":
            self.source = SSHSource(self.ssh)
        else:
            # Default / fallback: MQTT
            self.source = MQTTSource(self.mqtt)
        return self.source

    def start_source(self) -> None:
        """Ensure the current source exists and is started."""
        src = self.ensure_source()
        src.start()  # idempotent for both MQTT and SSH

        # Preserve existing MQTT frequency behaviour
        if isinstance(src, MQTTSource):
            try:
                if getattr(self.mqtt, "initial_hz", 0):
                    src.switch_frequency(int(self.mqtt.initial_hz))
            except Exception:
                # non-fatal if broker/device is offline
                pass

    def stop_source(self) -> None:
        """Stop the current source (MQTT or SSH) if present."""
        if self.source is not None:
            try:
                self.source.stop()
            except Exception:
                pass
