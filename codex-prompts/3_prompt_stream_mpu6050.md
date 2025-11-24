# Final Prompt 2 – Patch `mpu6050_multi_logger.py` with `--no-record` + stdout streaming

This version matches your current multi‑sensor logger implementation.

You are editing `mpu6050_multi_logger.py`, which logs up to three MPU6050 sensors to CSV/JSONL using `AsyncWriter` per sensor.

Goal: add OPTIONAL `--no-record` and stdout streaming, consistent with the ADXL logger, while preserving current behavior when new flags are not used.

File to modify:
- `mpu6050_multi_logger.py`

High-level requirements:
- Default behavior unchanged if new flags are not present.
- Add:
  - `--no-record` → disable file writers and metadata (no CSV/JSONL/meta on SD card).
  - `--stream-stdout` → emit JSON lines to stdout that a remote GUI can use for live plotting.
  - `--stream-every N` → only stream every N-th sample per sensor.
  - `--stream-fields` → select which numeric fields to include in streamed JSON.
- Each streamed JSON object MUST include at least:
  - `timestamp_ns`
  - `t_s`
  - `sensor_id`
  plus any selected fields like `ax`, `ay`, `az`, `gx`, `gy`, `gz`, `temp_c` depending on `--channels` and `--temp`.

Note: The script already imports `json`, `queue`, etc., and defines `header`, `samples_written`, etc., so you can reuse those.

---

## 1) Extend argument parser

In `main()`, locate the argparse block with options like `--rate`, `--sensors`, `--out`, `--format`, `--temp`, and flushing controls:

```python
ap.add_argument("--flush-every", ...)
ap.add_argument("--flush-seconds", ...)
ap.add_argument("--fsync-each-flush", ...)
```

Immediately after these, add:

```python
ap.add_argument(
    "--no-record",
    action="store_true",
    help="Disable file output (no CSV/JSONL or metadata files)."
)
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
    "--stream-fields",
    type=str,
    default="ax,ay,gz",
    help=("Comma-separated extra fields (e.g. 'ax,ay,gz,temp_c') to include in streamed JSON "
          "in addition to timestamp_ns,t_s,sensor_id.")
)
```

After `args = ap.parse_args()` and after you’ve built `header` and `ch_mode`, compute the stream field list:

```python
# Compute stream_fields: fields added on top of timestamp_ns, t_s, sensor_id
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

if args.no_record and not args.stream_stdout:
    print(
        "[WARN] --no-record specified without --stream-stdout; "
        "run will produce no output files and no streaming data.",
        file=sys.stderr,
    )
```

---

## 2) Make per-sensor writers optional

Later in `main()`, there is a section that prepares the output directory and writers:

```python
out_dir = Path(args.out).expanduser().resolve()
writers: Dict[int, AsyncWriter] = {}
...
for sid in enabled:
    ...
    # Prepare writer
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    suffix = f"S{sid}"
    ext = "csv" if args.format == "csv" else "jsonl"
    fpath = out_dir / f"{args.prefix}_{suffix}_{timestamp}.{ext}"
    writer = AsyncWriter(
        fpath, args.format, header,
        flush_every=args.flush_every,
        flush_seconds=args.flush_seconds,
        fsync_each_flush=args.fsync_each_flush
    )
    writer.start()
    # metadata per sensor file
    gyro_bw, acc_bw = DLPF_BW.get(args.dlpf, (None, None))
    meta = { ... }
    writer.write_metadata(meta)
    writers[sid] = writer
    ...
```

Change this so that writers and metadata are only created if **not** `args.no_record`:

```python
out_dir = Path(args.out).expanduser().resolve()
writers: Dict[int, AsyncWriter] = {}

...

for sid in enabled:
    bus_id = mapping[sid].bus
    addr = mapping[sid].addr
    try:
        if bus_id not in bus_handles:
            bus_handles[bus_id] = SMBus(bus_id)
        dev = MPU6050(bus_handles[bus_id], addr)
        who = dev.who_am_i()
        if who not in (0x68, 0x69):
            print(f"[WARN] Sensor {sid} WHO_AM_I=0x{who:02X} (expected 0x68/0x69). Continuing.", file=sys.stderr)
        div, actual = dev.initialize(dlpf_cfg=args.dlpf, fs_accel=0, fs_gyro=0, rate_hz=req_rate)
        devices[sid] = dev
        who_values[sid] = who
        smplrt_divs[sid] = div
        actual_rates[sid] = actual

        # Prepare writer only if recording is enabled
        if not args.no_record:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            suffix = f"S{sid}"
            ext = "csv" if args.format == "csv" else "jsonl"
            fpath = out_dir / f"{args.prefix}_{suffix}_{timestamp}.{ext}"
            writer = AsyncWriter(
                fpath, args.format, header,
                flush_every=args.flush_every,
                flush_seconds=args.flush_seconds,
                fsync_each_flush=args.fsync_each_flush
            )
            writer.start()
            gyro_bw, acc_bw = DLPF_BW.get(args.dlpf, (None, None))
            meta = {
                "start_utc": start_iso,
                "hostname": hostname,
                "sensor_id": sid,
                "bus": bus_id,
                "address_hex": f"0x{addr:02X}",
                "who_am_i_hex": f"0x{who:02X}",
                "requested_rate_hz": float(args.rate),
                "clamped_rate_hz": req_rate,
                "dlpf_cfg": args.dlpf,
                "dlpf_gyro_bw_hz": gyro_bw,
                "dlpf_accel_bw_hz": acc_bw,
                "fs_accel": "±2g",
                "fs_gyro": "±250dps",
                "smplrt_div": div,
                "device_rate_hz": round(actual, 6),
                "channels": ch_mode,
                "format": args.format,
                "header": header,
                "start_monotonic_ns": start_mono_ns,
                "version": 3
            }
            writer.write_metadata(meta)
            writers[sid] = writer
            bw_str = f"DLPF={args.dlpf} (gyro≈{gyro_bw}Hz, accel≈{acc_bw}Hz)" if gyro_bw else f"DLPF={args.dlpf}"
            print(f"[INFO] Sensor {sid}: bus={bus_id} addr=0x{addr:02X} WHO=0x{who:02X} "
                  f"div={div} device_rate≈{actual:.3f} Hz {bw_str}")
        else:
            print(
                f"[INFO] Sensor {sid}: no-record mode, file output disabled; using in-memory streaming only.",
                file=sys.stderr,
            )
```

---

## 3) Use writers only if they exist, and add streaming

In the sampling loop, locate:

```python
for sid, dev in list(devices.items()):
    try:
        ts_ns = time.monotonic_ns()
        t_s = (ts_ns - start_mono_ns) / 1e9
        row = {"timestamp_ns": ts_ns, "t_s": t_s, "sensor_id": sid}
        ...
        writers[sid].write(row)
        samples_written[sid] += 1
    except Exception as e:
        ...
```

Before the `try:` loop, you already have:

```python
samples_written: Dict[int, int] = {sid: 0 for sid in enabled}
```

You do NOT need another counter; we can use `samples_written[sid]` for decimation.

Change the body of the inner loop to:

```python
for sid, dev in list(devices.items()):
    try:
        ts_ns = time.monotonic_ns()
        t_s = (ts_ns - start_mono_ns) / 1e9
        row = {"timestamp_ns": ts_ns, "t_s": t_s, "sensor_id": sid}

        # existing channel handling (acc/gyro/both/default)
        if ch_mode == "acc":
            ax, ay, az = dev.read_accel()
            row.update({
                "ax": (ax / ACC_SF) * G_TO_MS2,
                "ay": (ay / ACC_SF) * G_TO_MS2,
                "az": (az / ACC_SF) * G_TO_MS2,
            })
        elif ch_mode == "gyro":
            gx, gy, gz = dev.read_gyro()
            row.update({
                "gx": gx / GYR_SF,
                "gy": gy / GYR_SF,
                "gz": gz / GYR_SF,
            })
        elif ch_mode == "both":
            ax, ay, az = dev.read_accel()
            gx, gy, gz = dev.read_gyro()
            row.update({
                "ax": (ax / ACC_SF) * G_TO_MS2,
                "ay": (ay / ACC_SF) * G_TO_MS2,
                "az": (az / ACC_SF) * G_TO_MS2,
                "gx": gx / GYR_SF,
                "gy": gy / GYR_SF,
                "gz": gz / GYR_SF,
            })
        elif ch_mode == "default":
            ax, ay, _ = dev.read_accel()
            _, _, gz = dev.read_gyro()
            row.update({
                "ax": (ax / ACC_SF) * G_TO_MS2,
                "ay": (ay / ACC_SF) * G_TO_MS2,
                "gz": gz / GYR_SF,
            })

        if args.temp:
            try:
                row["temp_c"] = dev.read_temp_c()
            except Exception:
                row["temp_c"] = float("nan")

        # 1) Optional file output
        w = writers.get(sid)
        if w is not None:
            w.write(row)

        # 2) Update per-sensor sample counter
        samples_written[sid] += 1

        # 3) Optional stdout streaming (decimated per sensor)
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

    except Exception as e:
        errors[sid] += 1
        if errors[sid] <= 10 or (errors[sid] % 100) == 0:
            print(f"[WARN] Read error on sensor {sid}: {e} (count={errors[sid]})", file=sys.stderr)
        continue
```

---

## 4) Safe shutdown of writers

In the `finally:` block, writers are currently stopped unconditionally:

```python
for sid, w in writers.items():
    w.stop()
```

This remains valid, because with `--no-record`, `writers` is simply empty.  
No change needed unless you start storing placeholders.

With these changes, the script supports:

- Normal recording (no new flags) → unchanged.
- Recording + streaming (`--stream-stdout --stream-every 5`) → files + JSON lines.
- Streaming only (`--no-record --stream-stdout ...`) → JSON lines only, no files.
- `--no-record` alone → a warning and no logging/streaming.
