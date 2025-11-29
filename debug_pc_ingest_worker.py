#!/usr/bin/env python
# debug_pc_ingest_worker.py
"""
Debug SensorIngestWorker + PiRecorder in a minimal Qt event loop.

Run from project root:

    python debug_pc_ingest_worker.py
    python debug_pc_ingest_worker.py --seconds 5 --host-name Pi06

This uses hosts.yaml via HostInventory to pick the Pi, starts
PiRecorder.stream_mpu6050(...), and then feeds that stream into a
SensorIngestWorker running in a QThread. It counts how many samples
arrive per sensor_id.

Each MPU6050 sensor can provide up to 6 channels (ax, ay, az, gx, gy, gz).
This script does not inspect the channel values; it only counts how many
MpuSample instances arrive per sensor_id via SensorIngestWorker.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys
import time
from typing import Any, Dict

from PySide6.QtCore import QCoreApplication, QObject, QThread, QTimer, Slot  # type: ignore

# --- Make src/ importable ----------------------------------------------------
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sensepi.config.app_config import HostInventory  # type: ignore
from sensepi.remote.pi_recorder import PiRecorder  # type: ignore
from sensepi.remote.sensor_ingest_worker import SensorIngestWorker  # type: ignore
from sensepi.core.live_stream import select_parser  # type: ignore
from sensepi.sensors.mpu6050 import MpuSample  # type: ignore


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

    return hosts[0]


def build_recorder(inv: HostInventory, host_dict: Dict[str, Any]) -> PiRecorder:
    """
    Construct a PiRecorder for the given host mapping from hosts.yaml.

    Uses HostInventory.to_remote_host(...) and HostInventory.scripts_dir_for(...)
    so behaviour matches the GUI's RecorderTab.
    """
    remote_host = inv.to_remote_host(host_dict)
    base_path = inv.scripts_dir_for(host_dict)
    print(
        f"Using host {host_dict.get('name', remote_host.host)} "
        f"at {remote_host.host}:{remote_host.port}, "
        f"base_path={base_path}"
    )
    return PiRecorder(remote_host, base_path=base_path)


class IngestDebug(QObject):
    """
    Small helper that owns a SensorIngestWorker in a QThread and keeps
    per-sensor sample counts for a fixed duration.
    """

    def __init__(
        self,
        recorder: PiRecorder,
        stream,
        seconds: float,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._recorder = recorder
        self._stream = stream
        self._seconds = float(seconds)
        if self._seconds < 0:
            self._seconds = 0.0

        self._thread = QThread(self)
        parser = select_parser("mpu6050")

        def _stream_factory():
            # Mirror RecorderTab: return the same iterator; the worker will
            # consume it until stopped or the remote process exits.
            return self._stream

        self._worker = SensorIngestWorker(
            recorder=self._recorder,
            stream_factory=_stream_factory,
            parser=parser,
            batch_size=50,
            max_latency_ms=100,
            stream_label="mpu6050",
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)

        self._worker.samples_batch.connect(self.on_batch)
        self._worker.error.connect(self.on_error)
        self._worker.finished.connect(self.on_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        app = QCoreApplication.instance()
        if app is not None:
            self._worker.finished.connect(app.quit)

        self._counts: Counter[int] = Counter()
        self._total = 0
        self._t_start: float | None = None

        # Hard stop after N seconds (even if the stream keeps running)
        if self._seconds > 0:
            QTimer.singleShot(int(self._seconds * 1000), self.stop)

    @Slot()
    def start(self) -> None:
        print("[INGEST] Starting QThread + worker...")
        self._t_start = time.time()
        self._thread.start()

    @Slot()
    def stop(self) -> None:
        print("[INGEST] stop() requested")
        try:
            self._worker.stop()
        except Exception as exc:  # pragma: no cover
            print(f"[INGEST] stop() raised: {exc!r}")

    @Slot(list)
    def on_batch(self, samples: list) -> None:
        n = len(samples)
        self._total += n
        for s in samples:
            if isinstance(s, MpuSample) and s.sensor_id is not None:
                self._counts[int(s.sensor_id)] += 1
        print(f"[INGEST] got batch of {n} samples (total={self._total})")

    @Slot(str)
    def on_error(self, msg: str) -> None:
        print(f"[INGEST ERROR] {msg}")

    @Slot()
    def on_finished(self) -> None:
        print("[INGEST] finished")
        print(f"Total samples seen: {self._total}")

        elapsed: float | None = None
        if self._t_start is not None:
            elapsed = max(0.0, time.time() - self._t_start)
        elif self._seconds > 0:
            elapsed = self._seconds

        for sid in sorted(self._counts.keys()):
            count = self._counts[sid]
            if elapsed and elapsed > 0:
                approx_rate = count / elapsed
                print(
                    f"  sensor_id={sid}: {count} samples "
                    f"(~{approx_rate:.1f} Hz effective stream rate)"
                )
            else:
                print(f"  sensor_id={sid}: {count} samples")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run SensorIngestWorker + PiRecorder in a minimal Qt event loop\n"
            "and print per-sensor sample counts for a short window."
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
        default=5.0,
        help="How long to let the ingest worker run.",
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

    app = QCoreApplication(sys.argv)

    inv = HostInventory()
    host_dict = pick_host(inv, args.host_name)
    rec = build_recorder(inv, host_dict)

    def on_stderr(line: str) -> None:
        print(f"[REMOTE STDERR] {line}", flush=True)

    print("\n=== Starting PiRecorder.stream_mpu6050() for ingest debug ===")
    stream = rec.stream_mpu6050(
        extra_args=args.extra_args,
        recording=False,
        on_stderr=on_stderr,
    )

    dbg = IngestDebug(recorder=rec, stream=stream, seconds=args.seconds)
    QTimer.singleShot(0, dbg.start)

    app.exec()

    print("Qt event loop exited; closing recorder...")
    try:
        rec.close()
    except Exception as exc:  # pragma: no cover
        print(f"[WARN] rec.close() raised: {exc!r}")


if __name__ == "__main__":
    main()
