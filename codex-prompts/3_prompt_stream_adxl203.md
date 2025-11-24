# Final Prompt 1 – Patch `adxl203_ads1115_logger.py` with `--no-record` + stdout streaming

This version is compatible with the current ADXL logger implementation.

You are editing an existing Raspberry Pi sensor logger: `adxl203_ads1115_logger.py`.
It currently logs ADXL203 (via ADS1115) to CSV using `AsyncWriter` and prints an INFO summary at the end.

Goal: add OPTIONAL features (no-record + stdout JSON streaming) without breaking any existing behavior.

File to modify:
- `adxl203_ads1115_logger.py`

Key constraints:
- If the new flags are NOT supplied, behavior must be 100% identical to now.
- Streaming and recording must be independent:
  - default (no new flags) → record to CSV only (current behavior)
  - `--stream-stdout` → record as usual AND emit decimated JSON lines to stdout
  - `--no-record` → no CSV/meta files, no stream unless `--stream-stdout` is also set
  - `--no-record --stream-stdout` → stream-only, no file I/O on SD card

The script already imports `json`, `sys`, `AsyncWriter`, etc., and uses `from __future__ import annotations`, so type hints like `Optional[AsyncWriter]` are OK.

---

## 1) Extend argparse

In `main()`, find the existing argument definitions:

```python
ap.add_argument("--rate", ...)
ap.add_argument("--channels", ...)
ap.add_argument("--duration", ...)
ap.add_argument("--out", ...)
ap.add_argument("--addr", ...)
ap.add_argument("--map", ...)
ap.add_argument("--calibrate", ...)
ap.add_argument("--lp-cut", ...)
```

Immediately after `--lp-cut`, add:

```python
ap.add_argument(
    "--no-record",
    action="store_true",
    help="Disable file output (no CSV/meta). Sampling still runs, and streaming can be used."
)
ap.add_argument(
    "--stream-stdout",
    action="store_true",
    help="Stream samples to stdout as JSON lines for a remote GUI."
)
ap.add_argument(
    "--stream-every",
    type=int,
    default=1,
    help="Only stream every Nth output sample (default: 1 = every sample)."
)
ap.add_argument(
    "--stream-fields",
    type=str,
    default="x_lp,y_lp",
    help="Comma-separated list of field names (from the header) to include in the stdout JSON stream."
)
```

After `args = ap.parse_args()`, compute the list of stream fields (before the main loop, after you know `enabled_axes` / `header`):

```python
# Determine which fields to stream; always include timestamp_ns
user_fields = [
    s.strip()
    for s in (getattr(args, "stream_fields", "") or "").split(",")
    if s.strip()
]
# Valid numeric columns are the *_lp entries that we write to CSV
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
```

---

## 2) Make writing optional with `--no-record`

Locate the output setup section:

```python
out_dir = Path(args.out).expanduser().resolve()
out_dir.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
fpath = out_dir / f"adxl203_{timestamp}.csv"
header: List[str] = ["timestamp_ns"] + [f"{ax}_lp" for ax in enabled_axes]
writer = AsyncWriter(fpath, "csv", header)
writer.start()
```

Change it to:

```python
out_dir = Path(args.out).expanduser().resolve()
out_dir.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
fpath = out_dir / f"adxl203_{timestamp}.csv"
header: List[str] = ["timestamp_ns"] + [f"{ax}_lp" for ax in enabled_axes]

writer: Optional[AsyncWriter] = None
if not args.no_record:
    writer = AsyncWriter(fpath, "csv", header)
    writer.start()
    print(f"[INFO] Recording enabled → {fpath}")
else:
    print(
        "[INFO] no-record mode: CSV/meta output disabled; only streaming/log messages will be produced.",
        file=sys.stderr,
    )
```

---

## 3) Add streaming + guard writes in main loop

Just before the main `try:` loop, add a sample counter:

```python
sample_idx = 0
```

Inside the sampling loop (inside `try`), you currently do something like:

```python
row: Dict[str, float] = {"timestamp_ns": ts_ns}
...
writer.write(row)
```

Replace the `writer.write(row)` part with:

```python
# 1) Optional file output
if writer is not None:
    writer.write(row)

# 2) Optional stdout streaming (decimated)
if args.stream_stdout and (sample_idx % max(1, args.stream_every) == 0):
    out_obj = {"timestamp_ns": ts_ns}
    for key in stream_fields:
        if key in row:
            out_obj[key] = row[key]
    # Emit as JSON line, compact format
    print(json.dumps(out_obj, separators=(",", ":")), flush=True)

sample_idx += 1
```

Make sure there is no other stray `writer.write(row)` left; all writing should go through this guarded block.

---

## 4) Safe shutdown when writer may be `None`

In the `finally:` block there is currently:

```python
finally:
    reader.stop()
    reader.join(timeout=1.0)
    writer.stop()
```

Change it to:

```python
finally:
    reader.stop()
    reader.join(timeout=1.0)
    if writer is not None:
        writer.stop()
```

---

## 5) Only write metadata when recording

At the very end, metadata is written unconditionally:

```python
AsyncWriter(fpath, "csv", header).write_metadata(meta)
```

Change to:

```python
if not args.no_record:
    AsyncWriter(fpath, "csv", header).write_metadata(meta)
```

Everything else (sampling, calibration, filtering, INFO prints) should remain unchanged.  
Default behavior (no new flags) must be byte‑for‑byte equivalent in the main output CSV.
