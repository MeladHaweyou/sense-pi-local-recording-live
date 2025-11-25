#sudo chrt -f 20 taskset -c 2 python3 /home/verwalter/sensor/adxl203_ads1115_logger.py --rate 100 --channels both --map "x:P0,y:P1" --duration 10 --calibrate 300 --lp-cut 15 --out /home/verwalter/sensor/logs --addr 0x48

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ADXL203 (via ADS1115) logger — lean build (sweet-spot defaults)
================================================================

- SINGLE-SHOT conversions (honest per-read).
- Background reader fills per-axis deques.
- OSR=2 + median (best quality/perf at 100 Hz two-axis), with a tiny auto-cap so higher rates don't stall.
- Filter: 1st-order IIR; default fc=15 Hz (or auto ~0.3×Nyquist if --lp-cut 0).
- Minimal CLI; CSV output with filtered acceleration by default.
- Ctrl+C cleanly stops (SIGINT/SIGTERM).

Recommended: 100 Hz, both axes (X+Y)
  --rate 100 --channels both

Configuration via YAML
----------------------
This logger understands a small YAML config file. Use
``--config /path/to/pi_config.yaml`` explicitly, or omit ``--config``
and a ``pi_config.yaml`` located next to this script will be used if it
exists.

We read defaults from the ``adxl203_ads1115`` section and then apply
explicit command-line options on top. For boolean flags (``--no-record``,
``--stream-stdout``) the config controls the default state while the CLI
can only enable additional behaviour.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import queue
import signal
import socket
import statistics
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from pi_logger_common import load_config

# ----------------------------
# Constants & ADS parameters
# ----------------------------
G_TO_MS2 = 9.80665
ALLOWED_RATES = [8, 16, 32, 64, 128, 250, 475, 860]  # ADS1115 total SPS choices
GAIN_TO_FS = {2/3: 6.144, 1: 4.096, 2: 2.048, 4: 1.024, 8: 0.512, 16: 0.256}
OSR_TARGET = 2            # fixed best-setting at 100 Hz two-axis
ADC_SAFETY = 2.0          # headroom when picking ADS total SPS
FIXED_GAIN = 1            # ±4.096 V
DEFAULT_LP_CUT = 15.0     # Hz (set 0 to auto ~0.3×Nyquist)
FLUSH_EVERY = 2000
FLUSH_SECONDS = 5.0
LP_OUT = "filtered"       # CSV will contain filtered m/s^2 by default

# ----------------------------
# Library imports
# ----------------------------
try:
    import board
    import busio
    from adafruit_ads1x15.ads1115 import ADS1115
    from adafruit_ads1x15.analog_in import AnalogIn
    from adafruit_ads1x15.ads1x15 import Mode  # type: ignore
except Exception:
    print(
        "ERROR: adafruit-circuitpython-ads1x15 & adafruit-blinka are required.\n"
        "Install:\n  python3 -m pip install --upgrade adafruit-circuitpython-ads1x15 adafruit-blinka",
        file=sys.stderr,
    )
    raise

# ----------------------------
# Global stop flag for Ctrl+C
# ----------------------------
STOP_EVENT = threading.Event()
def _stop_handler(signum, frame):
    STOP_EVENT.set()
signal.signal(signal.SIGINT, _stop_handler)
signal.signal(signal.SIGTERM, _stop_handler)

# ----------------------------
# Helpers
# ----------------------------
def _resolve_pin_enum() -> Dict[str, object]:
    try:
        import adafruit_ads1x15.ads1x15 as ads_base  # type: ignore
        pins = {}
        for n in ("P0", "P1", "P2", "P3"):
            if hasattr(ads_base, n):
                pins[n] = getattr(ads_base, n)
        if len(pins) == 4:
            return pins
    except Exception:
        pass
    try:
        from adafruit_ads1x15.ads1x15 import ADS as _ADS  # type: ignore
        return {"P0": _ADS.P0, "P1": _ADS.P1, "P2": _ADS.P2, "P3": _ADS.P3}
    except Exception:
        pass
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

PIN_ENUM = _resolve_pin_enum()

def parse_map(map_str: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not map_str:
        return out
    for part in map_str.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            k, v = part.split(":")
            k = k.strip().lower()
            v = v.strip().upper()
            if k in ("x", "y") and v in ("P0", "P1", "P2", "P3"):
                out[k] = v
        except Exception:
            continue
    return out

def monotonic_controller(rate_hz: float):
    period = int(1e9 / rate_hz)
    next_t = time.monotonic_ns()
    while True:
        next_t += period
        yield next_t

def choose_ads_rate_total(requested_hz: float, n_channels: int, target_osr: int) -> int:
    target = max(1.0, requested_hz) * max(1, n_channels) * max(1, target_osr) * ADC_SAFETY
    for r in ALLOWED_RATES:
        if r >= target:
            return r
    return ALLOWED_RATES[-1]

def open_i2c_try_400k() -> busio.I2C:
    try:
        return busio.I2C(board.SCL, board.SDA, frequency=400000)  # kernel may ignore; set /boot config
    except TypeError:
        return busio.I2C(board.SCL, board.SDA)
    except Exception:
        return busio.I2C(board.SCL, board.SDA)

# ----------------------------
# Async writer (CSV/JSONL)
# ----------------------------
class AsyncWriter:
    def __init__(self, filepath: Path, fmt: str, header: List[str],
                 flush_every: int = FLUSH_EVERY, flush_seconds: float = FLUSH_SECONDS,
                 do_fsync: bool = False):
        self.filepath = filepath
        self.meta_path = filepath.with_suffix(filepath.suffix + ".meta.json")
        self.fmt = fmt
        self.header = header
        self.flush_every = flush_every
        self.flush_seconds = flush_seconds
        self.do_fsync = do_fsync
        self._q: "queue.Queue[Optional[dict]]" = queue.Queue()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._fh = None
        self._writer = None
        self._lines_since_flush = 0
        self._last_flush = time.monotonic()

    def start(self):
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.filepath, "w", newline="")
        if self.fmt == "csv":
            self._writer = csv.DictWriter(self._fh, fieldnames=self.header)
            self._writer.writeheader()
        self._t.start()

    def write(self, row: dict):
        self._q.put(row)

    def _maybe_flush(self):
        self._fh.flush()
        if self.do_fsync:
            os.fsync(self._fh.fileno())

    def _run(self):
        while True:
            item = self._q.get()
            if item is None:
                break
            if self.fmt == "csv":
                self._writer.writerow(item)
            else:
                self._fh.write(json.dumps(item, separators=(",", ":")) + "\n")
            self._lines_since_flush += 1
            now = time.monotonic()
            if self._lines_since_flush >= self.flush_every or (now - self._last_flush) >= self.flush_seconds:
                self._maybe_flush()
                self._lines_since_flush = 0
                self._last_flush = now
        self._maybe_flush()
        self._fh.close()

    def stop(self):
        self._q.put(None)
        self._t.join()

    def write_metadata(self, meta: dict):
        with open(self.meta_path, "w") as mfh:
            json.dump(meta, mfh, indent=2)

# ----------------------------
# Background reader (SINGLE-SHOT)
# ----------------------------
class ReaderThread(threading.Thread):
    def __init__(self, chans: Dict[str, AnalogIn], maxlen: int = 4096):
        super().__init__(daemon=True)
        self.chans = chans
        self.buffers: Dict[str, deque] = {ax: deque(maxlen=maxlen) for ax in chans}
        self.stop_event = threading.Event()

    def run(self):
        axes = list(self.chans.keys())
        while not self.stop_event.is_set():
            for ax in axes:
                try:
                    v = self.chans[ax].voltage  # single-shot conversion
                    ts = time.monotonic_ns()
                    self.buffers[ax].append((ts, v))
                except Exception:
                    pass

    def stop(self):
        self.stop_event.set()

# ----------------------------
# Unique collector (half-LSB gate)
# ----------------------------
def collect_unique_since(buf: deque, cutoff_ns: int, max_n: int, eps_volts: float) -> List[float]:
    fresh: List[float] = []
    last_v = None
    for (t_ns, v) in reversed(buf):
        if t_ns <= cutoff_ns:
            break
        if last_v is None or (math.isfinite(v) and math.isfinite(last_v) and abs(v - last_v) >= 0.49 * eps_volts):
            fresh.append(v)
            last_v = v
            if len(fresh) >= max(1, max_n):
                break
    if fresh:
        return fresh
    return [buf[-1][1]] if buf else [float("nan")]

# ----------------------------
# Zero-g calibration
# ----------------------------
def calibrate_zero_g(chans: Dict[str, AnalogIn], n: int, sleep_s: float) -> Dict[str, float]:
    acc: Dict[str, float] = {ax: 0.0 for ax in chans}
    for _ in range(max(1, n)):
        if STOP_EVENT.is_set():
            break
        for ax, ch in chans.items():
            try:
                acc[ax] += ch.voltage
            except Exception:
                pass
        time.sleep(max(1e-4, sleep_s))
    return {ax: (acc[ax] / max(1, n)) for ax in chans}

# ----------------------------
# Warm-up unique-rate estimate (for OSR auto-cap)
# ----------------------------
def estimate_unique_rate(chans: Dict[str, AnalogIn], eps_volts: float, duration_s: float = 0.25) -> Dict[str, float]:
    counts: Dict[str, int] = {ax: 0 for ax in chans}
    last: Dict[str, Optional[float]] = {ax: None for ax in chans}
    end = time.monotonic() + max(0.05, duration_s)
    axes = list(chans.keys())
    while time.monotonic() < end and not STOP_EVENT.is_set():
        for ax in axes:
            try:
                v = chans[ax].voltage
                lv = last[ax]
                if (lv is None) or (math.isfinite(v) and math.isfinite(lv) and abs(v - lv) >= 0.49 * eps_volts):
                    counts[ax] += 1
                    last[ax] = v
            except Exception:
                pass
    span = max(1e-6, duration_s)
    return {ax: counts[ax] / span for ax in axes}

# ----------------------------
# IIR low-pass filter
# ----------------------------
class FirstOrderIIR:
    def __init__(self, fs_hz: float, fc_hz: float):
        dt = 1.0 / max(1.0, fs_hz)
        if fc_hz <= 0:
            self.alpha = 1.0
        else:
            rc = 1.0 / (2.0 * math.pi * fc_hz)
            self.alpha = dt / (rc + dt)
        self.y: Optional[float] = None

    def step(self, x: float) -> float:
        if self.y is None:
            self.y = x
            return x
        self.y = self.y + self.alpha * (x - self.y)
        return self.y

# ----------------------------
# Main
# ----------------------------
def main():
    ap = argparse.ArgumentParser(description="ADXL203 via ADS1115 logger (lean, SINGLE-SHOT, OSR=2 median).")
    ap.add_argument(
        "--rate",
        type=float,
        required=False,
        help="Output sampling rate in Hz (per axis)",
    )
    ap.add_argument("--channels", type=str, choices=["x", "y", "both"], default="both", help="Axes to record")
    ap.add_argument("--duration", type=float, default=None, help="Duration in seconds; omit for indefinite")
    ap.add_argument("--out", type=str, default="./logs", help="Output directory")
    ap.add_argument("--addr", type=lambda x: int(x, 0), default=0x48, help="ADS1115 I²C address (e.g., 0x48)")
    ap.add_argument("--map", type=str, default="x:P0,y:P1", help="Channel map like 'x:P0,y:P1'")
    ap.add_argument("--calibrate", type=int, default=300, help="N samples at rest to compute zero-g per axis (0=skip)")
    ap.add_argument("--lp-cut", type=float, default=DEFAULT_LP_CUT, help="LPF cutoff Hz (0→auto ~0.3×Nyq)")
    ap.add_argument(
        "--no-record",
        action="store_true",
        help="Disable file output (no CSV/meta). Sampling still runs, and streaming can be used.",
    )
    ap.add_argument(
        "--stream-stdout",
        action="store_true",
        help="Stream samples to stdout as JSON lines for a remote GUI.",
    )
    ap.add_argument(
        "--stream-every",
        type=int,
        default=1,
        help="Only stream every Nth output sample (default: 1 = every sample).",
    )
    # For streaming, `timestamp_ns` (int, monotonic nanoseconds) is always
    # included. By default we also stream:
    #   x_lp, y_lp : low-pass filtered acceleration components in m/s^2 for
    #                the X and Y axes respectively.
    ap.add_argument(
        "--stream-fields",
        type=str,
        default="x_lp,y_lp",
        help=(
            "Comma-separated list of data fields (from the CSV header) to "
            "include in the stdout JSON stream, in addition to timestamp_ns."
        ),
    )
    ap.add_argument(
        "--config",
        type=str,
        default=None,
        help=(
            "Path to YAML config file with defaults "
            "(falls back to 'pi_config.yaml' next to this script if omitted)."
        ),
    )
    args = ap.parse_args()

    # ------------------------------------------------------------------
    # YAML configuration merge
    # ------------------------------------------------------------------
    script_dir = Path(__file__).resolve().parent
    default_cfg_path = script_dir / "pi_config.yaml"

    if args.config:
        cfg_path = Path(args.config)
    elif default_cfg_path.exists():
        cfg_path = default_cfg_path
    else:
        cfg_path = None

    cfg = {}
    section = {}
    if cfg_path is not None:
        try:
            cfg = load_config(cfg_path)
            section = cfg.get("adxl203_ads1115", {}) or {}
        except Exception as exc:
            print(f"[WARN] Failed to load config {cfg_path}: {exc}", file=sys.stderr)
            section = {}

    argv = sys.argv[1:]

    def _flag_present(name: str) -> bool:
        prefix = name + "="
        return any(a == name or a.startswith(prefix) for a in argv)

    # sample rate (Hz)
    cfg_rate = section.get("sample_rate_hz")
    if args.rate is None and cfg_rate is not None:
        try:
            args.rate = float(cfg_rate)
        except Exception:
            print(f"[WARN] Invalid adxl203_ads1115.sample_rate_hz in config: {cfg_rate!r}", file=sys.stderr)

    # channels: x|y|both
    cfg_channels = section.get("channels")
    if not _flag_present("--channels") and cfg_channels is not None:
        args.channels = str(cfg_channels)

    # calibration_samples -> --calibrate
    cfg_cal = section.get("calibration_samples")
    if not _flag_present("--calibrate") and cfg_cal is not None:
        try:
            args.calibrate = int(cfg_cal)
        except Exception:
            print(f"[WARN] Invalid adxl203_ads1115.calibration_samples in config: {cfg_cal!r}", file=sys.stderr)

    # output_dir -> --out
    cfg_out = section.get("output_dir") or section.get("out")
    if cfg_out is not None and not _flag_present("--out"):
        args.out = str(cfg_out)

    # Optional defaults for flags and streaming
    if section.get("no_record") and not args.no_record:
        args.no_record = True
    if section.get("stream_stdout") and not args.stream_stdout:
        args.stream_stdout = True

    cfg_stream_every = section.get("stream_every")
    if cfg_stream_every is not None and not _flag_present("--stream-every"):
        try:
            args.stream_every = int(cfg_stream_every)
        except Exception:
            print(f"[WARN] Invalid adxl203_ads1115.stream_every in config: {cfg_stream_every!r}", file=sys.stderr)

    cfg_stream_fields = section.get("stream_fields")
    if cfg_stream_fields and not _flag_present("--stream-fields"):
        args.stream_fields = str(cfg_stream_fields)

    cfg_duration = section.get("duration_s")
    if cfg_duration is not None and args.duration is None and not _flag_present("--duration"):
        try:
            args.duration = float(cfg_duration)
        except Exception:
            print(f"[WARN] Invalid adxl203_ads1115.duration_s in config: {cfg_duration!r}", file=sys.stderr)

    # After merging, ensure a valid rate
    if args.rate is None or args.rate <= 0:
        print(
            "ERROR: --rate must be > 0 (set via CLI --rate or "
            "adxl203_ads1115.sample_rate_hz in pi_config.yaml).",
            file=sys.stderr,
        )
        return 2

    # Channels & mapping
    ch_map = parse_map(args.map)
    if not ch_map:
        ch_map = {"x": "P0", "y": "P1"}
    enabled_axes: List[str] = []
    if args.channels in ("x", "both"):
        enabled_axes.append("x")
    if args.channels in ("y", "both"):
        enabled_axes.append("y")
    if not enabled_axes:
        print("ERROR: no axes enabled", file=sys.stderr); return 2
    n_ch = len(enabled_axes)

    # I²C + ADS
    try:
        i2c = open_i2c_try_400k()
        ads = ADS1115(i2c, address=args.addr)
    except Exception as e:
        print(f"ERROR: ADS1115 init failed @ 0x{args.addr:02X}: {e}", file=sys.stderr); return 2

    # Fixed gain & SINGLE-SHOT
    try:
        ads.gain = FIXED_GAIN
        ads.mode = Mode.SINGLE
    except Exception:
        pass
    fs_v = GAIN_TO_FS.get(FIXED_GAIN, 4.096)
    lsb_volts = fs_v / 32768.0

    # Build channels
    try:
        pin = PIN_ENUM
        chans: Dict[str, AnalogIn] = {}
        if "x" in enabled_axes:
            chans["x"] = AnalogIn(ads, pin[ch_map["x"]])
        if "y" in enabled_axes:
            chans["y"] = AnalogIn(ads, pin.get(ch_map.get("y", "P1"), 1))
    except Exception as e:
        print(f"ERROR: Failed to create ADS1115 channels with map {ch_map}: {e}", file=sys.stderr)
        return 2

    # Calibration
    zero_g_offsets: Dict[str, float] = {ax: 2.5 for ax in enabled_axes}
    if args.calibrate and args.calibrate > 0:
        print(f"[INFO] Calibrating zero-g over {args.calibrate} samples... keep the sensor still")
        zero_g_offsets = calibrate_zero_g(chans, args.calibrate, sleep_s=1.0/100.0)
        print(f"[INFO] Zero-g offsets (V): {zero_g_offsets}")

    # LPF cutoff
    lp_cut = args.lp_cut if args.lp_cut > 0 else max(2.0, 0.3 * (0.5 * args.rate))

    # OSR (fixed 2) with tiny auto-cap via warm-up unique rate
    osr_req = OSR_TARGET
    uniq = estimate_unique_rate(chans, eps_volts=lsb_volts, duration_s=0.25)
    min_unique_hz = min(uniq.get(ax, 0.0) for ax in enabled_axes) if uniq else 0.0
    feedable = int((min_unique_hz / args.rate) * 0.9)  # 10% margin
    osr_eff = max(1, min(osr_req, feedable)) if feedable > 0 else 1

    # ADS data rate with headroom
    ads_total = choose_ads_rate_total(args.rate, n_ch, osr_eff)
    try:
        ads.data_rate = ads_total
    except Exception:
        pass

    print(f"[INFO] ADS1115 @ 0x{args.addr:02X}, mode=SINGLE, data_rate={ads_total} SPS, gain={FIXED_GAIN} (±{fs_v:.3f} V)")
    print(f"[INFO] Channels: {enabled_axes} mapped as {ch_map}; rate={args.rate:.1f} Hz; OSR={osr_eff} (median); LPF={lp_cut:.1f} Hz")

    # Output setup
    out_dir = Path(args.out).expanduser().resolve()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(
            f"[WARN] Unable to create output directory {out_dir}: {exc}",
            file=sys.stderr,
        )
        return 1
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    fpath = out_dir / f"adxl203_{timestamp}.csv"
    header: List[str] = ["timestamp_ns"] + [f"{ax}_lp" for ax in enabled_axes]  # filtered only (LP_OUT)

    # Determine which fields to stream; always include timestamp_ns
    user_fields = [
        s.strip()
        for s in (getattr(args, "stream_fields", "") or "").split(",")
        if s.strip()
    ]
    valid_fields = [f"{ax}_lp" for ax in enabled_axes]
    if not user_fields:
        stream_fields = valid_fields
    else:
        stream_fields = [f for f in user_fields if f in valid_fields]
        if not stream_fields:
            print(
                "[WARN] --stream-fields did not match any known columns; "
                f"falling back to default {valid_fields}",
                file=sys.stderr,
            )
            stream_fields = valid_fields

    if args.no_record and not args.stream_stdout:
        print(
            "[WARN] --no-record specified without --stream-stdout; "
            "sensor will run but no data will be saved or streamed.",
            file=sys.stderr,
        )

    writer: Optional[AsyncWriter] = None
    if not args.no_record:
        try:
            writer = AsyncWriter(fpath, "csv", header)
            writer.start()
            print(f"[INFO] Recording enabled → {fpath}")
        except Exception as exc:
            print(
                f"[WARN] Failed to initialize output at {out_dir}: {exc}",
                file=sys.stderr,
            )
            return 1
    else:
        print(
            "[INFO] no-record mode (CSV/meta output disabled); streaming only.",
            file=sys.stderr,
        )

    # Filters
    lp_filters: Dict[str, Optional[FirstOrderIIR]] = {ax: FirstOrderIIR(args.rate, lp_cut) for ax in enabled_axes}

    # Reader
    reader = ReaderThread(chans, maxlen=8192)
    reader.start()

    # Pacing
    controller = monotonic_controller(args.rate)
    target_next = next(controller)
    start_ns = time.monotonic_ns()
    deadline_ns = start_ns + int(args.duration * 1e9) if (args.duration and args.duration > 0) else None
    last_frame_cutoff: Dict[str, int] = {ax: start_ns for ax in enabled_axes}

    # Aggregator: median
    def robust_median(xs: List[float]) -> float:
        if not xs:
            return float("nan")
        if len(xs) == 1:
            return xs[0]
        return statistics.median(xs)

    sample_idx = 0

    try:
        while not STOP_EVENT.is_set():
            now_ns = time.monotonic_ns()
            sleep_ns = target_next - now_ns
            if sleep_ns > 0:
                time.sleep(sleep_ns / 1e9)

            ts_ns = time.monotonic_ns()
            row: Dict[str, float] = {"timestamp_ns": ts_ns}

            for ax in enabled_axes:
                buf = reader.buffers[ax]
                fresh_v = collect_unique_since(buf, last_frame_cutoff[ax], osr_eff, lsb_volts)
                v_agg = robust_median(fresh_v)
                if math.isfinite(v_agg):
                    g_val = (v_agg - zero_g_offsets[ax]) / 1.0  # sens 1.0 V/g
                    a_ms2 = g_val * G_TO_MS2
                else:
                    a_ms2 = float("nan")
                row[f"{ax}_lp"] = lp_filters[ax].step(a_ms2) if lp_filters[ax] else a_ms2
                last_frame_cutoff[ax] = ts_ns

            # 1) Optional file output
            if writer is not None:
                writer.write(row)

            # 2) Optional stdout streaming (decimated)
            if args.stream_stdout and (sample_idx % max(1, args.stream_every) == 0):
                out_obj = {"timestamp_ns": ts_ns}
                for key in stream_fields:
                    if key in row:
                        out_obj[key] = row[key]
                print(json.dumps(out_obj, separators=(",", ":")), flush=True)

            sample_idx += 1

            if deadline_ns is not None and ts_ns >= deadline_ns:
                break
            target_next = next(controller)
    except KeyboardInterrupt:
        # Also stop cleanly on Ctrl+C if default handler triggers KeyboardInterrupt
        pass
    finally:
        reader.stop()
        reader.join(timeout=1.0)
        if writer is not None:
            writer.stop()

    # Metadata
    meta = {
        "start_utc": datetime.utcnow().isoformat() + "Z",
        "hostname": socket.gethostname(),
        "requested_rate_hz": args.rate,
        "duration_s": args.duration,
        "channels": enabled_axes,
        "map": ch_map,
        "addr_hex": f"0x{args.addr:02X}",
        "ads_mode": "SINGLE",
        "ads_total_sps": ads_total,
        "gain": FIXED_GAIN,
        "gain_full_scale_V": fs_v,
        "lsb_volts": lsb_volts,
        "zero_g_V": {k: float(v) for k, v in (zero_g_offsets or {}).items()},
        "sens_V_per_g": 1.0,
        "osr_requested": OSR_TARGET,
        "osr_effective": osr_eff,
        "osr_agg": "median",
        "lp_cut_hz": lp_cut,
        "format": "csv",
        "header": header,
        "version": 8,
        "output_file": str(fpath),
    }
    if not args.no_record:
        AsyncWriter(fpath, "csv", header).write_metadata(meta)

    print("\n=== Run complete ===")
    print(f"File     : {fpath}")
    print(f"Metadata : {fpath}.meta.json")
    return 0

if __name__ == "__main__":
    sys.exit(main())
