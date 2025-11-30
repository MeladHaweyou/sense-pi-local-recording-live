"""Default application paths and configuration helpers."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

from .pi_logger_config import PiLoggerConfig
from .sampling import SamplingConfig


DEFAULT_BASE_PATH = Path("~/sensor")
DEFAULT_DATA_DIR = Path("~/logs")


@dataclass
class AppPaths:
    """
    Commonly used paths for the desktop application.

    ``SENSEPI_DATA_ROOT`` and ``SENSEPI_LOG_DIR`` override the default
    ``data``/``logs`` folders relative to the repository root so that
    packaged installs and alternate layouts can store files elsewhere.
    """

    # repo_root points at the project root (one level above src/)
    repo_root: Path = Path(__file__).resolve().parents[3]
    data_root: Path = field(init=False)
    raw_data: Path = field(init=False)
    processed_data: Path = field(init=False)
    logs: Path = field(init=False)
    config_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        env_data_root = os.environ.get("SENSEPI_DATA_ROOT")
        if env_data_root:
            self.data_root = Path(env_data_root).expanduser()
        else:
            self.data_root = self.repo_root / "data"

        env_logs_dir = os.environ.get("SENSEPI_LOG_DIR")
        if env_logs_dir:
            self.logs = Path(env_logs_dir).expanduser()
        else:
            self.logs = self.repo_root / "logs"

        self.raw_data = self.data_root / "raw"
        self.processed_data = self.data_root / "processed"
        self.config_dir = self.repo_root / "src" / "sensepi" / "config"

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
    port: int
    base_path: Path
    data_dir: Path
    pi_config_path: Path
    password: Optional[str] = None


def _hz_to_interval_ms(value_hz: float, fallback_ms: int) -> int:
    """Convert a frequency in Hz into a positive integer interval in ms."""
    try:
        hz = float(value_hz)
    except (TypeError, ValueError):
        hz = 0.0
    if hz <= 0.0 or math.isnan(hz) or math.isinf(hz):
        return max(1, int(fallback_ms))
    interval = int(round(1000.0 / hz))
    return max(1, interval)


@dataclass
class PlotPerformanceConfig:
    """
    Tunable limits and refresh rates for the live plot / FFT tabs.

    These parameters cap resource usage so the GUI stays responsive even
    when multiple sensors or view presets are active.
    """

    signal_update_hz: float = 50.0
    time_window_seconds: float = 3.0
    fft_update_hz: float = 10.0
    max_signal_subplots: int = 18
    max_lines_per_subplot: int = 1
    signal_max_points_per_line: int = 2000

    def signal_refresh_interval_ms(self) -> int:
        """Return the timer interval that corresponds to ``signal_update_hz``."""
        return _hz_to_interval_ms(self.signal_update_hz, fallback_ms=50)

    def fft_refresh_interval_ms(self) -> int:
        """Return the timer interval that corresponds to ``fft_update_hz``."""
        return _hz_to_interval_ms(self.fft_update_hz, fallback_ms=500)

    def normalized_time_window_s(self) -> float:
        """Clamp the time-domain window length to a safe, positive range."""
        try:
            window = float(self.time_window_seconds)
        except (TypeError, ValueError):
            window = 3.0
        if not math.isfinite(window) or window <= 0.5:
            return 2.0
        return min(10.0, window)

    def normalized_max_subplots(self) -> int:
        try:
            value = int(self.max_signal_subplots)
        except (TypeError, ValueError):
            value = 18
        return max(1, value)

    def normalized_max_lines(self) -> int:
        try:
            value = int(self.max_lines_per_subplot)
        except (TypeError, ValueError):
            value = 1
        return max(1, value)

    def normalized_max_points(self) -> int:
        try:
            value = int(self.signal_max_points_per_line)
        except (TypeError, ValueError):
            value = 2000
        return max(100, value)


@dataclass
class AppConfig:
    """In-memory configuration snapshot used for Pi sync and GUI runtime."""

    sensor_defaults: Dict[str, Any] = field(default_factory=dict)
    signal_backend: str = "pyqtgraph"
    plot_performance: PlotPerformanceConfig = field(
        default_factory=PlotPerformanceConfig
    )
    sampling_config: SamplingConfig | None = None

    def normalized_signal_backend(self) -> str:
        """Return the canonical backend identifier (``pyqtgraph`` or ``matplotlib``)."""
        backend = str(self.signal_backend or "").strip().lower()
        if backend in {"matplotlib", "mpl"}:
            return "matplotlib"
        if backend in {"pyqtgraph", "pg", "pyqt"}:
            return "pyqtgraph"
        return "pyqtgraph"


@dataclass
class SensorDefaults:
    """
    Helper for loading/saving sensor defaults (sensors.yaml).

    The authoritative sampling configuration is stored under a top-level
    ``sampling`` key and mirrored into per-sensor entries for readability.

    sampling:
      device_rate_hz: 150
      mode: high_fidelity

    sensors:
      mpu6050:
        channels: "default"
        dlpf: 3
        include_temperature: false
        sample_rate_hz: 150  # mirror of sampling.device_rate_hz
    """

    sensors_file: Path = AppPaths().config_dir / "sensors.yaml"

    def _normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(data) if isinstance(data, dict) else {}

        sampling_cfg = SamplingConfig.from_mapping(normalized)
        sampling_block = {
            "device_rate_hz": sampling_cfg.device_rate_hz,
            "mode": sampling_cfg.mode_key,
        }

        sensors_block = normalized.get("sensors")
        if not isinstance(sensors_block, dict):
            sensors_block = {}

        mpu_cfg = dict(sensors_block.get("mpu6050", {}) or {})
        mpu_cfg["sample_rate_hz"] = sampling_cfg.device_rate_hz
        sensors_block["mpu6050"] = mpu_cfg

        normalized["sampling"] = sampling_block
        normalized["sensors"] = sensors_block
        normalized.pop("mpu6050", None)
        return normalized

    def load(self) -> Dict[str, Any]:
        """Load and return the full sensors.yaml mapping (or ``{}`` if missing)."""
        if not self.sensors_file.exists():
            return self._normalize({})
        with self.sensors_file.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        return self._normalize(loaded)

    def load_sampling_config(self, data: Dict[str, Any] | None = None) -> SamplingConfig:
        if data is None:
            data = self.load()
        return SamplingConfig.from_mapping(data)

    def save(self, data: Dict[str, Any]) -> None:
        """
        Write the given mapping back to ``sensors.yaml``.

        Callers are expected to start from :meth:`load` so that unknown keys
        are preserved.
        """
        normalized = self._normalize(data)
        self.sensors_file.parent.mkdir(parents=True, exist_ok=True)
        with self.sensors_file.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(
                normalized,
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
        sampling_cfg = SamplingConfig.from_mapping(config)
        sensors = config.get("sensors") or {}
        base = dict(sensors.get("mpu6050", {}) or {})
        base["sample_rate_hz"] = sampling_cfg.device_rate_hz
        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    base[key] = value
        return build_mpu6050_cli_args(base)


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
            password: "hunter2"
            base_path: ~/sensor
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
    def scripts_dir_for(self, host_cfg: Mapping[str, Any]) -> Path:
        """Return the scripts/base path for a host, with ``~`` expanded."""
        raw = (
            host_cfg.get("base_path")
            or host_cfg.get("scripts_dir")
            or DEFAULT_BASE_PATH
        )
        return Path(str(raw)).expanduser()

    def to_host_config(self, host_cfg: Mapping[str, Any]) -> HostConfig:
        """Convert a host mapping from YAML into a normalized :class:`HostConfig`."""

        name = str(host_cfg.get("name", host_cfg.get("host", "pi")))
        host = str(host_cfg.get("host", "raspberrypi.local"))
        user = str(host_cfg.get("user", "pi"))
        port = int(host_cfg.get("port", 22))
        password = host_cfg.get("password")

        base_path = Path(str(host_cfg.get("base_path", DEFAULT_BASE_PATH))).expanduser()
        data_dir = Path(str(host_cfg.get("data_dir", DEFAULT_DATA_DIR))).expanduser()
        pi_cfg = Path(
            str(host_cfg.get("pi_config_path", base_path / "pi_config.yaml"))
        ).expanduser()

        return HostConfig(
            name=name,
            host=host,
            user=user,
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

def build_pi_config_for_host(host_cfg: HostConfig, app_cfg: AppConfig) -> Dict[str, Any]:
    """
    Build the YAML structure that will be written to pi_config.yaml for a host.

    Currently this mirrors only the MPU6050 logger configuration.
    """
    sensors = app_cfg.sensor_defaults or {}
    sampling_cfg = app_cfg.sampling_config or SamplingConfig.from_mapping(sensors)
    decimation = sampling_cfg.compute_decimation()
    pi_cfg = PiLoggerConfig.from_sampling(sampling_cfg)

    sensor_defaults = sensors.get("sensors") or {}
    mpu_defaults = dict(sensor_defaults.get("mpu6050", {}) or {})
    sensors_list = mpu_defaults.get("sensors", [1, 2, 3])
    if isinstance(sensors_list, str):
        sensors_list = [s.strip() for s in sensors_list.split(",") if s.strip()]

    mpu_cfg = {
        "output_dir": str(host_cfg.data_dir / "mpu"),
        "sample_rate_hz": int(pi_cfg.device_rate_hz),
        "record_decimate": int(pi_cfg.record_decimate),
        "stream_every": int(pi_cfg.stream_decimate),
        "record_rate_hz": float(decimation["record_rate_hz"]),
        "stream_rate_hz": float(decimation["stream_rate_hz"]),
        "channels": str(mpu_defaults.get("channels", "default")),
        "dlpf": int(mpu_defaults.get("dlpf", 3)),
        "include_temperature": bool(mpu_defaults.get("include_temperature", False)),
        "sensors": sensors_list,
    }

    return {
        "generated": "GENERATED FILE - DO NOT EDIT BY HAND",
        "device_rate_hz": float(pi_cfg.device_rate_hz),
        "record_decimate": int(pi_cfg.record_decimate),
        "stream_decimate": int(pi_cfg.stream_decimate),
        "record_rate_hz": float(decimation["record_rate_hz"]),
        "stream_rate_hz": float(decimation["stream_rate_hz"]),
        "mpu6050": mpu_cfg,
    }

