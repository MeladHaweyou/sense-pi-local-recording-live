#!/usr/bin/env python3
"""
Generate figures for the Sense-Pi parameter sweep.

This script expects to live in the project root, alongside:
  - param_sweep_data/
  - param_sweep_logs/
and will write PNG files into figures/.
"""

from pathlib import Path
import re
from typing import Dict, List

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# -----------------------------------------------------------------------------
# Paths / constants
# -----------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "param_sweep_data"
LOG_DIR = BASE_DIR / "param_sweep_logs"
FIG_DIR = BASE_DIR / "figures"

FIG_DIR.mkdir(parents=True, exist_ok=True)

ACC_AXES = ["ax", "ay", "az"]
GYRO_AXES = ["gx", "gy", "gz"]
ALL_AXES = ACC_AXES + GYRO_AXES

# Which CSVs to load for noise
NOISE_CONFIGS = [
    # still
    dict(path=DATA_DIR / "dlpf 1 param_noise_summary.csv", dlpf=1, condition="still"),
    dict(path=DATA_DIR / "dlpf 3 param_noise_summary.csv", dlpf=3, condition="still"),
    # with shaking (only used for possible extensions)
    dict(
        path=DATA_DIR / "dlpf 1_with_shaking param_noise_summary.csv",
        dlpf=1,
        condition="shaking",
    ),
]

# Which log folders to load, and how to label them
LOG_CONFIGS = [
    dict(path=LOG_DIR / "dlpf1", dlpf=1, condition="still"),
    dict(path=LOG_DIR / "dlpf3", dlpf=3, condition="still"),
    dict(path=LOG_DIR / "dlpf1_with_shaking", dlpf=1, condition="shaking"),
]

# Channel / sensor configurations we care about
CHANNEL_CONFIGS = [
    dict(
        key="S1_3ch",
        label="1 sensor, 3 ch (accel)",
        mode="SPEC",
        sensor_block="S1",
        profile="3ch_default",
        tag="SPEC_S1_3ch_default",
        axes_type="accel3",
    ),
    dict(
        key="S1_6ch",
        label="1 sensor, 6 ch (acc+gyro)",
        mode="SPEC",
        sensor_block="S1",
        profile="6ch_both",
        tag="SPEC_S1_6ch_both",
        axes_type="accel_gyro6",
    ),
    dict(
        key="S123_6ch",
        label="3 sensors, 6 ch (acc+gyro)",
        mode="SPEC",
        sensor_block="S123",
        profile="6ch_both",
        tag="SPEC_S123_6ch_both",
        axes_type="accel_gyro6",
    ),
]


# -----------------------------------------------------------------------------
# Noise CSV loading
# -----------------------------------------------------------------------------

def load_noise_data() -> pd.DataFrame:
    """Load all param_noise_summary.csv files and add dlpf / condition columns."""
    frames = []
    for cfg in NOISE_CONFIGS:
        path = cfg["path"]
        if not path.exists():
            print(f"[WARN] Noise CSV not found, skipping: {path}")
            continue
        df = pd.read_csv(path)
        # Expect columns: dlpf, tag, rate_hz, sensor_id, axis, std_dev, n_samples, source_file
        expected_cols = {
            "dlpf",
            "tag",
            "rate_hz",
            "sensor_id",
            "axis",
            "std_dev",
            "n_samples",
        }
        missing = expected_cols - set(df.columns)
        if missing:
            raise ValueError(
                f"Noise CSV {path} missing columns: {missing}. "
                f"Available columns: {df.columns.tolist()}"
            )
        # In case dlpf column isn't present or is wrong, overwrite with our config
        df["dlpf"] = cfg["dlpf"]
        df["condition"] = cfg["condition"]
        frames.append(df)

    if not frames:
        raise RuntimeError("No noise CSVs could be loaded; check paths in NOISE_CONFIGS.")
    noise_df = pd.concat(frames, ignore_index=True)
    return noise_df


# -----------------------------------------------------------------------------
# Log parsing
# -----------------------------------------------------------------------------

LOG_LINE_INFO_RE = re.compile(
    r"device_rate.*?([\d.]+)\s*Hz.*?DLPF=(\d+)", re.IGNORECASE
)
LOG_LINE_SAMPLES_RE = re.compile(r"Sensor\s+(\d+):\s+samples=(\d+)", re.IGNORECASE)
LOG_LINE_OVERRUNS_RE = re.compile(r"Overruns:\s+(\d+)", re.IGNORECASE)


def parse_single_log(path: Path) -> Dict:
    """
    Parse a single .log file into a record.

    Filename convention assumed:
      MODE_SENSORBLOCK_PROFILE_RATEHz.log

    Examples:
        GEN_S1_default_100Hz.log
        SPEC_S1_3ch_default_300Hz.log
        SPEC_S123_6ch_both_50Hz.log
    """
    stem = path.stem  # e.g. SPEC_S1_3ch_default_100Hz
    parts = stem.split("_")
    if len(parts) < 3:
        raise ValueError(f"Unexpected log filename format: {path.name}")

    mode = parts[0]  # GEN or SPEC
    sensor_block = parts[1]  # S1 or S123
    profile = "_".join(parts[2:-1])  # e.g. default, 3ch_default, 6ch_both
    rate_part = parts[-1]  # e.g. 100Hz

    m_rate = re.match(r"(\d+)Hz", rate_part, re.IGNORECASE)
    if not m_rate:
        raise ValueError(f"Could not parse rate from log filename: {path.name}")
    target_rate_hz = float(m_rate.group(1))

    info_rate = None
    info_dlpf = None
    sensor_samples = {}  # sensor_id -> samples
    overruns = None

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "device_rate" in line and "DLPF" in line:
                m = LOG_LINE_INFO_RE.search(line)
                if m:
                    info_rate = float(m.group(1))
                    info_dlpf = int(m.group(2))
            elif "samples=" in line and "Sensor" in line:
                m = LOG_LINE_SAMPLES_RE.search(line)
                if m:
                    sensor_id = int(m.group(1))
                    samples = int(m.group(2))
                    sensor_samples[sensor_id] = samples
            elif "Overruns:" in line:
                m = LOG_LINE_OVERRUNS_RE.search(line)
                if m:
                    overruns = int(m.group(1))

    if not sensor_samples:
        raise ValueError(f"No sensor sample lines found in log: {path}")
    if overruns is None:
        overruns = 0

    # assume all sensors have same number of samples
    avg_samples = np.mean(list(sensor_samples.values()))

    return dict(
        mode=mode,
        sensor_block=sensor_block,
        profile=profile,
        target_rate_hz=target_rate_hz,
        info_rate_hz=info_rate,
        samples_per_sensor=avg_samples,
        overruns=overruns,
        path=str(path),
    )


def load_log_data() -> pd.DataFrame:
    """Load all logs from LOG_CONFIGS, parse them, and attach dlpf/condition."""
    rows = []
    for cfg in LOG_CONFIGS:
        base = cfg["path"]
        if not base.exists():
            print(f"[WARN] Log directory not found, skipping: {base}")
            continue
        for path in sorted(base.glob("*.log")):
            rec = parse_single_log(path)
            rec["dlpf"] = cfg["dlpf"]
            rec["condition"] = cfg["condition"]
            rows.append(rec)

    if not rows:
        raise RuntimeError("No logs found; check LOG_CONFIGS and directory structure.")

    df = pd.DataFrame(rows)
    # derive effective rate from samples over a 15 second test
    DURATION_S = 15.0
    df["effective_rate_hz"] = df["samples_per_sensor"] / DURATION_S
    df["overrun_percent"] = df["overruns"] / (
        df["overruns"] + df["samples_per_sensor"]
    ) * 100.0
    return df


# -----------------------------------------------------------------------------
# Helpers for selecting data
# -----------------------------------------------------------------------------

def axes_for_config(cfg: Dict) -> List[str]:
    """Return the list of axes to include when computing noise for a config."""
    if cfg["axes_type"] == "accel3":
        return ACC_AXES
    elif cfg["axes_type"] == "accel_gyro6":
        return ALL_AXES
    else:
        raise ValueError(f"Unknown axes_type: {cfg['axes_type']}")


def filter_log_config(
    log_df: pd.DataFrame, dlpf: int, condition: str, cfg: Dict
) -> pd.DataFrame:
    """Filter logs for a specific DLPF, condition, and channel configuration."""
    mask = (
        (log_df["dlpf"] == dlpf)
        & (log_df["condition"] == condition)
        & (log_df["mode"] == cfg["mode"])
        & (log_df["sensor_block"] == cfg["sensor_block"])
        & (log_df["profile"] == cfg["profile"])
    )
    return log_df[mask].sort_values("target_rate_hz")


def compute_noise_series(
    noise_df: pd.DataFrame, dlpf: int, condition: str, cfg: Dict
) -> pd.Series:
    """
    Compute a single noise metric (RMS std_dev) versus rate for a given config.

    The metric is:
        sqrt(mean(std_dev^2)) across all selected sensors + axes
    at each sampling rate.
    """
    axes = axes_for_config(cfg)
    mask = (
        (noise_df["dlpf"] == dlpf)
        & (noise_df["condition"] == condition)
        & (noise_df["tag"] == cfg["tag"])
        & (noise_df["axis"].isin(axes))
    )
    sub = noise_df[mask]
    if sub.empty:
        return pd.Series(dtype=float)

    grouped = sub.groupby("rate_hz")["std_dev"].apply(
        lambda v: np.sqrt(np.mean(np.square(v)))
    )
    # ensure sorted by rate
    grouped = grouped.sort_index()
    return grouped


# -----------------------------------------------------------------------------
# Plotting: still, channel-config comparison (DLPF 1 & 3)
# -----------------------------------------------------------------------------

def plot_overruns_vs_rate_channel_configs_still(log_df: pd.DataFrame) -> None:
    """
    For still condition, compare overruns vs target rate for:
      - 1 sensor, 3 channels
      - 1 sensor, 6 channels
      - 3 sensors, 6 channels
    for DLPF = 1 and DLPF = 3.
    """
    for dlpf in (1, 3):
        fig, ax = plt.subplots(figsize=(8, 5))
        for cfg in CHANNEL_CONFIGS:
            sub = filter_log_config(log_df, dlpf=dlpf, condition="still", cfg=cfg)
            if sub.empty:
                print(
                    f"[WARN] No still logs for DLPF={dlpf}, config={cfg['key']} "
                    f"(overruns plot)"
                )
                continue
            ax.plot(
                sub["target_rate_hz"],
                sub["overrun_percent"],
                marker="o",
                label=cfg["label"],
            )

        ax.set_title(f"Overruns vs target rate (still, DLPF={dlpf})")
        ax.set_xlabel("Target rate [Hz]")
        ax.set_ylabel("Overruns [%]")
        ax.grid(True, which="both", linestyle="--", alpha=0.4)
        ax.legend()
        fig.tight_layout()
        out_path = FIG_DIR / f"overruns_vs_rate_still_dlpf{dlpf}.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"Saved {out_path}")


def plot_effective_vs_target_channel_configs_still(log_df: pd.DataFrame) -> None:
    """
    For still condition, compare effective vs target rate for the same configs,
    for DLPF = 1 and DLPF = 3.
    """
    for dlpf in (1, 3):
        fig, ax = plt.subplots(figsize=(8, 5))

        # reference line y = x
        # cover the whole range present for this DLPF
        sub_all = log_df[(log_df["dlpf"] == dlpf) & (log_df["condition"] == "still")]
        if sub_all.empty:
            print(f"[WARN] No still logs for DLPF={dlpf} (effective vs target plot)")
            continue
        min_r = sub_all["target_rate_hz"].min()
        max_r = sub_all["target_rate_hz"].max()
        ax.plot([min_r, max_r], [min_r, max_r], "k--", alpha=0.5, label="ideal")

        for cfg in CHANNEL_CONFIGS:
            sub = filter_log_config(log_df, dlpf=dlpf, condition="still", cfg=cfg)
            if sub.empty:
                print(
                    f"[WARN] No still logs for DLPF={dlpf}, config={cfg['key']} "
                    f"(effective vs target plot)"
                )
                continue
            ax.plot(
                sub["target_rate_hz"],
                sub["effective_rate_hz"],
                marker="o",
                label=cfg["label"],
            )

        ax.set_title(f"Effective vs target rate (still, DLPF={dlpf})")
        ax.set_xlabel("Target rate [Hz]")
        ax.set_ylabel("Effective rate from samples [Hz]")
        ax.grid(True, which="both", linestyle="--", alpha=0.4)
        ax.legend()
        fig.tight_layout()
        out_path = FIG_DIR / f"effective_vs_target_still_dlpf{dlpf}.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"Saved {out_path}")


def plot_noise_vs_rate_channel_configs_still(noise_df: pd.DataFrame) -> None:
    """
    For still condition, compare noise (RMS std_dev over chosen axes) vs rate
    for:
      - 1 sensor, 3 channels (accel only)
      - 1 sensor, 6 channels (acc+gyro)
      - 3 sensors, 6 channels (acc+gyro)
    for DLPF = 1 and DLPF = 3.
    """
    for dlpf in (1, 3):
        fig, ax = plt.subplots(figsize=(8, 5))
        any_data = False
        for cfg in CHANNEL_CONFIGS:
            series = compute_noise_series(
                noise_df, dlpf=dlpf, condition="still", cfg=cfg
            )
            if series.empty:
                print(
                    f"[WARN] No still noise data for DLPF={dlpf}, config={cfg['key']}"
                )
                continue
            any_data = True
            ax.plot(
                series.index.values,
                series.values,
                marker="o",
                label=cfg["label"],
            )

        if not any_data:
            plt.close(fig)
            print(f"[WARN] Skipping noise figure for DLPF={dlpf}, no data.")
            continue

        ax.set_title(f"Noise vs rate (still, DLPF={dlpf})")
        ax.set_xlabel("Sampling rate [Hz]")
        ax.set_ylabel("RMS noise std_dev (over selected axes)")
        ax.grid(True, which="both", linestyle="--", alpha=0.4)
        ax.legend()
        fig.tight_layout()
        out_path = FIG_DIR / f"noise_vs_rate_still_dlpf{dlpf}.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"Saved {out_path}")


# -----------------------------------------------------------------------------
# Plotting: DLPF = 1, still vs shaking comparison
# -----------------------------------------------------------------------------

def plot_dlpf1_overruns_still_vs_shaking(log_df: pd.DataFrame) -> None:
    """
    For DLPF=1, compare overruns vs target rate between:
      - still
      - with shaking
    for each channel configuration.
    """
    dlpf = 1
    for cfg in CHANNEL_CONFIGS:
        fig, ax = plt.subplots(figsize=(8, 5))
        for cond, style in (("still", "o-"), ("shaking", "s--")):
            sub = filter_log_config(log_df, dlpf=dlpf, condition=cond, cfg=cfg)
            if sub.empty:
                print(
                    f"[WARN] No logs for DLPF=1, condition={cond}, "
                    f"config={cfg['key']} (overruns still vs shaking)"
                )
                continue
            ax.plot(
                sub["target_rate_hz"],
                sub["overrun_percent"],
                style,
                label=f"{cond}",
            )

        ax.set_title(
            f"Overruns vs rate (DLPF=1, still vs shaking, {cfg['label']})"
        )
        ax.set_xlabel("Target rate [Hz]")
        ax.set_ylabel("Overruns [%]")
        ax.grid(True, which="both", linestyle="--", alpha=0.4)
        ax.legend(title="Condition")
        fig.tight_layout()
        out_path = FIG_DIR / f"overruns_vs_rate_dlpf1_{cfg['key']}_still_vs_shaking.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"Saved {out_path}")


def plot_dlpf1_effective_vs_target_still_vs_shaking(log_df: pd.DataFrame) -> None:
    """
    For DLPF=1, compare effective vs target rate between:
      - still
      - with shaking
    for each channel configuration.
    """
    dlpf = 1
    for cfg in CHANNEL_CONFIGS:
        fig, ax = plt.subplots(figsize=(8, 5))

        # ideal line
        sub_all = log_df[log_df["dlpf"] == dlpf]
        min_r = sub_all["target_rate_hz"].min()
        max_r = sub_all["target_rate_hz"].max()
        ax.plot([min_r, max_r], [min_r, max_r], "k--", alpha=0.5, label="ideal")

        for cond, style in (("still", "o-"), ("shaking", "s--")):
            sub = filter_log_config(log_df, dlpf=dlpf, condition=cond, cfg=cfg)
            if sub.empty:
                print(
                    f"[WARN] No logs for DLPF=1, condition={cond}, "
                    f"config={cfg['key']} (effective vs target still vs shaking)"
                )
                continue
            ax.plot(
                sub["target_rate_hz"],
                sub["effective_rate_hz"],
                style,
                label=f"{cond}",
            )

        ax.set_title(
            f"Effective vs target (DLPF=1, still vs shaking, {cfg['label']})"
        )
        ax.set_xlabel("Target rate [Hz]")
        ax.set_ylabel("Effective rate from samples [Hz]")
        ax.grid(True, which="both", linestyle="--", alpha=0.4)
        ax.legend(title="Condition")
        fig.tight_layout()
        out_path = (
            FIG_DIR / f"effective_vs_target_dlpf1_{cfg['key']}_still_vs_shaking.png"
        )
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"Saved {out_path}")


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------

def main() -> None:
    print("Base directory: ", BASE_DIR)
    print("Data directory: ", DATA_DIR)
    print("Logs directory: ", LOG_DIR)
    print("Figures will be saved under:", FIG_DIR)
    print()

    print("Loading noise summary CSVs...")
    noise_df = load_noise_data()
    print(f"Loaded {len(noise_df)} noise rows.")
    print(
        "Noise tags present:",
        sorted(noise_df["tag"].unique().tolist()),
    )
    print()

    print("Loading log files...")
    log_df = load_log_data()
    print(f"Loaded {len(log_df)} log entries.")
    print(
        "Example log rows:\n",
        log_df.head(),
    )
    print()

    # 1) Still, channel configs: overruns, noise, effective vs target
    plot_overruns_vs_rate_channel_configs_still(log_df)
    plot_effective_vs_target_channel_configs_still(log_df)
    plot_noise_vs_rate_channel_configs_still(noise_df)

    # 2) DLPF 1, still vs shaking: overruns and effective vs target
    plot_dlpf1_overruns_still_vs_shaking(log_df)
    plot_dlpf1_effective_vs_target_still_vs_shaking(log_df)

    print("\nDone. Figures written to", FIG_DIR)


if __name__ == "__main__":
    main()
