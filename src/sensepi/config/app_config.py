"""Default application paths and configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml


@dataclass
class AppPaths:
    """Commonly used paths for the desktop application."""

    # repo_root points at the project root (one level above src/)
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
class HostConfig:
    """Normalized host configuration derived from ``hosts.yaml`` entries."""

    name: str
    host: str
    user: str
    ssh_key: Optional[str]
    port: int
    base_path: Path
    data_dir: Path
    pi_config_path: Path
    password: Optional[str] = None


@dataclass
class AppConfig:
    """In-memory configuration snapshot used for Pi sync."""

    sensor_defaults: Dict[str, Any]


@dataclass
class SensorDefaults:
    """
    Container for sensor configuration defaults, backed by ``sensors.yaml``.

    Typical structure (may contain extra keys):

    .. code-block:: yaml

        mpu6050:
          sample_rate_hz: 200
          channels: both
          dlpf: 3
          include_temperature: false

        adxl203_ads1115:
          sample_rate_hz: 100
          channels: both
          calibration_samples: 300
    """

    sensors_file: Path = AppPaths().config_dir / "sensors.yaml"

    def load(self) -> Dict[str, Any]:
        """Load and return the full sensors.yaml mapping (or ``{}`` if missing)."""
        if not self.sensors_file.exists():
            return {}
        with self.sensors_file.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def save(self, data: Dict[str, Any]) -> None:
        """
        Write the given mapping back to ``sensors.yaml``.

        Callers are expected to start from :meth:`load` so that unknown keys
        are preserved.
        """
        self.sensors_file.parent.mkdir(parents=True, exist_ok=True)
        with self.sensors_file.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(
                data,
                fh,
                default_flow_style=False,
                sort_keys=False,
            )

    # ------------------------------------------------------------------
    # Convenience helpers for RecorderTab / other callers
    # ------------------------------------------------------------------
    def build_mpu6050_cli_args(
        self,
        overrides: Mapping[str, Any] | None = None,
    ) -> List[str]:
        """
        Build CLI arguments for ``mpu6050_multi_logger.py`` from defaults.

        Parameters
        ----------
        overrides:
            Optional mapping with keys like ``sample_rate_hz``, ``channels``,
            ``dlpf`` or ``include_temperature``.  Any non-``None`` value in
            *overrides* replaces the default read from :mod:`sensors.yaml`.
        """
        config = self.load()
        base = dict(config.get("mpu6050", {}) or {})
        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    base[key] = value
        return build_mpu6050_cli_args(base)

    def build_adxl203_cli_args(
        self,
        overrides: Mapping[str, Any] | None = None,
    ) -> List[str]:
        """
        Build CLI arguments for ``adxl203_ads1115_logger.py`` from defaults.
        """
        config = self.load()
        base = dict(config.get("adxl203_ads1115", {}) or {})
        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    base[key] = value
        return build_adxl203_cli_args(base)


@dataclass
class HostInventory:
    """
    Hosts and SSH defaults for Raspberry Pis, backed by ``hosts.yaml``.

    Expected structure (extra keys are allowed and preserved):

    .. code-block:: yaml

        pis:
          - name: lab-pi
            host: 192.168.0.6
            user: pi
            ssh_key: ~/.ssh/id_rsa  # or password: "hunter2"
            base_path: /home/pi/raspberrypi_scripts
            port: 22
    """

    hosts_file: Path = AppPaths().config_dir / "hosts.yaml"

    def load(self) -> Dict[str, Any]:
        """Load and return the raw mapping from ``hosts.yaml`` (or ``{}``)."""
        if not self.hosts_file.exists():
            return {}
        with self.hosts_file.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def save(self, data: Dict[str, Any]) -> None:
        """Write *data* back to ``hosts.yaml``."""
        self.hosts_file.parent.mkdir(parents=True, exist_ok=True)
        with self.hosts_file.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(
                data,
                fh,
                default_flow_style=False,
                sort_keys=False,
            )

    def list_hosts(self) -> List[Dict[str, Any]]:
        """
        Return a list of host dictionaries from the ``pis`` key.

        Each entry is copied so callers can mutate safely.
        """
        data = self.load()
        pis = data.get("pis") or []
        return [dict(item) for item in pis]

    def save_hosts(self, hosts: Iterable[Mapping[str, Any]]) -> None:
        """
        Replace the ``pis`` list in ``hosts.yaml`` with *hosts*.

        All other top-level keys in the file are preserved.
        """
        existing = self.load()
        existing["pis"] = [dict(h) for h in hosts]
        self.save(existing)

    # ------------------------------------------------------------------
    # Helpers for turning config dicts into runtime objects
    # ------------------------------------------------------------------
    def expand_ssh_key(self, ssh_key: str | None) -> str | None:
        """Expand ``~`` in an SSH key path without modifying the stored YAML."""
        if not ssh_key:
            return None
        return str(Path(ssh_key).expanduser())

    def scripts_dir_for(self, host_cfg: Mapping[str, Any]) -> Path:
        """Return the scripts/base path for a host, with ``~`` expanded."""
        raw = (
            host_cfg.get("base_path")
            or host_cfg.get("scripts_dir")
            or "/home/pi/raspberrypi_scripts"
        )
        return Path(str(raw)).expanduser()

    def to_host_config(self, host_cfg: Mapping[str, Any]) -> HostConfig:
        """Convert a host mapping from YAML into a normalized :class:`HostConfig`."""

        name = str(host_cfg.get("name", host_cfg.get("host", "pi")))
        host = str(host_cfg.get("host", "raspberrypi.local"))
        user = str(host_cfg.get("user", "pi"))
        ssh_key = self.expand_ssh_key(host_cfg.get("ssh_key"))
        port = int(host_cfg.get("port", 22))
        password = host_cfg.get("password")

        base_path = Path(str(host_cfg.get("base_path", "/home/pi/raspberrypi_scripts"))).expanduser()
        data_dir = Path(str(host_cfg.get("data_dir", "/home/pi/logs"))).expanduser()
        pi_cfg = Path(
            str(host_cfg.get("pi_config_path", base_path / "pi_config.yaml"))
        ).expanduser()

        return HostConfig(
            name=name,
            host=host,
            user=user,
            ssh_key=ssh_key,
            port=port,
            base_path=base_path,
            data_dir=data_dir,
            pi_config_path=pi_cfg,
            password=password,
        )

    def to_remote_host(self, host_cfg: Mapping[str, Any]):
        """
        Convert a host dict into :class:`sensepi.remote.ssh_client.Host`.

        This keeps parsing and ``~``-expansion in one place so GUI code
        can construct a ready-to-use SSH host without reimplementing the
        schema.
        """
        from ..remote.ssh_client import Host as RemoteHost

        cfg = self.to_host_config(host_cfg)
        return RemoteHost(
            name=cfg.name,
            host=cfg.host,
            user=cfg.user,
            ssh_key=cfg.ssh_key,
            password=cfg.password,
            port=cfg.port,
        )


# ---------------------------------------------------------------------------
# CLI argument builders for the Pi loggers
# ---------------------------------------------------------------------------

def build_mpu6050_cli_args(config: Mapping[str, Any]) -> List[str]:
    """
    Construct CLI args for ``mpu6050_multi_logger.py`` from a mapping.

    Expected keys in *config* (all optional except ``sample_rate_hz``):

    - ``sample_rate_hz`` (float / int)
    - ``channels`` (``acc``, ``gyro``, ``both``, or ``default``)
    - ``dlpf`` (0..6)
    - ``include_temperature`` (bool)
    """
    args: List[str] = []

    rate = config.get("sample_rate_hz")
    if rate is None:
        raise ValueError("mpu6050 defaults must include 'sample_rate_hz'")
    args.extend(["--rate", str(rate)])

    channels = config.get("channels")
    if channels:
        args.extend(["--channels", str(channels)])

    dlpf = config.get("dlpf")
    if dlpf is not None:
        args.extend(["--dlpf", str(dlpf)])

    if config.get("include_temperature"):
        args.append("--temp")

    return args


def build_adxl203_cli_args(config: Mapping[str, Any]) -> List[str]:
    """
    Construct CLI args for ``adxl203_ads1115_logger.py`` from a mapping.

    Expected keys in *config* (all optional except ``sample_rate_hz``):

    - ``sample_rate_hz`` (float / int)
    - ``channels`` (``x``, ``y``, or ``both``)
    - ``calibration_samples`` (int, mapped to ``--calibrate``)
    """
    args: List[str] = []

    rate = config.get("sample_rate_hz")
    if rate is None:
        raise ValueError("adxl203_ads1115 defaults must include 'sample_rate_hz'")
    args.extend(["--rate", str(rate)])

    channels = config.get("channels")
    if channels:
        args.extend(["--channels", str(channels)])

    cal = config.get("calibration_samples")
    if cal is not None:
        args.extend(["--calibrate", str(cal)])

    return args


def build_pi_config_for_host(host: HostConfig, app_config: AppConfig) -> Dict[str, Any]:
    """
    Build a configuration dictionary for Raspberry Pi loggers based on desktop config.

    The resulting mapping mirrors ``raspberrypi_scripts/pi_config.yaml``.
    """

    sensors_cfg = app_config.sensor_defaults
    mpu_defaults = sensors_cfg.get("mpu6050", {}) or {}
    adxl_defaults = sensors_cfg.get("adxl203_ads1115", {}) or {}

    return {
        "mpu6050": {
            "output_dir": str(host.data_dir / "mpu"),
            "sample_rate_hz": mpu_defaults.get("sample_rate_hz", 200),
            "channels": mpu_defaults.get("channels", "both"),
            "include_temperature": bool(
                mpu_defaults.get("include_temperature", False)
            ),
        },
        "adxl203_ads1115": {
            "output_dir": str(host.data_dir / "adxl"),
            "sample_rate_hz": adxl_defaults.get("sample_rate_hz", 100),
            "channels": adxl_defaults.get("channels", "both"),
            "calibration_samples": adxl_defaults.get("calibration_samples", 0),
        },
    }

