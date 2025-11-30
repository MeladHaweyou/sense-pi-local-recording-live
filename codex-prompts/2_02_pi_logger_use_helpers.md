# SensePi Implementation Prompt 2 – Use Helpers in `mpu6050_multi_logger.py`

In this prompt you will **wire the new log path & naming helpers** (from Prompt 1)
into the Raspberry Pi logger script:

- `raspberrypi_scripts/mpu6050_multi_logger.py`

The goal is to replace duplicated, ad-hoc path-building logic with calls to the
shared helpers, without changing the CLI or the overall behaviour from a user’s
point of view.

---

## Goal

Update `mpu6050_multi_logger.py` so that it:

1. Uses `build_pi_session_dir` to compute the output directory for a recording.
2. Uses `build_log_file_paths` to construct the data and `.meta.json` paths.
3. Ensures the **session name is slugified exactly once** and reused consistently.
4. Keeps default behaviour identical to the previous implementation.

---

## Context: current (simplified) code

In `mpu6050_multi_logger.py` there is code like this (the exact names may differ;
adjust to your actual file):

```python
from pathlib import Path
import datetime as dt

# ... load config into cfg, parse args into args ...

base_out_dir = Path(cfg["output_dir"]).expanduser()
session_name = args.session_name  # may be None / empty string

# Build output directory for this recording
if session_name:
    session_slug = slugify(session_name)  # sometimes done inline
    out_dir = base_out_dir / "mpu" / session_slug
else:
    out_dir = base_out_dir / "mpu"

out_dir.mkdir(parents=True, exist_ok=True)

start_dt = dt.datetime.utcnow()
ts_str = start_dt.strftime("%Y-%m-%d_%H-%M-%S")
ext = "csv" if args.format == "csv" else "jsonl"

# Per-sensor file construction (inside a loop over sensors)
sensor_id = 1  # example
filename = f"mpu_S{sensor_id}_{ts_str}.{ext}"
data_path = out_dir / filename
meta_path = data_path.with_suffix(data_path.suffix + ".meta.json")
```

This logic is what we want to centralize.

---

## Target integration: use `log_paths` helpers

Replace the above pieces with imports and calls into the helper module
introduced in Prompt 1.

At the top of `mpu6050_multi_logger.py`, add:

```python
# raspberrypi_scripts/mpu6050_multi_logger.py
from pathlib import Path
import datetime as dt

from sensepi.config.log_paths import (
    LOG_SUBDIR_MPU,
    build_pi_session_dir,
    build_log_file_paths,
)
```

Then in the main setup code, compute the output directory like this:

```python
# Existing config load and arg parsing...
base_out_dir = Path(cfg["output_dir"]).expanduser()
session_name = args.session_name or None  # normalize empty string to None

# Use the shared helper to build the Pi-side session directory
out_dir = build_pi_session_dir(
    sensor_prefix=LOG_SUBDIR_MPU,
    session_name=session_name,
    base_dir=base_out_dir,
)
out_dir.mkdir(parents=True, exist_ok=True)

start_dt = dt.datetime.utcnow()
ext = "csv" if args.format == "csv" else "jsonl"
```

Now, wherever you currently construct `data_path` and `meta_path` for each
sensor, replace that code with:

```python
# Inside the per-sensor setup loop
paths = build_log_file_paths(
    sensor_prefix=LOG_SUBDIR_MPU,
    session_name=session_name,
    sensor_id=sensor_id,
    start_dt=start_dt,
    format_ext=ext,
    out_dir=out_dir,
)

data_path = paths.data_path
meta_path = paths.meta_path
```

Make sure that:

- `sensor_id` is the 1-based index you want reflected as `S1`, `S2`, etc.
- `start_dt` is the same for all sensors in one run (so filenames share the
  same timestamp, matching the previous behaviour).
- `format_ext` is `"csv"` or `"jsonl"` (no leading dot).

---

## Session name handling

- If you were previously performing any manual “slugify” logic inside this
  file, you can now remove it and rely on the helper function in
  `log_paths.slugify_session_name`.
- Continue to accept `--session-name` (or equivalent) on the CLI – the
  helpers should not change the CLI surface.
- Ensure that the `.meta.json` file still uses the same base filename as the
  data file, with an extra `.meta.json` suffix.

---

## Testing & validation

1. Run the logger directly on the Pi with and without a session name, e.g.:
   - `python3 mpu6050_multi_logger.py --session-name Test1`
   - `python3 mpu6050_multi_logger.py`

2. Confirm that:
   - Files are created in the same directories as before relative to
     `cfg["output_dir"]` (e.g. `~/logs/mpu` and `~/logs/mpu/test1`).
   - Filenames follow the `[session_]mpu_S<id>_<timestamp>.<ext>` scheme.
   - `.meta.json` sidecars are still present and correctly named.

3. Make sure any unit tests or smoke tests referring to file paths still pass.

Once this is working, the Pi side is ready for the PC sync logic refactor
in Prompt 3.
