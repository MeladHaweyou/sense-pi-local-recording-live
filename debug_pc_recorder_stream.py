#!/usr/bin/env python
# debug_pc_recorder_stream.py
"""
Debug streaming using the SAME PiRecorder stack the GUI uses (no Qt).

Run from project root:

    python debug_pc_recorder_stream.py
    python debug_pc_recorder_stream.py --seconds 5
    python debug_pc_recorder_stream.py --host-name Pi06

This uses hosts.yaml via HostInventory to pick the Pi and then
PiRecorder.stream_mpu6050(...) to read JSON lines, just like RecorderTab.

Each MPU6050 sensor has up to 6 channels (ax, ay, az, gx, gy, gz), but the
GUI typically plots only three (ax, ay, gz) per sensor in the default view.
This script does not inspect channel values; it only counts how many
MpuSample rows arrive per sensor_id and estimates an effective stream rate.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys
import time
from typing import Any, Dict

# --- Make src/ importable ----------------------------------------------------
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sensepi.config.app_config import HostInventory  # type: ignore
from sensepi.remote.pi_recorder import PiRecorder  # type: ignore
from sensepi.sensors.mpu6050 import MpuSample, parse_line  # type: ignore


def pick_host(inv: HostInventory, name: str | None) -> Dict[str, Any]:
    """
    Pick a host entry from hosts.yaml by name (or the first one by default).
    """
    hosts = inv.list_hosts()
    if not hosts:
        raise SystemExit("No Pi hosts defined in hosts.yaml")

    if name:
        for h in hosts:
            if h.get("name") == name:
                return h
        raise SystemExit(
            f"Host {name!r} not found in hosts.yaml. "
            f"Available: {[h.get('name') for h in hosts]}"
        )

    # Default: first host
    return hosts[0]


def build_recorder(inv: HostInventory, host_dict: Dict[str, Any]) -> PiRecorder:
    """
    Construct a PiRecorder for the given host mapping from hosts.yaml.

    Uses HostInventory.to_remote_host(...) and HostInventory.scripts_dir_for(...)
    so the behaviour matches what the GUI's RecorderTab uses.
    """
    remote_host = inv.to_remote_host(host_dict)
    base_path = inv.scripts_dir_for(host_dict)
    print(
        f"Using host {host_dict.get('name', remote_host.host)} "
        f"at {remote_host.host}:{remote_host.port}, "
        f"base_path={base_path}"
    )
    return PiRecorder(remote_host, base_path=base_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Stream MPU6050 samples via PiRecorder.stream_mpu6050() and print\n"
            "per-sensor sample counts and approximate effective stream rates."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--host-name",
        type=str,
        default=None,
        help="Optional host name from hosts.yaml (e.g. Pi06)",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=3.0,
        help="How long to read from the stream (wall-clock seconds).",
    )
    parser.add_argument(
        "--extra-args",
        type=str,
        default="",
        help=(
            "Extra CLI args for mpu6050_multi_logger.py, e.g.:\n"
            "  --sample-rate-hz 300 --stream-every 3\n"
            "  --rate 100 --channels both --sensors 1,2,3 --stream-every 5"
        ),
    )
    args = parser.parse_args()

    inv = HostInventory()
    host_dict = pick_host(inv, args.host_name)
    rec = build_recorder(inv, host_dict)

    counts: Counter[int] = Counter()
    total = 0
    seconds = float(args.seconds)
    if seconds < 0:
        seconds = 0.0

    def on_stderr(line: str) -> None:
        print(f"[REMOTE STDERR] {line}", flush=True)

    stream = None
    try:
        print("\n=== Starting PiRecorder.stream_mpu6050() ===")
        print(f"extra_args: {args.extra_args!r}")
        stream = rec.stream_mpu6050(
            extra_args=args.extra_args,
            recording=False,
            on_stderr=on_stderr,
        )

        t_end = time.time() + seconds if seconds > 0 else None

        for raw in stream:
            if not raw:
                continue
            total += 1

            sample = parse_line(raw)
            if isinstance(sample, MpuSample) and sample.sensor_id is not None:
                counts[int(sample.sensor_id)] += 1

            # Show the first few lines for quick visual confirmation
            if total <= 5:
                print(f"[LINE] {raw.rstrip()}")

            if t_end is not None and time.time() >= t_end:
                break

    finally:
        # Try to close the stream iterator explicitly
        if stream is not None:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    print("Closing stream iterator...")
                    close()
                except Exception as exc:  # pragma: no cover
                    print(f"[WARN] stream.close() raised: {exc!r}")

        print("Closing PiRecorder...")
        try:
            rec.close()
        except Exception as exc:  # pragma: no cover
            print(f"[WARN] rec.close() raised: {exc!r}")

    print("\n=== Stream summary ===")
    print(f"Total lines read: {total}")

    elapsed = seconds if seconds > 0 else None
    for sid in sorted(counts.keys()):
        count = counts[sid]
        if elapsed and elapsed > 0:
            approx_rate = count / elapsed
            print(
                f"  sensor_id={sid}: {count} samples "
                f"(~{approx_rate:.1f} Hz effective stream rate)"
            )
        else:
            print(f"  sensor_id={sid}: {count} samples")

    if elapsed and elapsed > 0:
        print(
            "\nNote: the effective stream rate above is what reaches the PC "
            "after Pi-side decimation by --stream-every. The actual device "
            "sampling rate on the Pi is higher by that factor."
        )


if __name__ == "__main__":
    main()
