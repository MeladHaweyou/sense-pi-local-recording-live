============================= DIRECTORY OVERVIEW =============================
Root: C:\Projects\sense-pi-local-recording-live-main\debuging codes
Timestamp: 03/12/2025  0:38:21,52

----------------------------- TREE (with files) -----------------------------
Folder PATH listing
Volume serial number is 46B7-CF63
C:\PROJECTS\SENSE-PI-LOCAL-RECORDING-LIVE-MAIN\DEBUGING CODES
    combine.bat
    combined.py
    debug_log_channels.py
    debug_pc_ingest_worker.py
    debug_pc_recorder_stream.py
    debug_pi_via_ssh.py
    
No subfolders exist 


------------------------- DETAILED DIRECTORY LISTING -------------------------
 Volume in drive C has no label.
 Volume Serial Number is 46B7-CF63

 Directory of C:\Projects\sense-pi-local-recording-live-main\debuging codes

03/12/2025  00:38    <DIR>          .
03/12/2025  00:38    <DIR>          ..
30/11/2025  16:51             2.329 combine.bat
03/12/2025  00:38               646 combined.py
30/11/2025  16:51             5.419 debug_log_channels.py
30/11/2025  16:51            11.822 debug_pc_ingest_worker.py
30/11/2025  16:51            10.294 debug_pc_recorder_stream.py
30/11/2025  16:51             4.522 debug_pi_via_ssh.py
               6 File(s)         35.032 bytes

     Total Files Listed:
               6 File(s)         35.032 bytes
               2 Dir(s)  762.580.271.104 bytes free

============================================================================

============================= combine.bat
# File: combine.bat (ext: .bat
# Dir : 
# Size: 2329 bytes
# Time: 30/11/2025 16:51
============================= combine.bat
@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ====== Configuration ======
set "OUTPUT_FILE=combined.py"

REM Use the current directory as the root (run this from your main folder)
set "ROOT=%CD%"
set "OUT_FULL=%ROOT%\%OUTPUT_FILE%"

REM Delete output file if it exists
del "%OUTPUT_FILE%" 2>nul

REM ================== Directory Details (Tree + Detailed DIR) ==================
>>"%OUTPUT_FILE%" echo ============================= DIRECTORY OVERVIEW =============================
>>"%OUTPUT_FILE%" echo Root: %ROOT%
>>"%OUTPUT_FILE%" echo Timestamp: %DATE% %TIME%
>>"%OUTPUT_FILE%" echo.
>>"%OUTPUT_FILE%" echo ----------------------------- TREE (with files) -----------------------------
tree "%ROOT%" /F >>"%OUTPUT_FILE%"
>>"%OUTPUT_FILE%" echo.
>>"%OUTPUT_FILE%" echo ------------------------- DETAILED DIRECTORY LISTING -------------------------
dir "%ROOT%" /S /A >>"%OUTPUT_FILE%"
>>"%OUTPUT_FILE%" echo.
>>"%OUTPUT_FILE%" echo ============================================================================
>>"%OUTPUT_FILE%" echo(

REM ================== Concatenate ALL files (any extension) ======================
for /f "delims=" %%f in ('
  dir /b /s /a:-d "%ROOT%\*" ^| sort
') do (
  REM Skip the output file itself
  if /i not "%%~f"=="%OUT_FULL%" (
    REM Build nice relative labels
    set "ABS=%%~f"
    set "REL=!ABS:%ROOT%\=!"          REM e.g. sub\pkg\file.ext
    set "DIRABS=%%~dpf"
    set "DIRREL=!DIRABS:%ROOT%\=!"     REM e.g. sub\pkg\
    set "SIZE=%%~zf"
    set "TIME=%%~tf"
    set "EXT=%%~xf"

    echo Adding !REL!...

    REM Safe header lines (use echo() so parentheses are harmless)
    >>"%OUTPUT_FILE%" echo(============================= !REL!
    >>"%OUTPUT_FILE%" echo(# File: %%~nxf (ext: !EXT!)
    >>"%OUTPUT_FILE%" echo(# Dir : !DIRREL!
    >>"%OUTPUT_FILE%" echo(# Size: !SIZE! bytes
    >>"%OUTPUT_FILE%" echo(# Time: !TIME!
    >>"%OUTPUT_FILE%" echo(============================= !REL!

    REM Append file contents (binary files will be dumped raw)
    type "%%~f">>"%OUTPUT_FILE%"

    REM Separator line after content
    >>"%OUTPUT_FILE%" echo(
    >>"%OUTPUT_FILE%" echo ------------------------------ END OF FILE ------------------------------
    >>"%OUTPUT_FILE%" echo(
  )
)

echo All files from "%ROOT%" and subfolders combined into "%OUTPUT_FILE%".
pause

------------------------------ END OF FILE ------------------------------

# Dir : 
# Size: 2329 bytes
# Time: 30/11/2025 16:51
============================= combine.bat
============================= DIRECTORY OVERVIEW =============================
Root: C:\Projects\sense-pi-local-recording-live-main\debuging codes
Timestamp: 03/12/2025  0:38:21,52

----------------------------- TREE (with files) -----------------------------
Folder PATH listing
Volume serial number is 46B7-CF63
C:\PROJECTS\SENSE-PI-LOCAL-RECORDING-LIVE-MAIN\DEBUGING CODES
    combine.bat
    combined.py
    debug_log_channels.py
    debug_pc_ingest_worker.py
    debug_pc_recorder_stream.py
    debug_pi_via_ssh.py
    
No subfolders exist 


------------------------- DETAILED DIRECTORY LISTING -------------------------
 Volume in drive C has no label.
 Volume Serial Number is 46B7-CF63

 Directory of C:\Projects\sense-pi-local-recording-live-main\debuging codes

03/12/2025  00:38    <DIR>          .
03/12/2025  00:38    <DIR>          ..
30/11/2025  16:51             2.329 combine.bat
03/12/2025  00:38               646 combined.py
30/11/2025  16:51             5.419 debug_log_channels.py
30/11/2025  16:51            11.822 debug_pc_ingest_worker.py
30/11/2025  16:51            10.294 debug_pc_recorder_stream.py
30/11/2025  16:51             4.522 debug_pi_via_ssh.py
               6 File(s)         35.032 bytes

     Total Files Listed:
               6 File(s)         35.032 bytes
               2 Dir(s)  762.580.271.104 bytes free

============================================================================

============================= combine.bat
# File: combine.bat (ext: .bat
# Dir : 
# Size: 2329 bytes
# Time: 30/11/2025 16:51
============================= combine.bat
@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ====== Configuration ======
set "OUTPUT_FILE=combined.py"

REM Use the current directory as the root (run this from your main folder)
set "ROOT=%CD%"
set "OUT_FULL=%ROOT%\%OUTPUT_FILE%"

REM Delete output file if it exists
del "%OUTPUT_FILE%" 2>nul

REM ================== Directory Details (Tree + Detailed DIR) ==================
>>"%OUTPUT_FILE%" echo ============================= DIRECTORY OVERVIEW =============================
>>"%OUTPUT_FILE%" echo Root: %ROOT%
>>"%OUTPUT_FILE%" echo Timestamp: %DATE% %TIME%
>>"%OUTPUT_FILE%" echo.
>>"%OUTPUT_FILE%" echo ----------------------------- TREE (with files) -----------------------------
tree "%ROOT%" /F >>"%OUTPUT_FILE%"
>>"%OUTPUT_FILE%" echo.
>>"%OUTPUT_FILE%" echo ------------------------- DETAILED DIRECTORY LISTING -------------------------
dir "%ROOT%" /S /A >>"%OUTPUT_FILE%"
>>"%OUTPUT_FILE%" echo.
>>"%OUTPUT_FILE%" echo ============================================================================
>>"%OUTPUT_FILE%" echo(

REM ================== Concatenate ALL files (any extension) ======================
for /f "delims=" %%f in ('
  dir /b /s /a:-d "%ROOT%\*" ^| sort
') do (
  REM Skip the output file itself
  if /i not "%%~f"=="%OUT_FULL%" (
    REM Build nice relative labels
    set "ABS=%%~f"
    set "REL=!ABS:%ROOT%\=!"          REM e.g. sub\pkg\file.ext
    set "DIRABS=%%~dpf"
    set "DIRREL=!DIRABS:%ROOT%\=!"     REM e.g. sub\pkg\
    set "SIZE=%%~zf"
    set "TIME=%%~tf"
    set "EXT=%%~xf"

    echo Adding !REL!...

    REM Safe header lines (use echo() so parentheses are harmless)
    >>"%OUTPUT_FILE%" echo(============================= !REL!
    >>"%OUTPUT_FILE%" echo(# File: %%~nxf (ext: !EXT!)
    >>"%OUTPUT_FILE%" echo(# Dir : !DIRREL!
    >>"%OUTPUT_FILE%" echo(# Size: !SIZE! bytes
    >>"%OUTPUT_FILE%" echo(# Time: !TIME!
    >>"%OUTPUT_FILE%" echo(============================= !REL!

    REM Append file contents (binary files will be dumped raw)
    type "%%~f">>"%OUTPUT_FILE%"

    REM Separator line after content
    >>"%OUTPUT_FILE%" echo(
    >>"%OUTPUT_FILE%" echo ------------------------------ END OF FILE ------------------------------
    >>"%OUTPUT_FILE%" echo(
  )
)

echo All files from "%ROOT%" and subfolders combined into "%OUTPUT_FILE%".
pause

------------------------------ END OF FILE ------------------------------

# Dir : 
# Size: 2329 bytes
# Time: 30/11/2025 16:51
============================= combine.bat
============================= DIRECTORY OVERVIEW =============================
Root: C:\Projects\sense-pi-local-recording-live-main\debuging codes
Timestamp: 03/12/2025  0:38:21,52

----------------------------- TREE (with files) -----------------------------
Folder PATH listing
Volume serial number is 46B7-CF63
C:\PROJECTS\SENSE-PI-LOCAL-RECORDING-LIVE-MAIN\DEBUGING CODES
    combine.bat
    combined.py
    debug_log_channels.py
    deb
------------------------------ END OF FILE ------------------------------

============================= debug_log_channels.py
# File: debug_log_channels.py (ext: .py
# Dir : 
# Size: 5419 bytes
# Time: 30/11/2025 16:51
============================= debug_log_channels.py
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

------------------------------ END OF FILE ------------------------------

============================= debug_pc_ingest_worker.py
# File: debug_pc_ingest_worker.py (ext: .py
# Dir : 
# Size: 11822 bytes
# Time: 30/11/2025 16:51
============================= debug_pc_ingest_worker.py
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
from collections.abc import Iterator
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, Optional

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


@dataclass
class PiStreamConfig:
    pi_device_sample_rate_hz: Optional[float] = None
    pi_stream_decimation: Optional[int] = None
    pi_stream_rate_hz: Optional[float] = None
    sensor_ids: list[int] | None = None

    @classmethod
    def from_meta_json(cls, obj: dict) -> "PiStreamConfig":
        return cls(
            pi_device_sample_rate_hz=float(obj.get("pi_device_sample_rate_hz"))
            if obj.get("pi_device_sample_rate_hz") is not None
            else None,
            pi_stream_decimation=int(obj.get("pi_stream_decimation"))
            if obj.get("pi_stream_decimation") is not None
            else None,
            pi_stream_rate_hz=float(obj.get("pi_stream_rate_hz"))
            if obj.get("pi_stream_rate_hz") is not None
            else None,
            sensor_ids=[int(s) for s in obj.get("sensor_ids", [])],
        )


def extract_pi_meta_and_wrap_stream(
    raw_stream: Iterator[str],
) -> tuple[PiStreamConfig | None, Iterator[str]]:
    """
    Consume any initial JSON meta header lines and return a cleaned
    stream iterator that yields only sample lines.
    """

    buffer: list[str] = []
    pi_cfg: PiStreamConfig | None = None

    # Try to read at most a few lines as potential meta headers
    for _ in range(3):
        try:
            line = next(raw_stream)
        except StopIteration:
            break
        if not line:
            continue
        # Try to parse JSON; ignore failures
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            buffer.append(line)
            break

        if isinstance(obj, dict) and obj.get("meta") == "mpu6050_stream_config":
            pi_cfg = PiStreamConfig.from_meta_json(obj)
            # do NOT put this line back into buffer
            continue
        else:
            buffer.append(line)
            break

    def _iter() -> Iterator[str]:
        for b in buffer:
            yield b
        for line in raw_stream:
            yield line

    return pi_cfg, _iter()


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
        pi_cfg: PiStreamConfig | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._recorder = recorder
        self._stream = stream
        self._seconds = float(seconds)
        self._pi_cfg = pi_cfg
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

        print("\n=== Ingest summary (Pi vs PC) ===")

        # Pi config
        if self._pi_cfg and (
            self._pi_cfg.pi_device_sample_rate_hz is not None
            or self._pi_cfg.pi_stream_rate_hz is not None
        ):
            print("Pi config:")
            if self._pi_cfg.pi_device_sample_rate_hz is not None:
                print(
                    "  pi_device_sample_rate_hz = "
                    f"{self._pi_cfg.pi_device_sample_rate_hz:.1f}"
                )
            if self._pi_cfg.pi_stream_decimation is not None:
                print(
                    "  pi_stream_decimation     = "
                    f"{self._pi_cfg.pi_stream_decimation}"
                )
            if self._pi_cfg.pi_stream_rate_hz is not None:
                print(
                    "  pi_stream_rate_hz        = "
                    f"{self._pi_cfg.pi_stream_rate_hz:.1f}"
                )
        else:
            print("Pi config: (unknown in this run)")

        # PC ingest
        print("\nPC ingest:")
        pc_rates: list[float] = []
        for sid in sorted(self._counts.keys()):
            count = self._counts[sid]
            line = f"  sensor_id={sid}: {count} samples"
            if elapsed and elapsed > 0:
                approx_rate = count / elapsed
                pc_rates.append(approx_rate)
                line += f" → pc_effective_rate_hz ≈ {approx_rate:.1f}"
            print(line)

        if pc_rates and self._pi_cfg and self._pi_cfg.pi_stream_rate_hz:
            avg_pc_rate = sum(pc_rates) / len(pc_rates)
            loss_pct = 100.0 * (1.0 - (avg_pc_rate / self._pi_cfg.pi_stream_rate_hz))
            print("\nComparison:")
            print(
                "  expected_pc_rate_hz (from Pi) "
                f"≈ {self._pi_cfg.pi_stream_rate_hz:.1f}"
            )
            print(f"  measured_pc_rate_hz           ≈ {avg_pc_rate:.1f}")
            print(f"  loss_vs_pi_stream             ≈ {loss_pct:.1f}%")


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

    pi_cfg, stream = extract_pi_meta_and_wrap_stream(stream)

    dbg = IngestDebug(
        recorder=rec,
        stream=stream,
        seconds=args.seconds,
        pi_cfg=pi_cfg,
    )
    QTimer.singleShot(0, dbg.start)

    app.exec()

    print("Qt event loop exited; closing recorder...")
    try:
        rec.close()
    except Exception as exc:  # pragma: no cover
        print(f"[WARN] rec.close() raised: {exc!r}")


if __name__ == "__main__":
    main()

------------------------------ END OF FILE ------------------------------

============================= debug_pc_recorder_stream.py
# File: debug_pc_recorder_stream.py (ext: .py
# Dir : 
# Size: 10294 bytes
# Time: 30/11/2025 16:51
============================= debug_pc_recorder_stream.py
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
from collections.abc import Iterator
from dataclasses import dataclass
import json
import re
from pathlib import Path
import sys
import time
from typing import Any, Dict, Optional

# --- Make src/ importable ----------------------------------------------------
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sensepi.config.app_config import HostInventory  # type: ignore
from sensepi.remote.pi_recorder import PiRecorder  # type: ignore
from sensepi.sensors.mpu6050 import MpuSample, parse_line  # type: ignore


@dataclass
class PiStreamConfig:
    pi_device_sample_rate_hz: Optional[float] = None
    pi_stream_decimation: Optional[int] = None
    pi_stream_rate_hz: Optional[float] = None
    sensor_ids: list[int] | None = None

    @classmethod
    def from_meta_json(cls, obj: dict) -> "PiStreamConfig":
        return cls(
            pi_device_sample_rate_hz=float(obj.get("pi_device_sample_rate_hz"))
            if obj.get("pi_device_sample_rate_hz") is not None
            else None,
            pi_stream_decimation=int(obj.get("pi_stream_decimation"))
            if obj.get("pi_stream_decimation") is not None
            else None,
            pi_stream_rate_hz=float(obj.get("pi_stream_rate_hz"))
            if obj.get("pi_stream_rate_hz") is not None
            else None,
            sensor_ids=[int(s) for s in obj.get("sensor_ids", [])],
        )


def extract_pi_meta_and_wrap_stream(
    raw_stream: Iterator[str],
) -> tuple[PiStreamConfig | None, Iterator[str]]:
    """
    Consume any initial JSON meta header lines and return a cleaned
    stream iterator that yields only sample lines.
    """

    buffer: list[str] = []
    pi_cfg: PiStreamConfig | None = None

    # Try to read at most a few lines as potential meta headers
    for _ in range(3):
        try:
            line = next(raw_stream)
        except StopIteration:
            break
        if not line:
            continue
        # Try to parse JSON; ignore failures
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            buffer.append(line)
            break

        if isinstance(obj, dict) and obj.get("meta") == "mpu6050_stream_config":
            pi_cfg = PiStreamConfig.from_meta_json(obj)
            # do NOT put this line back into buffer
            continue
        else:
            buffer.append(line)
            break

    def _iter() -> Iterator[str]:
        for b in buffer:
            yield b
        for line in raw_stream:
            yield line

    return pi_cfg, _iter()


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

    pi_cfg: PiStreamConfig | None = None
    pi_cfg_from_stderr = PiStreamConfig()

    PI_STREAM_RE = re.compile(
        r"pi_device_sample_rate_hz=(?P<dev>[0-9.]+)\s+"
        r"pi_stream_decimation=(?P<dec>\d+)\s+"
        r"pi_stream_rate_hz=(?P<rate>[0-9.]+)"
    )

    def on_stderr(line: str) -> None:
        print(f"[REMOTE STDERR] {line}", flush=True)

        m = PI_STREAM_RE.search(line)
        if m:
            try:
                pi_cfg_from_stderr.pi_device_sample_rate_hz = float(
                    m.group("dev")
                )
                pi_cfg_from_stderr.pi_stream_decimation = int(m.group("dec"))
                pi_cfg_from_stderr.pi_stream_rate_hz = float(m.group("rate"))
            except Exception:
                pass

    stream = None
    try:
        print("\n=== Starting PiRecorder.stream_mpu6050() ===")
        print(f"extra_args: {args.extra_args!r}")
        stream = rec.stream_mpu6050(
            extra_args=args.extra_args,
            recording=False,
            on_stderr=on_stderr,
        )

        pi_cfg, stream = extract_pi_meta_and_wrap_stream(stream)
        if pi_cfg is None and any(
            [
                pi_cfg_from_stderr.pi_device_sample_rate_hz,
                pi_cfg_from_stderr.pi_stream_decimation,
                pi_cfg_from_stderr.pi_stream_rate_hz,
            ]
        ):
            pi_cfg = pi_cfg_from_stderr

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

    print("\n=== Stream summary (Pi vs PC) ===")
    print(f"Total lines read: {total}")

    elapsed = seconds if seconds > 0 else None

    # Pi config (if known)
    if pi_cfg and (
        pi_cfg.pi_device_sample_rate_hz is not None
        or pi_cfg.pi_stream_rate_hz is not None
    ):
        print("Pi config:")
        if pi_cfg.pi_device_sample_rate_hz is not None:
            print(
                f"  pi_device_sample_rate_hz = "
                f"{pi_cfg.pi_device_sample_rate_hz:.1f}"
            )
        if pi_cfg.pi_stream_decimation is not None:
            print(f"  pi_stream_decimation     = {pi_cfg.pi_stream_decimation}")
        if pi_cfg.pi_stream_rate_hz is not None:
            print(
                f"  pi_stream_rate_hz        = {pi_cfg.pi_stream_rate_hz:.1f}"
            )
    else:
        print("Pi config: (unknown in this run)")

    # PC measurements
    print("\nPC measurements (per sensor):")
    pc_rates: list[float] = []
    for sid in sorted(counts.keys()):
        count = counts[sid]
        line = f"  sensor_id={sid}: {count} samples"
        if elapsed and elapsed > 0:
            approx_rate = count / elapsed
            pc_rates.append(approx_rate)
            line += f" over {elapsed:.1f} s → pc_effective_rate_hz ≈ {approx_rate:.1f}"
        print(line)

    # Comparison Pi vs PC
    if pc_rates and pi_cfg and pi_cfg.pi_stream_rate_hz:
        avg_pc_rate = sum(pc_rates) / len(pc_rates)
        loss_pct = 100.0 * (1.0 - (avg_pc_rate / pi_cfg.pi_stream_rate_hz))
        print("\nComparison:")
        print(
            f"  expected_pc_rate_hz (from Pi) ≈ {pi_cfg.pi_stream_rate_hz:.1f}"
        )
        print(f"  measured_pc_rate_hz           ≈ {avg_pc_rate:.1f}")
        print(f"  loss_vs_pi_stream             ≈ {loss_pct:.1f}%")


if __name__ == "__main__":
    main()

------------------------------ END OF FILE ------------------------------

============================= debug_pi_via_ssh.py
# File: debug_pi_via_ssh.py (ext: .py
# Dir : 
# Size: 4522 bytes
# Time: 30/11/2025 16:51
============================= debug_pi_via_ssh.py
from __future__ import annotations

import sys
import time
from typing import Tuple

import paramiko


# ====== EDIT THESE IF NEEDED ======
PI_HOST = "192.168.0.6"
PI_USER = "verwalter"
PI_PASSWORD = "!66442200"
PI_BASE_PATH = "~/sensor"  # same as hosts.yaml base_path
LOGGER_SCRIPT = "mpu6050_multi_logger.py"
PI_CONFIG = "pi_config.yaml"
# ==================================


def _run_remote(
    ssh: paramiko.SSHClient,
    command: str,
    *,
    print_output: bool = True,
) -> Tuple[int, str, str]:
    """Run a command on the Pi and return (exit_code, stdout, stderr)."""

    print(f"\n=== Running on Pi: {command}")
    stdin, stdout, stderr = ssh.exec_command(command)

    # Wait explicitly for command to finish
    exit_status = stdout.channel.recv_exit_status()

    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")

    if print_output:
        print("--- stdout ---")
        print(out if out.strip() else "(empty)")
        print("--- stderr ---")
        print(err if err.strip() else "(empty)")
        print(f"--- exit code: {exit_status} ---")

    return exit_status, out, err


def main() -> None:
    print("=== SensePi Pi debug via SSH ===")
    print(f"Host: {PI_HOST}, user: {PI_USER}")
    print(f"Base path on Pi: {PI_BASE_PATH}")
    print()

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print("Connecting via username + password...")
        ssh.connect(
            PI_HOST,
            username=PI_USER,
            password=PI_PASSWORD,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
        )
        print("Connected OK.\n")

        # 1) Where are we and what is in ~/sensor?
        _run_remote(ssh, "pwd")
        _run_remote(ssh, f"ls -ld {PI_BASE_PATH}")
        _run_remote(ssh, f"cd {PI_BASE_PATH} && pwd && ls -l")

        # 2) Check Python & smbus2 import
        print("\n=== Check Python & smbus2 import ===")
        smbus_check = (
            "cd {base} && "
            "python3 - << 'EOF'\n"
            "try:\n"
            "    import smbus2\n"
            "    print('OK: smbus2 import worked')\n"
            "except Exception as e:\n"
            "    print('ERROR: smbus2 import failed:', e)\n"
            "EOF"
        ).format(base=PI_BASE_PATH)
        _run_remote(ssh, smbus_check)

        # 3) Check logger & config presence
        print("\n=== Check logger & pi_config.yaml existence ===")
        _run_remote(
            ssh,
            f"cd {PI_BASE_PATH} && "
            f"ls -l {LOGGER_SCRIPT} || echo '!! {LOGGER_SCRIPT} missing'",
        )
        _run_remote(
            ssh,
            f"cd {PI_BASE_PATH} && "
            f"ls -l {PI_CONFIG} || echo '!! {PI_CONFIG} missing'",
        )

        # 4) I2C device scan via logger --list
        print("\n=== Logger I2C scan: mpu6050_multi_logger.py --list ===")
        _run_remote(
            ssh,
            f"cd {PI_BASE_PATH} && python3 {LOGGER_SCRIPT} --list",
        )

        # 5) Short streaming test (what the GUI basically does)
        print("\n=== Short streaming test (stdout captured) ===")
        stream_cmd = (
            f"cd {PI_BASE_PATH} && "
            f"python3 {LOGGER_SCRIPT} "
            f"--config {PI_CONFIG} "
            f"--stream-stdout "
            f"--no-record "
            f"--stream-every 5 "
            f"--samples 50"
        )
        rc, out, err = _run_remote(ssh, stream_cmd)

        print("\n=== Summary of streaming test ===")
        print(f"Exit code: {rc}")
        # Show just first few lines of stdout for sanity
        out_lines = [ln for ln in out.splitlines() if ln.strip()]
        print(f"Stdout lines: {len(out_lines)}")
        for ln in out_lines[:5]:
            print("OUT:", ln)
        if len(out_lines) > 5:
            print("... (more lines truncated)")

        if err.strip():
            print("\nStderr (first 20 lines):")
            err_lines = err.splitlines()
            for ln in err_lines[:20]:
                print("ERR:", ln)
            if len(err_lines) > 20:
                print("... (more lines truncated)")
        else:
            print("\nStderr: (empty)")

        print("\n=== Debug finished ===")

    except Exception as exc:
        print(f"\nFATAL: SSH debug failed: {exc!r}")
    finally:
        try:
            ssh.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

------------------------------ END OF FILE ------------------------------

