
# Prompt: Improve `mpu6050_multi_logger.py` integration for streaming control

You are editing the Raspberry Pi side of the SensePi project:

- File: `raspberrypi_scripts/mpu6050_multi_logger.py`

The goal is to ensure that the logger is **easy to drive from the GUI** with clear semantics for:

- Recording rate (`--rate`).
- Streaming decimation (`--stream-every`).
- Fields included in the stream (`--stream-fields`).

The script is already quite feature-rich; we mainly want to:

1. Confirm / document the semantics so the GUI can reason about them.
2. Optionally add a **status line** to stderr summarizing effective settings when streaming starts.

## Existing relevant section (excerpt)

```python
ap.add_argument(
    "--stream-stdout",
    action="store_true",
    help="Stream each sensor sample to stdout as JSON lines for a remote GUI."
)
ap.add_argument(
    "--stream-every",
    type=int,
    default=1,
    help="Only stream every N-th sample per sensor (default: 1 = every sample)."
)
ap.add_argument(
    "--timing-warnings",
    action="store_true",
    help="Print overrun warnings to stderr (debugging only).",
)
# ...
# Compute stream_fields: fields added on top of timestamp_ns, t_s, sensor_id.
user_fields = [
    s.strip()
    for s in (getattr(args, "stream_fields", "") or "").split(",")
    if s.strip()
]
# Valid data fields are everything in header except the time/sensor_id trio
base_fields = {"timestamp_ns", "t_s", "sensor_id"}
valid_fields = [c for c in header if c not in base_fields]

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
# ...
if args.stream_stdout and (samples_written[sid] % max(1, args.stream_every) == 0):
    out_obj = {
        "timestamp_ns": ts_ns,
        "t_s": t_s,
        "sensor_id": sid,
    }
    for key in stream_fields:
        if key in row:
            out_obj[key] = row[key]
    print(json.dumps(out_obj, separators=(",", ":")), flush=True)
```

## Goal

Make it easy for the GUI (RecorderTab) to:

1. Choose a recording rate in Hz.
2. Set `--stream-every` so that `stream_rate ≈ record_rate / stream_every`.
3. Optionally restrict `stream_fields` to only the channels the GUI displays.

We also want better **introspection from stderr** so that, when the GUI starts streaming, we log a concise summary of effective values (useful for debugging and even for the GUI to parse if desired).

## Tasks for you

1. **Add a concise startup summary to stderr**

   Right after sensors are initialized and before entering the main loop, print a single-line summary per sensor that includes:

   - Logical sensor id.
   - Effective device rate (`actual_rates[sid]`).
   - `args.stream_every`.
   - `stream_fields`.

   Example:

   ```python
   print(
       f"[INFO] streaming: sensor={sid} rate={actual_rates[sid]:.1f}Hz "
       f"stream_every={args.stream_every} stream_fields={stream_fields}",
       file=sys.stderr,
   )
   ```

   This can be printed once (not per sample) and is safe to add.

2. **Ensure semantics of `--stream-every` are clear**

   Update the `help` string for `--stream-every` to explicitly say:

   - “Effective stream rate per sensor is approximately `device_rate_hz / stream_every`.”

   Example:

   ```python
   ap.add_argument(
       "--stream-every",
       type=int,
       default=1,
       help=(
           "Only stream every N-th sample per sensor (default: 1 = every sample). "
           "Effective GUI stream rate ≈ device_rate_hz / N."
       ),
   )
   ```

3. **Guard against invalid `--stream-every`**

   - After parsing `args`, clamp `args.stream_every` to at least 1:

     ```python
     args.stream_every = max(1, int(args.stream_every))
     ```

4. **Optionally expose `stream_every` via metadata**

   - In `AsyncWriter.write_metadata(meta)`, you already write a metadata JSON file per sensor.
   - Extend `meta` to include:

     ```python
     meta["stream_every"] = int(args.stream_every)
     meta["stream_fields"] = list(stream_fields)
     ```

   - This helps offline tools understand how the stream was configured, even though streaming might have been disabled when recording-only.

5. **Document stream_fields better**

   - Update the help for `--stream-fields` to mention the subset of valid field names, e.g.:

     ```python
     ap.add_argument(
         "--stream-fields",
         type=str,
         default="ax,ay,az,gx,gy,gz",
         help=(
             "Comma-separated list of data fields to include in streamed JSON, "
             "chosen from: ax, ay, az, gx, gy, gz, temp_c. "
             "Always includes timestamp_ns, t_s, and sensor_id."
         ),
     )
     ```

6. **Make it easy for the GUI to restrict fields**

   - No further code changes are needed: the GUI already passes `--stream-fields` via RecorderTab.

## Deliverables

- A patch to `raspberrypi_scripts/mpu6050_multi_logger.py` that:
  - Adds clearer help text for `--stream-every` and `--stream-fields`.
  - Ensures `args.stream_every >= 1`.
  - Adds logging of effective streaming configuration to stderr at startup.
  - Optionally includes `stream_every` and `stream_fields` in metadata JSON.

This will let the GUI reason about streaming more confidently and help diagnose mismatches between expected and actual stream rates.
