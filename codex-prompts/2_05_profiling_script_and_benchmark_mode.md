
# Prompt: Add a benchmark mode with synthetic data + profiling hooks

Now that you can see performance metrics in the GUI, you want a **repeatable performance test protocol** that doesn’t depend on a live Raspberry Pi.

The idea:

- Add a **benchmark / perf-test mode** that:
  - Uses a synthetic data source that mimics the sensor stream at configurable rates.
  - Runs the GUI with this synthetic stream for a fixed duration.
  - Logs performance metrics to stdout and/or a CSV file.
- Provide a small helper script / entry point to run this mode and optionally wrap it with `cProfile`.

---

## Your task

1. **Add a synthetic data generator** that:
   - Runs in the GUI process (in a QTimer or background thread) to emit `MpuSample`-like objects at a given rate (e.g. 50 Hz, 100 Hz, 200 Hz, 500 Hz).
   - For simplicity, you can generate sinusoidal or random values for each channel.

2. **Ensure synthetic samples go through the exact same pipeline** as real samples:
   - They must call `SignalsTab.handle_sample(sample)` (or equivalent).

3. **Add a CLI option or environment flag** to start the app in “benchmark mode”:
   - Example: `python mpu6050_multi_logger.py --benchmark --rate 200 --duration 30 --refresh 20 --channels 18`.
   - In this mode:
     - No real network/Pi connection is opened.
     - The synthetic data generator is started.

4. **During benchmark mode**, periodically:
   - Query `signals_tab.get_perf_snapshot()`.
   - Log summary metrics every second.
   - Optionally append to a CSV file with columns:
     - `t`, `fps`, `target_fps`, `timer_hz`, `avg_frame_ms`, `avg_latency_ms`, `max_latency_ms`, `approx_dropped_fps`, `cpu_percent`.

5. **Add a small helper to run with `cProfile`**:
   - A separate script `profile_benchmark.py` that runs the benchmark entry point under `cProfile` and writes the stats to a `.prof` file.

---

## Implementation details

1. **Synthetic sample generator**:

In the GUI module or a new `synthetic_source.py`:

```python
# synthetic_source.py
import math
import time
from dataclasses import dataclass
from typing import Callable

@dataclass
class SyntheticSample:
    # mimic MpuSample enough for the GUI
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    # add more fields as needed (e.g. sensor_id)
    sensor_id: int = 0

    # optional: device timestamp
    ts: float = 0.0
```

In `SignalsTab`, add:

```python
class SignalsTab(QtWidgets.QWidget):
    def start_synthetic_stream(self, rate_hz: float) -> None:
        self._synthetic_timer = QtCore.QTimer(self)
        interval_ms = int(1000.0 / rate_hz)
        self._synthetic_phase = 0.0
        self._synthetic_dt = 2.0 * math.pi * (1.0 / rate_hz)

        self._synthetic_timer.setInterval(interval_ms)
        self._synthetic_timer.timeout.connect(self._on_synthetic_tick)
        self._synthetic_timer.start()

    def _on_synthetic_tick(self) -> None:
        t = time.time()
        phase = self._synthetic_phase
        self._synthetic_phase += self._synthetic_dt

        # simple sine wave + noise for each axis
        sample = SyntheticSample(
            ax=math.sin(phase),
            ay=math.sin(phase + 0.5),
            az=math.sin(phase + 1.0),
            gx=math.cos(phase),
            gy=math.cos(phase + 0.5),
            gz=math.cos(phase + 1.0),
            sensor_id=0,
            ts=t,
        )

        # Reuse existing pipeline
        self.handle_sample(sample)
```

Adjust fields to match the real `MpuSample` shape so that your plotting code doesn’t need to special-case it.

2. **CLI option / flag for benchmark mode**:

In `mpu6050_multi_logger.py` (or the main entry point), add argparse logic:

```python
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", action="store_true", help="Run in synthetic benchmark mode")
    parser.add_argument("--bench-rate", type=float, default=200.0, help="Synthetic input rate (Hz)")
    parser.add_argument("--bench-duration", type=float, default=30.0, help="Benchmark duration (seconds)")
    parser.add_argument("--bench-refresh", type=float, default=20.0, help="Plot refresh rate (Hz)")
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()

    if args.benchmark:
        win.signals_tab.configure_refresh_rate(args.bench_refresh)
        win.signals_tab.start_synthetic_stream(args.bench_rate)
        win.start_benchmark_logger(args.bench_duration)
    else:
        # normal network / Pi connection setup
        win.start_real_stream()

    sys.exit(app.exec())
```

3. **Benchmark logger**:

In `MainWindow` or `SignalsTab`, add:

```python
import csv
import time
from .perf_system import get_process_cpu_percent

class MainWindow(QtWidgets.QMainWindow):
    def start_benchmark_logger(self, duration_s: float) -> None:
        self._bench_start = time.perf_counter()
        self._bench_duration_s = duration_s
        self._bench_log = []

        self._bench_timer = QtCore.QTimer(self)
        self._bench_timer.setInterval(1000)  # 1 Hz logging
        self._bench_timer.timeout.connect(self._on_bench_tick)
        self._bench_timer.start()

    def _on_bench_tick(self) -> None:
        now = time.perf_counter()
        elapsed = now - self._bench_start
        snap = self.signals_tab.get_perf_snapshot()
        cpu = get_process_cpu_percent()

        row = {
            "t": elapsed,
            "fps": snap.get("fps", 0.0),
            "target_fps": snap.get("target_fps", 0.0),
            "timer_hz": snap.get("timer_hz", 0.0),
            "avg_frame_ms": snap.get("avg_frame_ms", 0.0),
            "avg_latency_ms": snap.get("avg_latency_ms", 0.0),
            "max_latency_ms": snap.get("max_latency_ms", 0.0),
            "approx_dropped_fps": snap.get("approx_dropped_fps", 0.0),
            "cpu_percent": cpu,
        }
        self._bench_log.append(row)

        if elapsed >= self._bench_duration_s:
            self._bench_timer.stop()
            self._write_bench_csv("benchmark_results.csv")
            QtWidgets.QMessageBox.information(self, "Benchmark", "Benchmark finished.")

    def _write_bench_csv(self, path: str) -> None:
        if not self._bench_log:
            return
        fieldnames = list(self._bench_log[0].keys())
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self._bench_log)
```

4. **Helper script with `cProfile`**:

Create `profile_benchmark.py` at repo root:

```python
# profile_benchmark.py
import cProfile
import pstats
import sys
from pathlib import Path

def run():
    # Note: adapt module / main entry as needed
    import mpu6050_multi_logger
    sys.argv = [
        "mpu6050_multi_logger.py",
        "--benchmark",
        "--bench-rate", "200",
        "--bench-duration", "30",
        "--bench-refresh", "20",
    ]
    mpu6050_multi_logger.main()

if __name__ == "__main__":
    prof_path = Path("benchmark_profile.prof")
    cProfile.run("run()", str(prof_path))
    print(f"cProfile stats written to {prof_path}")
    stats = pstats.Stats(str(prof_path))
    stats.sort_stats("cumulative").print_stats(20)
```

---

## Output

After implementing this, you should be able to run:

```bash
python mpu6050_multi_logger.py --benchmark --bench-rate 200 --bench-duration 30 --bench-refresh 20
```

and:

- See the GUI with synthetic data.
- Observe the performance HUD.
- After 30 seconds, a `benchmark_results.csv` file will be created with time-series metrics.

You can also run:

```bash
python profile_benchmark.py
```

to get a `.prof` file for deeper analysis with tools like SnakeViz or `pstats`.
