#!/usr/bin/env python
"""
sampling_rate_debugging.py

Unified sampling / streaming / recording debugger.

Answers, in one short run:

    - What sampling rate do we *expect* (from sensors.yaml)?
    - What sampling rate does the Pi *report* via its stream meta header?
    - What sampling rate does the PC *see* over the SSH stream?
    - What sampling rate do the Pi log files *actually* contain?

It works by:

  1. Loading SamplingConfig from sensors.yaml on the PC.
  2. Connecting to the Pi described in hosts.yaml.
  3. Starting mpu6050_multi_logger.py over SSH via PiRecorder for a fixed duration,
     with both recording and streaming enabled.
  4. Reading the JSON meta header printed by the logger to get
     pi_device_sample_rate_hz and pi_stream_rate_hz.
  5. Counting streamed samples per sensor and estimating the effective PC stream rate.
  6. Running raspberrypi_scripts/debug_log_sample_rate.py on the Pi output directory
     for this session and parsing its summary.

Usage (from project root):

    python "debuging codes/sampling_rate_debugging.py" --host-name Pi06 --seconds 10 --session-name TestRate

Notes
-----
- This script assumes:
    * src/ is one level below the project root and contains the sensepi package.
    * hosts.yaml and sensors.yaml live under src/sensepi/config/.
    * raspberrypi_scripts/ (with mpu6050_multi_logger.py and debug_log_sample_rate.py)
      is present on the Pi at the host's base_path from hosts.yaml.
- It intentionally does not touch the GUI or Qt ingest pipeline; for ingest debugging
  continue to use debug_pc_ingest_worker.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, Mapping, Optional, Tuple

# --------------------------------------------------------------------------- #
# Repo root / sys.path setup
# --------------------------------------------------------------------------- #


def _find_repo_root() -> Path:
    """
    Best-effort guess of the project root by walking up until we see src/sensepi.

    This mirrors the logic used elsewhere (AppPaths._default_repo_root), but keeps
    the script self-contained.
    """
    here = Path(__file__).resolve()
    for candidate in [here] + list(here.parents):
        if (candidate / "src" / "sensepi").is_dir():
            return candidate
    # Fallback: assume we're inside the repo and src is a sibling of this file.
    return here.parent


REPO_ROOT = _find_repo_root()
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# --------------------------------------------------------------------------- #
# Imports from sensepi
# --------------------------------------------------------------------------- #

from sensepi.config.sampling import (  # type: ignore[import]
    GuiSamplingDisplay,
    SamplingConfig,
)
from sensepi.config.app_config import (  # type: ignore[import]
    AppConfig,
    HostConfig,
    HostInventory,
    SensorDefaults,
    normalize_remote_path,
)
from sensepi.config.pi_logger_config import PiLoggerConfig  # type: ignore[import]
from sensepi.config.log_paths import LOG_SUBDIR_MPU  # type: ignore[import]
from sensepi.remote.pi_recorder import PiRecorder  # type: ignore[import]
from sensepi.sensors.mpu6050 import (  # type: ignore[import]
    MpuSample,
    parse_line as parse_mpu_line,
)

# --------------------------------------------------------------------------- #
# Data classes for summaries
# --------------------------------------------------------------------------- #


@dataclass
class ExpectedRates:
    """Expected sampling/record/stream rates from PC config."""

    device_rate_hz: float
    record_rate_hz: float
    stream_rate_hz: float
    mode_label: str


@dataclass
class PiStreamMeta:
    """Meta header emitted by mpu6050_multi_logger on the Pi."""

    sensor_ids: list[int] = field(default_factory=list)
    pi_device_sample_rate_hz: Optional[float] = None
    pi_stream_rate_hz: Optional[float] = None
    pi_stream_decimation: Optional[int] = None

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "PiStreamMeta":
        sensor_ids_raw = mapping.get("sensor_ids", [])
        sensor_ids: list[int] = []
        if isinstance(sensor_ids_raw, Mapping):
            # shouldn't happen, but be defensive
            sensor_ids = [int(v) for v in sensor_ids_raw.values()]
        elif isinstance(sensor_ids_raw, (list, tuple)):
            try:
                sensor_ids = [int(s) for s in sensor_ids_raw]
            except Exception:
                sensor_ids = []
        else:
            sensor_ids = []

        def _as_float(key: str) -> Optional[float]:
            value = mapping.get(key)
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _as_int(key: str) -> Optional[int]:
            value = mapping.get(key)
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        return cls(
            sensor_ids=sorted(sensor_ids),
            pi_device_sample_rate_hz=_as_float("pi_device_sample_rate_hz"),
            pi_stream_rate_hz=_as_float("pi_stream_rate_hz"),
            pi_stream_decimation=_as_int("pi_stream_decimation"),
        )


@dataclass
class PCStreamSummary:
    """PC-side measurement of streamed samples."""

    elapsed_s: float
    total_samples: int
    per_sensor_counts: Dict[int, int] = field(default_factory=dict)
    per_sensor_rate_hz: Dict[int, float] = field(default_factory=dict)
    total_rate_hz: Optional[float] = None
    session_dir: Optional[str] = None  # remote Pi output directory for this run


@dataclass
class PiRecordSummary:
    """
    Parsed summary from debug_log_sample_rate.py.

    Values are per-sensor where possible; if debug_log_sample_rate could not
    resolve a sensor_id for a file, that file is ignored in the per-sensor map.
    """

    per_sensor_estimated_rate_hz: Dict[int, float] = field(default_factory=dict)
    per_sensor_meta_device_rate_hz: Dict[int, float] = field(default_factory=dict)
    per_sensor_meta_requested_rate_hz: Dict[int, float] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Helpers: host selection & config loading
# --------------------------------------------------------------------------- #


def pick_host(inventory: HostInventory, host_name: Optional[str]) -> Tuple[HostConfig, Mapping[str, object]]:
    """
    Resolve a host from hosts.yaml.

    Returns (HostConfig dataclass, raw host mapping).
    """
    hosts = inventory.list_hosts()
    if not hosts:
        raise RuntimeError("No hosts configured in hosts.yaml")

    selected_raw: Optional[Mapping[str, object]] = None

    if host_name:
        for h in hosts:
            if not isinstance(h, Mapping):
                continue
            name = str(h.get("name") or h.get("host") or "").strip()
            if name == host_name:
                selected_raw = h
                break
        if selected_raw is None:
            available = ", ".join(str(h.get("name") or h.get("host") or "?") for h in hosts if isinstance(h, Mapping))
            raise RuntimeError(f"Host '{host_name}' not found in hosts.yaml. Available: {available}")
    else:
        # Default to the first host
        selected_raw = hosts[0]

    host_cfg = inventory.to_host_config(selected_raw)
    return host_cfg, selected_raw  # type: ignore[return-value]


def load_expected_rates(app_cfg: AppConfig) -> Tuple[SamplingConfig, ExpectedRates]:
    """
    Load SamplingConfig and derived expected rates from sensors.yaml (sensor defaults).
    """
    sensors_mapping = app_cfg.sensor_defaults or {}
    sampling_cfg = app_cfg.sampling_config
    if not isinstance(sampling_cfg, SamplingConfig):
        sampling_cfg = SamplingConfig.from_mapping(sensors_mapping)

    display = GuiSamplingDisplay.from_sampling(sampling_cfg)
    expected = ExpectedRates(
        device_rate_hz=float(display.device_rate_hz),
        record_rate_hz=float(display.record_rate_hz),
        stream_rate_hz=float(display.stream_rate_hz),
        mode_label=str(display.mode_label),
    )
    return sampling_cfg, expected


def load_app_config_and_defaults() -> AppConfig:
    """
    Build an AppConfig using SensorDefaults (sensors.yaml) as the source of truth.
    """
    sensor_defaults = SensorDefaults()
    raw_defaults = sensor_defaults.load()
    sampling_cfg = SamplingConfig.from_mapping(raw_defaults)
    return AppConfig(sensor_defaults=raw_defaults, sampling_config=sampling_cfg)


# --------------------------------------------------------------------------- #
# Stream meta parsing
# --------------------------------------------------------------------------- #


def extract_pi_meta_and_wrap_stream(lines: Iterable[str]) -> Tuple[Optional[PiStreamMeta], Iterable[str]]:
    """
    Consume an iterable of lines from mpu6050_multi_logger and peel off the
    leading JSON meta header if present.

    Returns (PiStreamMeta or None, iterable of remaining lines without the meta).
    """
    iterator = iter(lines)
    try:
        first_line = next(iterator)
    except StopIteration:
        return None, iter(())

    text = first_line.strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            # Not JSON meta; push it back into the stream.
            def _combined() -> Iterator[str]:
                yield first_line
                yield from iterator

            return None, _combined()

        if obj.get("meta") == "mpu6050_stream_config":
            pi_meta = PiStreamMeta.from_mapping(obj)

            # Meta consumed; the rest of the stream are data + summary lines.
            return pi_meta, iterator

        # Some other JSON we don't understand; push it back.
        def _combined2() -> Iterator[str]:
            yield first_line
            yield from iterator

        return None, _combined2()

    # Non-JSON first line; just pass everything through.
    def _combined3() -> Iterator[str]:
        yield first_line
        yield from iterator

    return None, _combined3()


# --------------------------------------------------------------------------- #
# PC stream measurement
# --------------------------------------------------------------------------- #


def measure_pc_stream(sample_stream: Iterable[str]) -> PCStreamSummary:
    """
    Consume sample lines from the Pi and estimate per-sensor stream rates.

    Uses the logger's own t_s field when available (preferred), falling back
    to wall-clock time if necessary. Also captures the "Output directory: ..."
    line emitted by mpu6050_multi_logger to identify the Pi log folder.
    """
    counts: Counter[int] = Counter()
    total_samples = 0
    first_t_s: Optional[float] = None
    last_t_s: Optional[float] = None
    session_dir: Optional[str] = None

    start_wall = time.perf_counter()

    for raw in sample_stream:
        line = raw.strip()

        # Capture output directory from the run summary.
        if line.startswith("Output directory:"):
            session_dir = line.split(":", 1)[1].strip()
            continue

        # Everything else we try to parse as an MpuSample
        try:
            sample = parse_mpu_line(raw)
        except Exception:
            # Non-sample line (e.g. logger summary); ignore.
            continue

        if sample is None:
            continue

        total_samples += 1
        sensor_id = int(sample.sensor_id) if getattr(sample, "sensor_id", None) is not None else 0
        counts[sensor_id] += 1

        t_s = getattr(sample, "t_s", None)
        if t_s is not None:
            try:
                t_val = float(t_s)
            except (TypeError, ValueError):
                t_val = None
            if t_val is not None:
                if first_t_s is None:
                    first_t_s = t_val
                last_t_s = t_val

    end_wall = time.perf_counter()
    wall_elapsed = max(0.0, end_wall - start_wall)

    # Prefer the device's own relative timestamps when possible.
    if first_t_s is not None and last_t_s is not None and last_t_s > first_t_s:
        elapsed = last_t_s - first_t_s
    else:
        elapsed = wall_elapsed if wall_elapsed > 0 else 1e-9

    per_sensor_rate_hz = {sid: cnt / elapsed for sid, cnt in counts.items()}
    total_rate_hz: Optional[float] = total_samples / elapsed if elapsed > 0 else None

    return PCStreamSummary(
        elapsed_s=elapsed,
        total_samples=total_samples,
        per_sensor_counts=dict(counts),
        per_sensor_rate_hz=per_sensor_rate_hz,
        total_rate_hz=total_rate_hz,
        session_dir=session_dir,
    )


# --------------------------------------------------------------------------- #
# Pi log rate parsing (debug_log_sample_rate.py output)
# --------------------------------------------------------------------------- #


def parse_log_rate_output(text: str) -> PiRecordSummary:
    """
    Parse the text output from raspberrypi_scripts/debug_log_sample_rate.py.

    We look for blocks like::

        === Sample rate check ===
        File: /home/pi/logs/mpu/...
        sensor_id: 1
        ...
        estimated_rate: 199.8 Hz
        meta.device_rate_hz: 200.0 Hz (delta: ...)
        meta.requested_rate_hz: 200.0 Hz

    and aggregate per-sensor estimates.
    """
    summary = PiRecordSummary()

    cur_sid: Optional[int] = None
    cur_est: Optional[float] = None
    cur_dev: Optional[float] = None
    cur_req: Optional[float] = None

    def _commit() -> None:
        nonlocal cur_sid, cur_est, cur_dev, cur_req
        if cur_sid is None:
            return
        sid = cur_sid
        if cur_est is not None:
            summary.per_sensor_estimated_rate_hz[sid] = cur_est
        if cur_dev is not None:
            summary.per_sensor_meta_device_rate_hz[sid] = cur_dev
        if cur_req is not None:
            summary.per_sensor_meta_requested_rate_hz[sid] = cur_req

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        if line.startswith("=== Sample rate check"):
            _commit()
            cur_sid = None
            cur_est = None
            cur_dev = None
            cur_req = None
            continue

        if line.startswith("sensor_id:"):
            sid_str = line.split(":", 1)[1].strip()
            try:
                cur_sid = int(sid_str)
            except ValueError:
                # May be "mixed [1, 2]" or "(unknown)"; ignore for per-sensor map.
                cur_sid = None
            continue

        if line.startswith("estimated_rate:"):
            # e.g. "estimated_rate: 199.8 Hz"
            after_colon = line.split(":", 1)[1].strip()
            token = after_colon.split()[0]
            try:
                cur_est = float(token)
            except ValueError:
                cur_est = None
            continue

        if line.startswith("meta.device_rate_hz:"):
            after_colon = line.split(":", 1)[1].strip()
            token = after_colon.split()[0]
            try:
                cur_dev = float(token)
            except ValueError:
                cur_dev = None
            continue

        if line.startswith("meta.requested_rate_hz:"):
            after_colon = line.split(":", 1)[1].strip()
            token = after_colon.split()[0]
            try:
                cur_req = float(token)
            except ValueError:
                cur_req = None
            continue

    _commit()
    return summary


def run_remote_log_rate_check(recorder: PiRecorder, session_dir: str) -> PiRecordSummary:
    """
    Run debug_log_sample_rate.py on the Pi for the given session directory.

    Returns a parsed PiRecordSummary and also prints the raw debug_log_sample_rate
    output so you can see full details.
    """
    print("\n=== Pi log sampling-rate check ===")
    print(f"Remote session directory: {session_dir}")

    # PiRecorder.start_logger will run the script in base_path on the Pi.
    stdout_fh, stderr_fh = recorder.start_logger("debug_log_sample_rate.py", [session_dir])

    out_bytes = stdout_fh.read()
    err_bytes = stderr_fh.read()
    out_text = out_bytes.decode("utf-8", errors="replace") if isinstance(out_bytes, (bytes, bytearray)) else str(out_bytes)
    err_text = err_bytes.decode("utf-8", errors="replace") if isinstance(err_bytes, (bytes, bytearray)) else str(err_bytes)

    if err_text.strip():
        print("--- debug_log_sample_rate.py stderr (Pi) ---")
        print(err_text.rstrip())
        print("--- end stderr ---\n")

    if out_text.strip():
        print("--- debug_log_sample_rate.py stdout (Pi) ---")
        print(out_text.rstrip())
        print("--- end stdout ---\n")
    else:
        print("debug_log_sample_rate.py did not produce any output.")
        return PiRecordSummary()

    return parse_log_rate_output(out_text)


# --------------------------------------------------------------------------- #
# Pi logger configuration and stream run
# --------------------------------------------------------------------------- #


def build_pi_logger_config(
    sampling: SamplingConfig,
    host_cfg: HostConfig,
    remote_logs_root: str,
    session_name: str,
    duration_s: float,
) -> PiLoggerConfig:
    """
    Construct a PiLoggerConfig for a short record+stream run.

    - device_rate_hz comes from SamplingConfig (single-rate source of truth).
    - We pass extra CLI flags so the Pi logger:
        * runs for a finite --duration,
        * writes logs under remote_logs_root,
        * uses the given session name,
        * sets --gui-mode so it behaves like the GUI-driven runs.
    """
    extra_cli: Dict[str, object] = {
        "gui-mode": True,
        "duration": max(0.1, float(duration_s)),
    }

    if session_name:
        extra_cli["session-name"] = session_name

    if remote_logs_root:
        # mpu6050_multi_logger will create a sensor-specific subdir (mpu) under this.
        extra_cli["out"] = remote_logs_root

    return PiLoggerConfig.from_sampling(sampling, extra_cli=extra_cli)


def ssh_smoke_test(recorder: PiRecorder, remote_scripts_root: str, remote_logs_root: str) -> None:
    """
    Very lightweight Pi reachability / environment check.

    - Connects over SSH.
    - Checks that the scripts directory and logs root directory exist on the Pi.
    """
    print("=== Pi reachability / SSH smoke-test ===")
    try:
        recorder.connect()
    except Exception as exc:  # pragma: no cover - best effort diagnostic
        print(f"SSH connect failed: {exc!r}")
        print("Skipping further Pi checks.\n")
        return

    client = recorder.client

    def _check(path: str, label: str) -> None:
        try:
            exists = client.path_exists(path)
        except Exception as exc:  # pragma: no cover - best effort diagnostic
            print(f"  {label}: {path} -> error: {exc!r}")
            return
        print(f"  {label}: {path} -> {'OK' if exists else 'MISSING'}")

    _check(remote_scripts_root, "scripts dir")
    _check(remote_logs_root, "logs root")
    print("")


def run_stream_test(
    recorder: PiRecorder,
    sampling: SamplingConfig,
    host_cfg: HostConfig,
    remote_logs_root: str,
    session_name: str,
    duration_s: float,
) -> Tuple[Optional[PiStreamMeta], PCStreamSummary, str]:
    """
    Run a short record+stream exercise on the Pi and measure the PC stream rate.

    Returns:
        (PiStreamMeta or None, PCStreamSummary, remote_session_dir)
    """
    logger_cfg = build_pi_logger_config(
        sampling=sampling,
        host_cfg=host_cfg,
        remote_logs_root=remote_logs_root,
        session_name=session_name,
        duration_s=duration_s,
    )

    print("=== Starting Pi logger (record + stream) ===")
    print(f"Requested device rate (SamplingConfig): {sampling.device_rate_hz:.3f} Hz")
    print(f"Session name: {session_name!r}")
    print(f"Remote logs root: {remote_logs_root}")
    print("Logger command (on Pi):")
    print(f"  python3 {logger_cfg.logger_script} {logger_cfg.build_command()}")  # type: ignore[arg-type]
    print("")

    raw_stream = recorder.stream_mpu6050(logger_cfg, recording_enabled=True)
    pi_meta, sample_stream = extract_pi_meta_and_wrap_stream(raw_stream)

    if pi_meta is not None:
        print("Pi stream meta header:")
        print(f"  sensor_ids: {pi_meta.sensor_ids}")
        print(f"  pi_device_sample_rate_hz: {pi_meta.pi_device_sample_rate_hz}")
        print(f"  pi_stream_rate_hz:       {pi_meta.pi_stream_rate_hz}")
        print(f"  pi_stream_decimation:    {pi_meta.pi_stream_decimation}")
        print("")

    stream_summary = measure_pc_stream(sample_stream)

    # Determine session directory for this run
    session_dir = stream_summary.session_dir
    if not session_dir:
        # Fallback: we know the logger will put data under <logs_root>/mpu when
        # a session name is provided. We don't try to guess host slugs here.
        base = remote_logs_root.rstrip("/") or "/"
        session_dir = f"{base.rstrip('/')}/{LOG_SUBDIR_MPU}"
        if session_name:
            # debug_log_sample_rate.py accepts both the per-session directory
            # and the broader logs directory; pointing at the root is fine if
            # per-session is not obvious.
            pass

    return pi_meta, stream_summary, session_dir


# --------------------------------------------------------------------------- #
# CLI and main
# --------------------------------------------------------------------------- #


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified sampling / streaming / recording debugger for SensePi."
    )
    parser.add_argument(
        "--host-name",
        type=str,
        default=None,
        help="Host name from hosts.yaml (defaults to the first configured host).",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=10.0,
        help="Duration of the Pi logging run in seconds (default: 10).",
    )
    parser.add_argument(
        "--session-name",
        type=str,
        default="",
        help=(
            "Session name label for this test. "
            "Defaults to 'sampling_debug_<timestamp>' if omitted."
        ),
    )
    parser.add_argument(
        "--logs-dir",
        type=str,
        default=None,
        help=(
            "Override the Pi logs root directory. "
            "If omitted, uses the host's data_dir from hosts.yaml."
        ),
    )
    parser.add_argument(
        "--no-ssh-debug",
        action="store_true",
        help="Skip the SSH smoke-test (basic Pi reachability check).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)

    # ------------------------------------------------------------------ PC config
    app_cfg = load_app_config_and_defaults()
    sampling_cfg, expected = load_expected_rates(app_cfg)

    print("=== PC sampling expectations (from sensors.yaml) ===")
    print(f"Mode:        {expected.mode_label}")
    print(f"device_rate: {expected.device_rate_hz:.3f} Hz")
    print(f"record_rate: {expected.record_rate_hz:.3f} Hz")
    print(f"stream_rate: {expected.stream_rate_hz:.3f} Hz")
    print("")

    # ------------------------------------------------------------------ Host / Pi setup
    inventory = HostInventory()
    host_cfg, host_raw = pick_host(inventory, args.host_name)
    remote_host = inventory.to_remote_host(host_raw)

    # Normalize remote paths for the Pi (avoid local expanduser semantics).
    remote_scripts_root = normalize_remote_path(host_cfg.base_path, host_cfg.user)
    # logs root can be overridden from CLI, otherwise use host_cfg.data_dir.
    logs_root_raw = args.logs_dir or host_cfg.data_dir
    remote_logs_root = normalize_remote_path(logs_root_raw, host_cfg.user)

    print("=== Host configuration ===")
    host_label = host_cfg.name or remote_host.name or remote_host.host
    print(f"Host label:         {host_label}")
    print(f"SSH target:         {remote_host.user}@{remote_host.host}:{remote_host.port}")
    print(f"Remote scripts dir: {remote_scripts_root}")
    print(f"Remote logs root:   {remote_logs_root}")
    print("")

    recorder = PiRecorder(remote_host, base_path=Path(remote_scripts_root))

    if not args.no_ssh_debug:
        ssh_smoke_test(recorder, remote_scripts_root, remote_logs_root)

    # Default session name if not provided
    session_name = args.session_name.strip()
    if not session_name:
        session_name = f"sampling_debug_{int(time.time())}"

    # ------------------------------------------------------------------ Pi run + PC stream measurement
    pi_meta, stream_summary, session_dir = run_stream_test(
        recorder=recorder,
        sampling=sampling_cfg,
        host_cfg=host_cfg,
        remote_logs_root=remote_logs_root,
        session_name=session_name,
        duration_s=args.seconds,
    )

    # ------------------------------------------------------------------ Pi log-rate check
    pi_record_summary = run_remote_log_rate_check(recorder, session_dir)

    try:
        recorder.close()
    except Exception:
        pass

    # ------------------------------------------------------------------ Unified summary
    print("=== Sampling / Streaming / Recording summary ===")

    print("\nConfig / expectations (PC):")
    print(f"  device_rate_hz (sensors.yaml): {expected.device_rate_hz:.3f} Hz")
    print(f"  record_rate_hz (PC view):      {expected.record_rate_hz:.3f} Hz")
    print(f"  stream_rate_hz (PC view):      {expected.stream_rate_hz:.3f} Hz")

    if pi_meta is not None:
        print("\nPi logger (stream meta header):")
        print(f"  sensor_ids:                 {pi_meta.sensor_ids}")
        print(f"  pi_device_sample_rate_hz:   {pi_meta.pi_device_sample_rate_hz}")
        print(f"  pi_stream_rate_hz:          {pi_meta.pi_stream_rate_hz}")
        print(f"  pi_stream_decimation:       {pi_meta.pi_stream_decimation}")

    print("\nPi → PC raw stream (this run):")
    print(f"  Effective duration (t_s):    {stream_summary.elapsed_s:.3f} s")
    print(f"  Total samples parsed:        {stream_summary.total_samples}")
    if stream_summary.total_rate_hz is not None:
        print(f"  Total effective rate:        {stream_summary.total_rate_hz:.3f} Hz")

    if stream_summary.per_sensor_counts:
        for sid in sorted(stream_summary.per_sensor_counts.keys()):
            count = stream_summary.per_sensor_counts.get(sid, 0)
            rate = stream_summary.per_sensor_rate_hz.get(sid)
            if rate is None:
                print(f"  S{sid}: {count} samples")
                continue
            line = f"  S{sid}: {count} samples, pc_stream_rate ≈ {rate:.3f} Hz"
            if pi_meta and pi_meta.pi_stream_rate_hz:
                expected_pi = float(pi_meta.pi_stream_rate_hz)
                if expected_pi > 0:
                    delta = rate - expected_pi
                    pct = 100.0 * delta / expected_pi
                    line += f" (Δ {delta:+.3f} Hz, {pct:+.2f} % vs Pi stream)"
            print(line)
    else:
        print("  No samples parsed from stream (check SSH and logger output above).")

    print("\nPi recorded logs (debug_log_sample_rate.py):")
    if not pi_record_summary.per_sensor_estimated_rate_hz:
        print("  No per-sensor estimates parsed from debug_log_sample_rate output.")
    else:
        all_sids = sorted(pi_record_summary.per_sensor_estimated_rate_hz.keys())
        for sid in all_sids:
            est = pi_record_summary.per_sensor_estimated_rate_hz.get(sid)
            meta_dev = pi_record_summary.per_sensor_meta_device_rate_hz.get(sid)
            meta_req = pi_record_summary.per_sensor_meta_requested_rate_hz.get(sid)
            line = f"  S{sid}: estimated_record_rate ≈ {est:.3f} Hz"
            if meta_dev is not None and meta_dev > 0:
                delta = est - meta_dev
                pct = 100.0 * delta / meta_dev
                line += f" (meta.device_rate_hz {meta_dev:.3f} Hz, Δ {delta:+.3f} Hz, {pct:+.2f} %)"
            if meta_req is not None:
                line += f" [meta.requested_rate_hz {meta_req:.3f} Hz]"
            print(line)

    print("\nDone.")


if __name__ == "__main__":
    main()
