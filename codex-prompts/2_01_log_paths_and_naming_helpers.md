# SensePi Implementation Prompt 1 – Centralized Log Path & Naming Helpers

You are working on the **SensePi** project, which has:
- Raspberry Pi logging scripts under `raspberrypi_scripts/` (especially `mpu6050_multi_logger.py`).
- A PySide6 GUI app under `src/sensepi/gui/`.
- Configuration helpers under `src/sensepi/config/` (e.g. `app_config.py`, `sampling.py`, etc.).

This prompt is focused on introducing **centralized helpers for log paths and naming conventions** so that both the Pi and PC sides use the same logic.

---

## Goal

Implement a small, clearly documented helper module that encapsulates:
- Default log root locations on Pi and PC.
- Sensor-specific log subfolder names (e.g. `"mpu"`).
- Session name slugging.
- Log filename construction and accompanying `.meta.json` sidecar paths.

The aim is to **reduce magic strings**, **avoid duplicated logic**, and make the log layout obvious for students.

**Important constraint:** Do not change existing CLI options or config keys. Behaviour must remain effectively the same (same default paths and filenames) unless they were clearly buggy (like double session directory nesting on the PC side, which is handled in Prompt 3).

---

## Where to work

Create a new module in the config package, for example:

- `src/sensepi/config/log_paths.py`

You may also add imports in:

- `raspberrypi_scripts/mpu6050_multi_logger.py`
- `src/sensepi/gui/tab_offline.py` (or whatever module handles offline sync)
- Any `remote/` helpers that do path computations (e.g. log sync / downloader code).

---

## API to implement

Implement the following minimal API (you can extend it if needed, but keep it small and well-documented):

```python
# src/sensepi/config/log_paths.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import re
import datetime as _dt


# ---- Constants ---------------------------------------------------------

# Pi-side default log root (matches pi_config.yaml default)
DEFAULT_PI_LOG_ROOT = Path("~").expanduser() / "logs"

# PC-side default raw data root (matches existing AppPaths behaviour)
# You can import this from app_config if that is cleaner.
DEFAULT_PC_RAW_ROOT = Path("data") / "raw"

# Sensor-specific subdirectory names
LOG_SUBDIR_MPU = "mpu"  # used on both Pi and PC


# ---- Session slugging --------------------------------------------------

def slugify_session_name(name: str) -> str:
    """Return a filesystem-safe slug for a user-provided session name.

    - Lowercase
    - Strip leading/trailing whitespace
    - Replace runs of non-alphanumeric chars with a single hyphen
    - Remove leading/trailing hyphen
    """
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    return name or "session"
```

```python
# ---- Pi-side helpers ---------------------------------------------------

def build_pi_session_dir(
    sensor_prefix: str,
    session_name: Optional[str],
    base_dir: Path | str | None = None,
) -> Path:
    """Return the directory on the Pi where this session's logs should be stored.

    For MPU logs we expect:
        DEFAULT_PI_LOG_ROOT / LOG_SUBDIR_MPU / <session_slug or no subdir>

    Behaviour must match the existing mpu6050_multi_logger.py defaults:
    - If session_name is None/empty, use the sensor subdir directly.
    - If session_name is provided, create a subdirectory using the slug.
    """
    root = Path(base_dir).expanduser() if base_dir is not None else DEFAULT_PI_LOG_ROOT
    sensor_root = root / sensor_prefix

    if not session_name:
        return sensor_root

    slug = slugify_session_name(session_name)
    return sensor_root / slug
```

```python
# ---- Filename helpers --------------------------------------------------

def _format_start_ts(start_dt: _dt.datetime) -> str:
    return start_dt.strftime("%Y-%m-%d_%H-%M-%S")


@dataclass(frozen=True)
class LogFilePaths:
    data_path: Path
    meta_path: Path


def build_log_file_paths(
    sensor_prefix: str,
    session_name: Optional[str],
    sensor_id: int,
    start_dt: _dt.datetime,
    format_ext: str,
    out_dir: Path,
) -> LogFilePaths:
    """Return full paths for the data file and its .meta.json sidecar.

    Filename pattern (data_path.name):

        [<session_slug>_]<sensorPrefix>_S<sensorID>_<timestamp>.<ext>

    Where:
    - session_slug is slugified session_name, optional
    - sensorPrefix is e.g. "mpu"
    - sensorID is 1-based index
    - timestamp is start_dt formatted as YYYY-MM-DD_HH-MM-SS
    - ext is "csv" or "jsonl"

    meta_path uses the same name with an added ".meta.json" suffix.
    """
    ts_str = _format_start_ts(start_dt)
    session_slug = slugify_session_name(session_name) if session_name else ""

    if session_slug:
        stem = f"{session_slug}_{sensor_prefix}_S{sensor_id}_{ts_str}"
    else:
        stem = f"{sensor_prefix}_S{sensor_id}_{ts_str}"

    # Ensure format_ext has no leading dot
    format_ext = format_ext.lstrip(".")
    filename = f"{stem}.{format_ext}"

    data_path = out_dir / filename
    meta_path = data_path.with_suffix(data_path.suffix + ".meta.json")
    return LogFilePaths(data_path=data_path, meta_path=meta_path)
```

You may choose slightly different names, but keep the behaviour and intent the same.

---

## Integration notes

- In later prompts you will **replace ad-hoc path and filename code** in:
  - `mpu6050_multi_logger.py`
  - PC-side offline sync code
- For now, just create this module and make sure it is importable from both sides.
- Add short docstrings and comments explaining that these functions codify the “Log Conventions” described in the README.
- Do not introduce any runtime dependencies beyond `pathlib`, `dataclasses`, and `re`/`datetime` which are already in the standard library.

When you’re done, run the existing tests (if any) or at least run `mpu6050_multi_logger.py --help` and a quick manual run to ensure there are no import errors.
