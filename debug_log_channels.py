#!/usr/bin/env python
# debug_log_channels.py
"""
Inspect which MPU6050 channels are present and active in a log file.

Each sensor can have up to six numeric channels:

    ax, ay, az, gx, gy, gz

In many deployments we intentionally only use three channels per sensor
(ax, ay, gz) to match the GUI's 3-of-6 "default3" view and 9-plot layout.
This script reads a CSV or JSONL log produced by mpu6050_multi_logger.py
and reports, per sensor_id, which of the six channels ever carry a
non-zero, non-NaN value. It is a quick sanity check of 3-of-6 vs all-6 usage.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

ALL_CHANNELS = ("ax", "ay", "az", "gx", "gy", "gz")


def _load_rows_csv(path: Path) -> Iterable[Dict[str, Any]]:
    """Yield rows from a CSV log as dictionaries."""
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield dict(row)


def _load_rows_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    """Yield rows from a JSONL log as dictionaries."""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def _parse_sensor_id(row: Mapping[str, Any]) -> Any:
    """Parse sensor_id from a row, returning int when possible."""
    sid_val = row.get("sensor_id")
    if sid_val is None or sid_val == "":
        return None
    try:
        return int(sid_val)
    except (TypeError, ValueError):
        # Fall back to the raw value; we'll stringify it later
        return sid_val


def _value_is_active(value: Any) -> bool:
    """
    Return True when a channel value should be considered "active".

    - Missing / empty / non-numeric values -> inactive
    - 0.0 and NaN -> inactive
    - Any other numeric value -> active
    """
    if value is None:
        return False
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return False
        try:
            value = float(value)
        except ValueError:
            return False

    if isinstance(value, (int, float)):
        v = float(value)
        if v == 0.0 or math.isnan(v):
            return False
        return True

    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Report which of the 6 possible MPU6050 channels (ax, ay, az, gx, gy, gz)\n"
            "are present and active per sensor in a log file."
        )
    )
    parser.add_argument(
        "path",
        help="Path to a CSV or JSONL log produced by mpu6050_multi_logger.py.",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.is_file():
        raise SystemExit(f"Path is not a file: {path}")

    suffix = path.suffix.lower()
    if suffix.endswith(".csv"):
        rows_iter = _load_rows_csv(path)
    elif suffix.endswith(".jsonl"):
        rows_iter = _load_rows_jsonl(path)
    else:
        raise SystemExit(f"Unsupported log extension: {path.suffix!r}")

    present_cols = set()
    # sensor_id -> channel_name -> active_flag
    coverage: Dict[Any, Dict[str, bool]] = {}

    for row in rows_iter:
        present_cols.update(row.keys())
        sid = _parse_sensor_id(row)
        if sid not in coverage:
            coverage[sid] = {ch: False for ch in ALL_CHANNELS}
        chan_flags = coverage[sid]
        for ch in ALL_CHANNELS:
            if ch in row and not chan_flags[ch] and _value_is_active(row[ch]):
                chan_flags[ch] = True

    print("=== Channel coverage ===")
    print(f"File: {path}")
    if present_cols:
        print(f"Present columns: {', '.join(sorted(present_cols))}")
    else:
        print("Present columns: (none)")

    used_channels = sorted(ch for ch in ALL_CHANNELS if ch in present_cols)
    print(
        f"Max channels per sensor is {len(ALL_CHANNELS)} "
        f"({', '.join(ALL_CHANNELS)}); this log uses {len(used_channels)}."
    )

    if not coverage:
        print("No rows found in log; nothing to report.")
        return

    # Sort sensor_ids in a stable way (None last)
    def _sort_key(sid: Any) -> tuple:
        return (sid is None, str(sid))

    for sid in sorted(coverage.keys(), key=_sort_key):
        if sid is None:
            print("\nSensor (unknown):")
        else:
            print(f"\nSensor {sid}:")

        chan_flags = coverage[sid]
        active = [ch for ch in ALL_CHANNELS if chan_flags.get(ch)]
        inactive = [ch for ch in ALL_CHANNELS if ch not in active]

        if active:
            print(f"  active: {', '.join(active)}")
        else:
            print("  active: (none)")

        if inactive:
            print(f"  inactive: {', '.join(inactive)}")
        else:
            print("  inactive: (none)")

        if len(active) > 3:
            sid_label = sid if sid is not None else "(unknown)"
            print(
                f"  NOTE: sensor {sid_label} uses "
                f"{len(active)}/{len(ALL_CHANNELS)} channels "
                f"({', '.join(active)})."
            )


if __name__ == "__main__":
    main()
