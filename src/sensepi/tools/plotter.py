#!/usr/bin/env python3
"""
Simple CLI plotter for SensePi CSV logs.

This script is intended to be launched either directly from the command line
or via ``LocalPlotRunner`` in ``sensepi.tools.local_plot_runner``. It uses Matplotlib's
standard interactive window (no PySide6 integration) to display either:

  * a static replay of a CSV log (``--mode replay``), or
  * a "live" view that periodically reloads the CSV file (``--mode follow``).

By default, if no ``--file`` is provided, the script will look for the newest
``*.csv`` file under:

  * ``data/raw/``
  * ``logs/``
  * the repository root

and use that as the source.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


REPO_ROOT = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- # helpers
def find_latest_csv(search_roots: Sequence[Path]) -> Optional[Path]:
    candidates: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        candidates.extend(root.glob("*.csv"))

    if not candidates:
        return None

    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_csv(path: Path) -> tuple[np.ndarray, list[str]]:
    """Load a CSV file with a header row into a structured NumPy array."""
    data = np.genfromtxt(path, delimiter=",", names=True)

    # When there's only a single row, genfromtxt may return a scalar; coerce.
    if data.size == 0:
        raise ValueError(f"File {path} contains no data rows")
    if data.ndim == 0:
        data = data.reshape(1)

    names = list(data.dtype.names or [])
    if not names:
        raise ValueError(f"File {path} has no header / column names")

    return data, names


def infer_sensor_type(columns: Sequence[str]) -> str:
    lower = {c.lower() for c in columns}
    if {"ax", "ay", "az"} & lower or {"gx", "gy", "gz"} & lower:
        return "mpu6050"
    if {"x_lp", "y_lp"} <= lower or {"x", "y"} <= lower:
        return "adxl203_ads1115"
    return "generic"


def build_time_axis(data: np.ndarray, columns: Sequence[str]) -> tuple[np.ndarray, str]:
    """Return (t, x_label)."""
    if "t_s" in columns:
        t = data["t_s"]
        return t, "Time [s]"
    if "timestamp_ns" in columns:
        ns = data["timestamp_ns"]
        t0 = ns[0]
        t = (ns - t0) * 1e-9
        return t, "Time [s since start]"
    n = data.shape[0]
    t = np.arange(n, dtype=float)
    return t, "Sample index"


def pick_data_columns(sensor_type: str, columns: Sequence[str]) -> tuple[list[str], list[str]]:
    """Return (acc_columns, gyro_columns) based on the header."""
    cols_set = set(columns)
    if sensor_type == "mpu6050":
        acc_cols = [c for c in ("ax", "ay", "az") if c in cols_set]
        gyro_cols = [c for c in ("gx", "gy", "gz") if c in cols_set]
        return acc_cols, gyro_cols

    if sensor_type == "adxl203_ads1115":
        # Prefer filtered values if present.
        if "x_lp" in cols_set or "y_lp" in cols_set:
            acc_cols = [c for c in ("x_lp", "y_lp") if c in cols_set]
        else:
            acc_cols = [c for c in ("x", "y") if c in cols_set]
        return acc_cols, []

    ignore = {"timestamp_ns", "t_s", "sensor_id"}
    acc_cols = [c for c in columns if c not in ignore]
    return acc_cols, []


def setup_figure(
    path: Path,
    sensor_type: str,
    data: np.ndarray,
    columns: Sequence[str],
):
    """Create figure/axes/lines and return (fig, axes, lines, time_vector)."""
    t, x_label = build_time_axis(data, columns)
    acc_cols, gyro_cols = pick_data_columns(sensor_type, columns)

    if not acc_cols and not gyro_cols:
        raise ValueError(f"No plottable data columns found in {path}")

    n_axes = 2 if gyro_cols else 1
    fig, axes = plt.subplots(n_axes, 1, sharex=True)
    if not isinstance(axes, (list, tuple, np.ndarray)):
        axes = [axes]

    lines: dict[str, any] = {}

    # Acceleration subplot(s)
    if acc_cols:
        ax0 = axes[0]
        for col in acc_cols:
            y = data[col]
            (line,) = ax0.plot(t, y, label=col)
            lines[col] = line
        if sensor_type in ("mpu6050", "adxl203_ads1115"):
            ax0.set_ylabel("Acceleration [m/s²]")
        else:
            ax0.set_ylabel("Value")
        ax0.legend(loc="upper right")
        ax0.set_title(f"{sensor_type} — {path.name}")

    # Gyro subplot
    if gyro_cols:
        ax1 = axes[1]
        for col in gyro_cols:
            y = data[col]
            (line,) = ax1.plot(t, y, label=col)
            lines[col] = line
        ax1.set_ylabel("Angular rate [deg/s]")
        ax1.legend(loc="upper right")

    axes[-1].set_xlabel(x_label)
    fig.tight_layout()

    return fig, axes, lines, t


def build_plot_for_file(path: Path, sensor_type: str = "auto"):
    """Return a Matplotlib Figure configured for the given log file."""

    data, columns = load_csv(path)
    if sensor_type == "auto":
        sensor_type = infer_sensor_type(columns)

    fig, axes, lines, _t = setup_figure(path, sensor_type, data, columns)
    return fig, axes, lines


# --------------------------------------------------------------------------- # plotting modes
def plot_replay(path: Path, sensor_type: str) -> None:
    fig, _axes, _lines = build_plot_for_file(path, sensor_type)
    fig.canvas.manager.set_window_title(f"SensePi replay — {path.name}")
    plt.show()


def plot_follow(path: Path, sensor_type: str, interval_s: float) -> None:
    data, columns = load_csv(path)
    if sensor_type == "auto":
        sensor_type = infer_sensor_type(columns)

    fig, axes, lines, _t = setup_figure(path, sensor_type, data, columns)

    def _update(_frame):
        try:
            new_data, new_columns = load_csv(path)
        except Exception:
            # If the file temporarily disappears or is being written to, just
            # skip this frame.
            return list(lines.values())

        t_new, _x_label = build_time_axis(new_data, new_columns)

        for name, line in lines.items():
            if name not in new_columns:
                continue
            y = new_data[name]
            line.set_data(t_new, y)

        for ax in axes:
            ax.relim()
            ax.autoscale_view()

        return list(lines.values())

    fig.canvas.manager.set_window_title(f"SensePi live — {path.name}")
    FuncAnimation(fig, _update, interval=interval_s * 1000.0, blit=False)
    plt.show()


# --------------------------------------------------------------------------- # CLI
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Simple Matplotlib-based plotter for SensePi CSV logs."
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        help=(
            "Path to a CSV log file. If omitted, the newest CSV found under "
            "data/raw, logs, or the project root is used."
        ),
    )
    parser.add_argument(
        "-s",
        "--sensor",
        type=str,
        choices=["auto", "mpu6050", "adxl203_ads1115", "generic"],
        default="auto",
        help="Sensor type for plotting (default: auto-detect from columns).",
    )
    parser.add_argument(
        "-m",
        "--mode",
        type=str,
        choices=["follow", "replay"],
        default="follow",
        help=(
            "Plot mode: 'replay' for a static plot, 'follow' to periodically "
            "reload the file for a live view (default)."
        ),
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=0.5,
        help="Update interval in seconds when using --mode follow (default: 0.5).",
    )

    args = parser.parse_args(argv)

    if args.file:
        csv_path = Path(args.file).expanduser().resolve()
        if not csv_path.exists():
            parser.error(f"CSV file not found: {csv_path}")
    else:
        csv_path = find_latest_csv(
            [
                REPO_ROOT / "data" / "raw",
                REPO_ROOT / "logs",
                REPO_ROOT,
            ]
        )
        if csv_path is None:
            parser.error(
                "No CSV files found in data/raw, logs, or the project root.\n"
                "Specify a file explicitly with --file."
            )
        print(f"[INFO] Using latest CSV log: {csv_path}")

    try:
        if args.mode == "replay":
            plot_replay(csv_path, args.sensor)
        else:
            plot_follow(csv_path, args.sensor, args.interval)
    except KeyboardInterrupt:
        # Allow clean exit on Ctrl+C
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
