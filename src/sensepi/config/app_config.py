"""Default application paths and configuration helpers."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass
class AppPaths:
    """Commonly used paths for the desktop application."""

    repo_root: Path = Path(__file__).resolve().parents[3]
    data_root: Path = repo_root / "data"
    raw_data: Path = data_root / "raw"
    processed_data: Path = data_root / "processed"
    logs: Path = repo_root / "logs"
    config_dir: Path = repo_root / "src" / "sensepi" / "config"

    def ensure(self) -> None:
        """Create directories if they do not yet exist."""
        for path in (self.data_root, self.raw_data, self.processed_data, self.logs):
            path.mkdir(parents=True, exist_ok=True)


@dataclass
class SensorDefaults:
    """Container for sensor configuration defaults."""

    sensors_file: Path = AppPaths().config_dir / "sensors.yaml"

    def load(self) -> Dict[str, Any]:
        with self.sensors_file.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}


@dataclass
class HostInventory:
    """Hosts and SSH defaults for Raspberry Pis."""

    hosts_file: Path = AppPaths().config_dir / "hosts.yaml"

    def load(self) -> Dict[str, Any]:
        with self.hosts_file.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
