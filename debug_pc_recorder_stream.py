#!/usr/bin/env python
"""
Debug streaming using the SAME PiRecorder stack the GUI uses (no Qt).

Run from project root:

    python debug_pc_recorder_stream.py
    python debug_pc_recorder_stream.py --seconds 5
    python debug_pc_recorder_stream.py --host-name Pi06

This uses hosts.yaml via HostInventory to pick the Pi and then
PiRecorder.stream_mpu6050(...) to read JSON lines, just like RecorderTab.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys
import time

# --- Make src/ importable ----------------------------------------------------
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sensepi.config.app_config import HostInventory  # type: ignore
from sensepi.remote.pi_recorder import PiRecorder    # type: ignore
from sensepi.sensors.mpu6050 import MpuSample, parse_line  # type: ignore


def pick_host(inv: HostInventory, name: str | None):
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


def build_recorder(inv: HostInventory, host_dict: dict) -> PiRecorder:
    # host_dict is the raw mapping from hosts.yaml (inv.list_hosts())
    remote_host = inv.to_remote_host(host_dict)
    base_path = inv.scripts_dir_for(host_dict)
    print(
        f"Using host {host_dict.get('name', remote_host.host)} "
        f"at {remote_host.host}:{remote_host.port}, "
        f"base_path={base_path}"
    )
    return PiRecorder(remote_host, base_path=base_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host-name", type=str, default=None,
                        help="Optional host name from hosts.yaml (e.g. Pi06)")
    parser.add_argument("--seconds", type=float, default=3.0,
                        help="How long to read from the stream")
    parser.add_argument(
        "--extra-args",
        type=str,
        default="",
        help=(
            "Extra CLI args for mpu6050_multi_logger.py, e.g.: "
            "--rate 100 --channels both --sensors 1,2,3 --stream-every 5"
        ),
    )
    args = parser.parse_args()

    inv = HostInventory()
    host_dict = pick_host(inv, args.host_name)
    rec = build_recorder(inv, host_dict)

    counts: Counter[int] = Counter()
    total = 0

    def on_stderr(line: str) -> None:
        print(f"[REMOTE STDERR] {line}", flush=True)

    try:
        print("\n=== Starting PiRecorder.stream_mpu6050() ===")
        print(f"extra_args: {args.extra_args!r}")
        stream = rec.stream_mpu6050(
            extra_args=args.extra_args,
            recording=False,
            on_stderr=on_stderr,
        )

        t_end = time.time() + float(args.seconds)
        for raw in stream:
            if not raw:
                continue
            total += 1
            sample = parse_line(raw)
            if isinstance(sample, MpuSample) and sample.sensor_id is not None:
                counts[int(sample.sensor_id)] += 1

            # Show first few lines for visual confirmation
            if total <= 5:
                print(f"[LINE] {raw.rstrip()}")

            if time.time() >= t_end:
                break

        # Try to close the stream explicitly
        close = getattr(stream, "close", None)
        if callable(close):
            print("Closing stream iterator...")
            close()

    finally:
        print("Closing PiRecorder...")
        try:
            rec.close()
        except Exception as exc:  # pragma: no cover
            print(f"[WARN] rec.close() raised: {exc!r}")

    print("\n=== Stream summary ===")
    print(f"Total lines read: {total}")
    for sid in sorted(counts.keys()):
        print(f"  sensor_id={sid}: {counts[sid]} samples")


if __name__ == "__main__":
    main()
