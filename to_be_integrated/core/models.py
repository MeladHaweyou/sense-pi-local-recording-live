# core/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class ChannelCalibration:
    """Per-channel calibration (currently just a scale factor)."""
    scale: float = 1.0


@dataclass
class ChannelConfig:
    """Configuration for one of the 9 slots."""
    name: str
    enabled: bool = True
    cal: ChannelCalibration = field(default_factory=ChannelCalibration)


@dataclass
class MQTTSettings:
    """
    Minimal MQTT-related settings needed by the UI and AppState.
    Extend later when you wire in the real MQTT client.
    """
    host: str = "localhost"
    port: int = 1883
    topic: str = "sensors/raw"
    initial_hz: int = 50        # used by AppState.start_source()
    recorder: str = "mpu6050"   # displayed in SignalsTab


@dataclass
class SSHSettings:
    # Basic connection
    host: str = "192.168.0.6"
    port: int = 22
    username: str = "verwalter"
    password: str = ""
    key_path: str = ""

    # Remote scripts + output
    mpu_script: str = "/home/verwalter/sensor/mpu6050_multi_logger.py"
    adxl_script: str = "/home/verwalter/sensor/adxl203_ads1115_logger.py"
    remote_out_dir: str = "/home/verwalter/sensor/logs"
    local_download_dir: str = str(Path("logs").resolve())

    # Run configuration
    # which sensor logger to run by default: "mpu" or "adxl"
    run_sensor: str = "mpu"

    # recording/streaming mode:
    #   "record"       -> record only (no --stream-stdout)
    #   "record+live"  -> record + stream
    #   "live"         -> stream only (--no-record + --stream-stdout)
    run_mode: str = "record+live"

    # common CLI parameters for both scripts
    rate_hz: float = 100.0
    stream_every: int = 5           # Nth sample to stream over stdout


@dataclass
class GlobalCalibration:
    """Global baseline offsets for 9 slots + enabled flag."""
    enabled: bool = False
    offsets: List[float] = field(default_factory=lambda: [0.0] * 9)
