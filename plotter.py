#!/usr/bin/env python3
# Plot the newest ADXL203/ADS1115 CSV from a fixed Windows directory
# Directory: G:\Projects\sense-pi-local-recording\logs
#
# - Finds the most recent *.csv in that folder
# - Builds a time axis from timestamp_ns (seconds from start)
# - Applies per-axis baseline correction (configurable)
# - Plots each axis (baseline-corrected) in its own figure
# - Saves PNGs into a "plots" subfolder next to the CSVs
# - Also shows the plots interactively

from pathlib import Path
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def compute_baseline(y: np.ndarray, t: np.ndarray, mode: str, first_seconds: float) -> float:
    """Return a single baseline value for subtraction."""
    y = np.asarray(y, dtype=float)
    t = np.asarray(t, dtype=float)

    if mode == "none":
        return 0.0

    if mode == "median":
        return float(np.nanmedian(y))

    if mode == "mean":
        return float(np.nanmean(y))

    if mode == "first-seconds":
        if first_seconds <= 0:
            return float(np.nanmedian(y))
        mask = t <= first_seconds
        if not np.any(mask):
            # Fallback if timestamps are weird or too short
            return float(np.nanmedian(y))
        return float(np.nanmedian(y[mask]))

    raise ValueError(f"Unknown baseline mode: {mode}")

def main():
    ap = argparse.ArgumentParser(description="Plot newest ADXL203 CSV with baseline correction.")
    ap.add_argument("--baseline", choices=["median", "mean", "first-seconds", "none"],
                    default="median",
                    help="Baseline method to subtract per axis (default: median).")
    ap.add_argument("--baseline-seconds", type=float, default=2.0,
                    help="Duration (s) for 'first-seconds' baseline (default: 2.0).")
    # You usually won't need to change this path; adjust if your folder differs:
    ap.add_argument("--dir", type=str, default=r"G:\Projects\sense-pi-local-recording\logs-ADXL",
                    help="Directory containing CSV logs (default: the fixed Windows path).")
    args = ap.parse_args()

    base_dir = Path(args.dir)

    if not base_dir.exists():
        raise SystemExit(f"Directory not found: {base_dir}")

    csv_files = sorted(base_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not csv_files:
        raise SystemExit(f"No CSV files found in {base_dir}")

    csv_path = csv_files[0]  # newest CSV
    print(f"Using CSV: {csv_path}")

    # Load data
    df = pd.read_csv(csv_path)
    if "timestamp_ns" not in df.columns:
        raise SystemExit(f"Missing 'timestamp_ns' in {csv_path}. Columns: {list(df.columns)}")

    # Time axis in seconds (relative to first sample)
    t = (df["timestamp_ns"] - df["timestamp_ns"].iloc[0]) / 1e9
    t = t.to_numpy()

    # Prefer filtered columns that end with '_lp'; fall back to any non-timestamp columns
    axis_cols = [c for c in df.columns if c.endswith("_lp")]
    if not axis_cols:
        axis_cols = [c for c in df.columns if c != "timestamp_ns"]
    if not axis_cols:
        raise SystemExit("No axis columns found (expected something like x_lp, y_lp).")

    # Basic sampling stats
    dt_ms = np.diff(df["timestamp_ns"].to_numpy()) / 1e6  # ms
    if dt_ms.size:
        mean_dt = float(np.nanmean(dt_ms))
        std_dt = float(np.nanstd(dt_ms))
        min_dt = float(np.nanmin(dt_ms))
        max_dt = float(np.nanmax(dt_ms))
        approx_rate = 1000.0 / mean_dt if mean_dt > 0 else float("nan")
        print(
            f"Rows={len(df)}  Axes={axis_cols}  "
            f"Δt mean={mean_dt:.3f} ms, std={std_dt:.3f} ms "
            f"(min={min_dt:.3f}, max={max_dt:.3f})  →  ~{approx_rate:.2f} Hz"
        )
    else:
        print(f"Rows={len(df)}  Axes={axis_cols}")

    # Output directory
    outdir = base_dir / "plots"
    outdir.mkdir(parents=True, exist_ok=True)

    # Plot each axis (apply baseline correction)
    for col in axis_cols:
        y = df[col].to_numpy(dtype=float)
        b = compute_baseline(y, t, mode=args.baseline, first_seconds=args.baseline_seconds)
        y_bc = y - b

        print(f"[{col}] baseline ({args.baseline}) = {b:.6g}  → subtracting to center around ~0")

        plt.figure()
        plt.plot(t, y_bc)
        plt.xlabel("Time [s]")
        plt.ylabel("Acceleration [m/s²] (baseline-corrected)")
        plt.title(f"{col} vs Time (baseline: {args.baseline}, {csv_path.name})")
        plt.grid(True)

        out_path = outdir / f"{csv_path.stem}_{col}_bc.png"
        plt.savefig(out_path, dpi=144, bbox_inches="tight")
        print(f"Saved: {out_path}")

    plt.show()

if __name__ == "__main__":
    main()
