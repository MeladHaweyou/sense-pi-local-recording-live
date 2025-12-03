#!/usr/bin/env python
import csv
import math
import statistics as stats
from pathlib import Path

# Adjust if needed
ROOT = Path(r"C:\Projects\sense-pi-local-recording-live-main")
DATA_ROOT = ROOT / "param_sweep_data\dlpf1"
OUT_CSV = ROOT / "param_noise_summary.csv"

AXES = ["ax", "ay", "az", "gx", "gy", "gz"]


def parse_run_info(path: Path):
    """
    Expect paths like:
      .../param_sweep/dlpf3/GEN_S1_default/100Hz/mpu_S1_....csv
    Returns (dlpf:int, tag:str, rate_hz:float, sensor_id:int)
    """
    rate_dir = path.parent.name           # "100Hz"
    tag = path.parent.parent.name         # "GEN_S1_default"
    dlpf_str = path.parent.parent.parent.name  # "dlpf3"

    if not dlpf_str.lower().startswith("dlpf"):
        raise ValueError(f"Unexpected path layout for {path}")

    dlpf = int(dlpf_str[4:])
    rate_hz = float(rate_dir.replace("Hz", ""))

    # Sensor id is in the CSV (sensor_id column), but also in filename: mpu_S1_...
    sensor_id = None
    stem = path.stem
    # crude parse: look for '_S<id>_'
    if "_S" in stem:
        try:
            after_s = stem.split("_S", 1)[1]
            sensor_id = int(after_s.split("_", 1)[0])
        except Exception:
            pass

    return dlpf, tag, rate_hz, sensor_id


def main():
    if not DATA_ROOT.is_dir():
        raise SystemExit(f"Data root not found: {DATA_ROOT}")

    csv_files = sorted(DATA_ROOT.rglob("mpu_S*.csv"))
    if not csv_files:
        raise SystemExit(f"No mpu_S*.csv files found under {DATA_ROOT}")

    print(f"Found {len(csv_files)} CSV files.")
    rows_out = 0

    with OUT_CSV.open("w", newline="", encoding="utf-8") as fout:
        writer = csv.writer(fout)
        writer.writerow([
            "dlpf", "tag", "rate_hz",
            "sensor_id",
            "axis", "std_dev",
            "n_samples",
            "source_file",
        ])

        for path in csv_files:
            try:
                dlpf, tag, rate_hz, sensor_id = parse_run_info(path)
            except Exception as exc:
                print(f"[WARN] Skipping {path}: {exc}")
                continue

            with path.open("r", newline="", encoding="utf-8") as fin:
                reader = csv.DictReader(fin)
                values = {axis: [] for axis in AXES}

                for row in reader:
                    for axis in AXES:
                        if axis in row and row[axis] not in ("", None):
                            try:
                                v = float(row[axis])
                                if math.isfinite(v):
                                    values[axis].append(v)
                            except Exception:
                                pass

            for axis, vals in values.items():
                if len(vals) < 2:
                    continue
                std_dev = stats.stdev(vals)
                writer.writerow([
                    dlpf, tag, rate_hz,
                    sensor_id,
                    axis, std_dev,
                    len(vals),
                    str(path),
                ])
                rows_out += 1

            print(f"[INFO] Processed {path}")

    print(f"\n[INFO] Wrote {rows_out} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
