#!/usr/bin/env python3
r"""
Generate figures from param_sweep_data and param_sweep_logs.

- Assumes this script is placed in the project root:
    C:\Projects\sense-pi-local-recording-live-main

- Uses noise summary CSVs (long format: dlpf, tag, rate_hz, sensor_id, axis, std_dev):
    param_sweep_data\dlpf 1 param_noise_summary.csv
    param_sweep_data\dlpf 1_with_shaking param_noise_summary.csv
    param_sweep_data\dlpf 3 param_noise_summary.csv

- Uses logs:
    param_sweep_logs\dlpf1
    param_sweep_logs\dlpf1_with_shaking
    param_sweep_logs\dlpf3

IMPORTANT: "3 channels" here means the 3 acceleration axes ax, ay, az.
"""

from pathlib import Path
import re
import sys
from typing import Dict, List

import pandas as pd
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Paths / basic config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "param_sweep_data"
LOGS_DIR = BASE_DIR / "param_sweep_logs"
FIG_DIR = BASE_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Noise CSV files
NOISE_CONFIGS = [
    dict(
        dlpf=1,
        condition="still",
        path=DATA_DIR / "dlpf 1 param_noise_summary.csv",
    ),
    dict(
        dlpf=1,
        condition="shaking",
        path=DATA_DIR / "dlpf 1_with_shaking param_noise_summary.csv",
    ),
    dict(
        dlpf=3,
        condition="still",
        path=DATA_DIR / "dlpf 3 param_noise_summary.csv",
    ),
]

# Log folders
LOG_CONFIGS = [
    dict(dlpf=1, condition="still", subdir="dlpf1"),
    dict(dlpf=1, condition="shaking", subdir="dlpf1_with_shaking"),
    dict(dlpf=3, condition="still", subdir="dlpf3"),
]

# Duration used in the parametric sweep scripts
DURATION_S = 15.0

# Tag names we’ll use for plotting
TAG_ACC_3CH = "SPEC_S1_1ch_acc"      # 1 sensor, 3 accel axes ax/ay/az
TAG_3CH_DEFAULT = "SPEC_S1_3ch_default"  # 1 sensor, 3 plotted channels (contains ax/ay/gz)
TAG_3SENS_6CH = "SPEC_S123_6ch_both"     # 3 sensors × 6 ch


# ---------------------------------------------------------------------------
# Noise data loading (long format: dlpf, tag, rate_hz, sensor_id, axis, std_dev)
# ---------------------------------------------------------------------------

def load_noise_data() -> pd.DataFrame:
    """
    Load and combine the three param_noise_summary CSV files.

    Returns a DataFrame with at least:
        ['dlpf', 'tag', 'rate_hz', 'sensor_id', 'axis', 'std_dev',
         'n_samples', 'source_file', 'condition']
    """
    frames: List[pd.DataFrame] = []
    for cfg in NOISE_CONFIGS:
        path = cfg["path"]
        if not path.exists():
            print(f"[load_noise_data] WARNING: noise file not found: {path}")
            continue
        df = pd.read_csv(path)
        # Ensure expected columns exist
        required = {"dlpf", "tag", "rate_hz", "sensor_id", "axis",
                    "std_dev", "n_samples", "source_file"}
        missing = required - set(df.columns)
        if missing:
            raise RuntimeError(
                f"Noise file {path} missing columns: {missing}. "
                "Adjust load_noise_data() to match your schema."
            )
        df["condition"] = cfg["condition"]
        frames.append(df)

    if not frames:
        raise RuntimeError("No noise summary data could be loaded. "
                           "Check NOISE_CONFIGS paths.")

    noise_df = pd.concat(frames, ignore_index=True)

    # Type-cleaning
    noise_df["rate_hz"] = noise_df["rate_hz"].astype(float)
    noise_df["sensor_id"] = noise_df["sensor_id"].astype(int)

    return noise_df


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

def parse_single_log(path: Path, dlpf: int, condition: str) -> Dict:
    """
    Parse one .log file and extract:
        mode          (GEN / SPEC)
        sensor_block  (S1, S123, etc.)
        profile       (default, 1ch_acc, 3ch_default, 6ch_both, ...)
        target_rate_hz (from filename)
        device_rate_hz (from [INFO] line)
        n_sensors
        samples_total
        errors_total
        overruns
    """
    name = path.name
    stem = path.stem  # e.g. SPEC_S1_3ch_default_100Hz

    parts = stem.split("_")
    if len(parts) < 3:
        raise ValueError(f"Unexpected log filename format: {name}")

    mode = parts[0]          # 'GEN' or 'SPEC'
    sensor_block = parts[1]  # 'S1', 'S123', etc.
    rate_part = parts[-1]    # '100Hz'
    profile = "_".join(parts[2:-1]) or "default"

    m_rate = re.match(r"(\d+)Hz", rate_part)
    if not m_rate:
        raise ValueError(f"Cannot parse rate from filename: {name}")
    target_rate_hz = int(m_rate.group(1))

    text = path.read_text(encoding="utf-8", errors="ignore")

    # device_rate from [INFO] Sensor ... device_rate≈xxx Hz
    m_dev = re.search(r"device_rate[^\d]*([\d\.]+)\s*Hz", text)
    device_rate_hz = float(m_dev.group(1)) if m_dev else float("nan")

    # Overruns: 0
    m_over = re.search(r"Overruns:\s+(\d+)", text)
    overruns = int(m_over.group(1)) if m_over else 0

    # Sensor lines: Sensor 1: samples=1500, errors=0
    sensor_matches = re.findall(
        r"Sensor\s+(\d+):\s+samples=(\d+),\s+errors=(\d+)",
        text,
    )

    n_sensors = len(sensor_matches)
    samples_total = sum(int(s) for _, s, _ in sensor_matches) if sensor_matches else 0
    errors_total = sum(int(e) for _, _, e in sensor_matches) if sensor_matches else 0

    return dict(
        file=str(path),
        dlpf=dlpf,
        condition=condition,
        mode=mode,
        sensor_block=sensor_block,
        profile=profile,
        target_rate_hz=target_rate_hz,
        device_rate_hz=device_rate_hz,
        n_sensors=n_sensors,
        samples_total=samples_total,
        errors_total=errors_total,
        overruns=overruns,
    )


def load_log_data() -> pd.DataFrame:
    """
    Walk param_sweep_logs subfolders and parse every .log file.
    """
    records: List[Dict] = []
    for cfg in LOG_CONFIGS:
        dlpf = cfg["dlpf"]
        condition = cfg["condition"]
        subdir = LOGS_DIR / cfg["subdir"]

        if not subdir.exists():
            print(f"[load_log_data] WARNING: log subdir not found: {subdir}")
            continue

        for path in sorted(subdir.glob("*.log")):
            try:
                rec = parse_single_log(path, dlpf=dlpf, condition=condition)
                records.append(rec)
            except Exception as e:
                print(f"[load_log_data] ERROR parsing {path}: {e}", file=sys.stderr)

    if not records:
        raise RuntimeError("No log data parsed – check LOG_CONFIGS and directory layout.")

    df = pd.DataFrame.from_records(records)

    # Derived quantities
    # Effective per-sensor rate (samples per sensor per second)
    df["n_sensors"] = df["n_sensors"].replace(0, 1)
    df["samples_per_sensor"] = df["samples_total"] / df["n_sensors"]
    df["effective_rate_hz"] = df["samples_per_sensor"] / DURATION_S

    df["overrun_fraction"] = df["overruns"] / (df["overruns"] + df["samples_per_sensor"])
    df["overrun_percent"] = 100.0 * df["overrun_fraction"]

    return df


# ---------------------------------------------------------------------------
# Plotting: noise vs rate for 3 accel channels (ax, ay, az)
# ---------------------------------------------------------------------------

def plot_noise_acc_3ch_vs_rate(noise_df: pd.DataFrame) -> None:
    """
    Plot noise (std_dev) vs rate for ax, ay, az, for each (dlpf, condition),
    using the tag TAG_ACC_3CH (SPEC_S1_1ch_acc) and sensor_id=1.
    """
    axes_acc = ["ax", "ay", "az"]

    for dlpf in sorted(noise_df["dlpf"].dropna().unique()):
        for condition in sorted(noise_df["condition"].dropna().unique()):
            df = noise_df[
                (noise_df["dlpf"] == dlpf)
                & (noise_df["condition"] == condition)
                & (noise_df["tag"] == TAG_ACC_3CH)
                & (noise_df["sensor_id"] == 1)
                & (noise_df["axis"].isin(axes_acc))
            ].copy()
            if df.empty:
                continue

            pivot = df.pivot_table(
                index="rate_hz",
                columns="axis",
                values="std_dev",
                aggfunc="mean",
            ).sort_index()

            fig, ax = plt.subplots(figsize=(6, 4))
            for axis_name, marker in zip(axes_acc, ["o", "s", "^"]):
                if axis_name in pivot.columns:
                    ax.plot(pivot.index, pivot[axis_name],
                            marker=marker, linestyle="-",
                            label=f"{axis_name}")

            ax.set_xlabel("Sample rate [Hz]")
            ax.set_ylabel("Std dev (accel) [units]")
            ax.set_title(f"Noise vs rate – {TAG_ACC_3CH}, S1, DLPF={dlpf}, {condition}")
            ax.grid(True, which="both", linestyle="--", alpha=0.3)
            ax.legend()
            fig.tight_layout()

            out_name = f"noise_{TAG_ACC_3CH}_S1_dlpf{dlpf}_{condition}_3acc.png"
            out_path = FIG_DIR / out_name
            fig.savefig(out_path, dpi=300)
            plt.close(fig)
            print(f"[plot_noise_acc_3ch_vs_rate] Saved {out_path}")


# ---------------------------------------------------------------------------
# Plotting: overruns & effective rate for SPEC_S1_3ch_default (3 accel channels)
# ---------------------------------------------------------------------------

def select_3ch_profile(log_df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter logs for SPEC_S1_3ch_default (1 sensor, 3 channels profile).
    """
    df = log_df[
        (log_df["mode"] == "SPEC")
        & (log_df["sensor_block"] == "S1")
        & (log_df["profile"] == "3ch_default")
    ].copy()
    return df


def plot_overruns_vs_rate_3ch(log_df: pd.DataFrame) -> None:
    """
    Overruns vs rate for SPEC_S1_3ch_default, for each condition and dlpf.
    """
    df = select_3ch_profile(log_df)
    if df.empty:
        print("[plot_overruns_vs_rate_3ch] No SPEC_S1_3ch_default logs found.")
        return

    for condition in sorted(df["condition"].dropna().unique()):
        df_c = df[df["condition"] == condition].copy()
        if df_c.empty:
            continue

        fig, ax = plt.subplots(figsize=(6, 4))
        for dlpf in sorted(df_c["dlpf"].dropna().unique()):
            df_plot = df_c[df_c["dlpf"] == dlpf].sort_values("target_rate_hz")
            ax.plot(df_plot["target_rate_hz"], df_plot["overrun_percent"],
                    marker="o", linestyle="-", label=f"DLPF {dlpf}")

        ax.set_xlabel("Target rate [Hz]")
        ax.set_ylabel("Overrun [%]")
        ax.set_title(f"Overruns vs rate – SPEC_S1_3ch_default – {condition}")
        ax.grid(True, which="both", linestyle="--", alpha=0.3)
        ax.legend()
        fig.tight_layout()

        out_path = FIG_DIR / f"overruns_SPEC_S1_3ch_default_{condition}.png"
        fig.savefig(out_path, dpi=300)
        plt.close(fig)
        print(f"[plot_overruns_vs_rate_3ch] Saved {out_path}")


def plot_effective_vs_target_3ch(log_df: pd.DataFrame) -> None:
    """
    Effective (realized) sample rate vs target, for SPEC_S1_3ch_default.
    """
    df = select_3ch_profile(log_df)
    if df.empty:
        print("[plot_effective_vs_target_3ch] No SPEC_S1_3ch_default logs found.")
        return

    for condition in sorted(df["condition"].dropna().unique()):
        df_c = df[df["condition"] == condition].copy()
        if df_c.empty:
            continue

        fig, ax = plt.subplots(figsize=(6, 4))
        for dlpf in sorted(df_c["dlpf"].dropna().unique()):
            df_plot = df_c[df_c["dlpf"] == dlpf].sort_values("target_rate_hz")
            ax.plot(df_plot["target_rate_hz"], df_plot["effective_rate_hz"],
                    marker="o", linestyle="-", label=f"DLPF {dlpf}")

        # y = x reference
        all_rates = df_c["target_rate_hz"].unique()
        if len(all_rates) > 0:
            r_min, r_max = min(all_rates), max(all_rates)
            ax.plot([r_min, r_max], [r_min, r_max],
                    linestyle="--", color="grey", alpha=0.4,
                    label="ideal y=x")

        ax.set_xlabel("Target rate [Hz]")
        ax.set_ylabel("Effective rate [Hz]")
        ax.set_title(f"Effective vs target – SPEC_S1_3ch_default – {condition}")
        ax.grid(True, which="both", linestyle="--", alpha=0.3)
        ax.legend()
        fig.tight_layout()

        out_path = FIG_DIR / f"effective_vs_target_SPEC_S1_3ch_default_{condition}.png"
        fig.savefig(out_path, dpi=300)
        plt.close(fig)
        print(f"[plot_effective_vs_target_3ch] Saved {out_path}")


# ---------------------------------------------------------------------------
# Plotting: static vs shaking (noise bars, SNR-style)
# ---------------------------------------------------------------------------

def plot_static_vs_shaking(noise_df: pd.DataFrame) -> None:
    """
    Bar chart of std_dev for static vs shaking at one operating point.

    Uses:
        dlpf = 1
        tag  = TAG_ACC_3CH (SPEC_S1_1ch_acc)
        rate = 100 Hz
        sensor_id = 1
        axes = ax, ay, az
    """
    dlpf = 1
    rate = 100.0
    tag = TAG_ACC_3CH
    sensor_id = 1
    axes_acc = ["ax", "ay", "az"]

    rows_static = noise_df[
        (noise_df["dlpf"] == dlpf)
        & (noise_df["condition"] == "still")
        & (noise_df["tag"] == tag)
        & (noise_df["rate_hz"] == rate)
        & (noise_df["sensor_id"] == sensor_id)
        & (noise_df["axis"].isin(axes_acc))
    ]
    rows_shaking = noise_df[
        (noise_df["dlpf"] == dlpf)
        & (noise_df["condition"] == "shaking")
        & (noise_df["tag"] == tag)
        & (noise_df["rate_hz"] == rate)
        & (noise_df["sensor_id"] == sensor_id)
        & (noise_df["axis"].isin(axes_acc))
    ]

    if rows_static.empty or rows_shaking.empty:
        print("[plot_static_vs_shaking] Missing data for static or shaking.")
        return

    # Build aligned arrays
    axes_present = []
    static_vals = []
    shaking_vals = []

    for axis_name in axes_acc:
        s_row = rows_static[rows_static["axis"] == axis_name]
        q_row = rows_shaking[rows_shaking["axis"] == axis_name]
        if s_row.empty or q_row.empty:
            continue
        axes_present.append(axis_name)
        static_vals.append(float(s_row["std_dev"].iloc[0]))
        shaking_vals.append(float(q_row["std_dev"].iloc[0]))

    if not axes_present:
        print("[plot_static_vs_shaking] No common accel axes found.")
        return

    import numpy as np

    x = np.arange(len(axes_present))
    width = 0.35

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(x - width / 2, static_vals, width, label="Still")
    ax.bar(x + width / 2, shaking_vals, width, label="Shaking")

    ax.set_xticks(x)
    ax.set_xticklabels(axes_present)
    ax.set_ylabel("Std dev [units]")
    ax.set_title(f"Static vs shaking – {tag}, dlpf={dlpf}, rate={rate} Hz, S{sensor_id}")
    ax.grid(True, axis="y", linestyle="--", alpha=0.3)
    ax.legend()
    fig.tight_layout()

    out_path = FIG_DIR / f"static_vs_shaking_{tag}_dlpf{dlpf}_{int(rate)}Hz_S{sensor_id}.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"[plot_static_vs_shaking] Saved {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Base directory: ", BASE_DIR)
    print("Data directory: ", DATA_DIR)
    print("Logs directory: ", LOGS_DIR)
    print("Figures will be saved under:", FIG_DIR)
    print()

    # Load noise data (long format)
    print("Loading noise summary CSVs (long format with 'axis' column)...")
    noise_df = load_noise_data()
    print(f"Noise rows loaded: {len(noise_df)}")
    print("Noise columns:", list(noise_df.columns))
    print()

    # Load log data
    print("Loading and parsing log files...")
    log_df = load_log_data()
    print(f"Log runs parsed: {len(log_df)}")
    print("Log columns:", list(log_df.columns))
    print()

    # Figures from noise
    print("Creating noise vs rate plots for 3 acceleration channels...")
    plot_noise_acc_3ch_vs_rate(noise_df)

    print("Creating static vs shaking bar plot at one operating point...")
    plot_static_vs_shaking(noise_df)

    # Figures from logs
    print("Creating overruns vs rate plots for SPEC_S1_3ch_default...")
    plot_overruns_vs_rate_3ch(log_df)

    print("Creating effective vs target rate plots for SPEC_S1_3ch_default...")
    plot_effective_vs_target_3ch(log_df)

    print()
    print("All figures written to:", FIG_DIR)


if __name__ == "__main__":
    main()
