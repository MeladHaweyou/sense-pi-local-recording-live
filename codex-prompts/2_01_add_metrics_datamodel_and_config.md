
# Prompt: Add performance metrics data model and debug config

You are working in a PySide6 + Matplotlib desktop GUI project for live plotting of MPU6050 sensor data.
The main components involved in plotting are:

- `mpu6050_multi_logger.py` – starts the GUI and networking / logging.
- A GUI tab class (e.g. `SignalsTab` / `RecorderTab`) that receives `MpuSample` objects from the backend.
- `SignalPlotWidget` – a QWidget wrapping a Matplotlib canvas that:
  - Holds ring buffers / history of samples per channel.
  - Exposes an `add_sample(...)` method.
  - Has a `redraw()` method connected to a `QTimer` for live updates.

We want to **introduce a small performance metrics data model** and a **debug configuration flag** that will be used by later tasks.

---

## Your task

1. **Create a lightweight performance metrics dataclass** used by the plotting code:
   - It should track at least:
     - Recent frame times (timestamps when `redraw()` is called).
     - Recent frame durations (how long each `redraw()` takes).
     - Recent sample-to-draw latencies (filled in later).
   - Use bounded deques to avoid unbounded growth.

2. **Add a debug configuration flag** to globally enable/disable metrics:
   - Example: `ENABLE_PLOT_PERF_METRICS = True` in a central config module or constants section.
   - All later instrumentation must check this flag before doing any heavy work.

3. **Expose a minimal API on `SignalPlotWidget`** to get a current summary:
   - Provide a method like `get_perf_snapshot()` that returns:
     - `fps` (estimated from recent frame times),
     - `avg_frame_ms`,
     - placeholder fields for `avg_latency_ms`, `max_latency_ms` (can be `0.0` for now).

Don’t try to draw anything or log to disk yet; just data structures and a clean way to fetch a snapshot.

---

## Implementation details

1. **Add a small module or dataclass near the plotting code** (e.g. in the same file as `SignalPlotWidget`):

```python
# perf_metrics.py or at top of signal_plot_widget.py

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional
import time

MAX_SAMPLES_PERF = 300  # about last 5–15 seconds, depending on FPS

@dataclass
class PlotPerfStats:
    frame_times: Deque[float] = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES_PERF))
    frame_durations: Deque[float] = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES_PERF))
    sample_to_draw_latencies: Deque[float] = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES_PERF))

    def record_frame(self, start_ts: float, end_ts: float) -> None:
        self.frame_times.append(end_ts)
        self.frame_durations.append(end_ts - start_ts)

    def record_latency(self, latency_s: float) -> None:
        self.sample_to_draw_latencies.append(latency_s)

    def compute_fps(self) -> float:
        if len(self.frame_times) < 2:
            return 0.0
        dt = self.frame_times[-1] - self.frame_times[0]
        if dt <= 0:
            return 0.0
        return (len(self.frame_times) - 1) / dt

    def avg_frame_ms(self) -> float:
        if not self.frame_durations:
            return 0.0
        return 1000.0 * sum(self.frame_durations) / len(self.frame_durations)

    def avg_latency_ms(self) -> float:
        if not self.sample_to_draw_latencies:
            return 0.0
        return 1000.0 * sum(self.sample_to_draw_latencies) / len(self.sample_to_draw_latencies)

    def max_latency_ms(self) -> float:
        if not self.sample_to_draw_latencies:
            return 0.0
        return 1000.0 * max(self.sample_to_draw_latencies)
```

2. **Add a global or config constant** (place this where you keep other app-wide constants):

```python
# config.py or at module level
ENABLE_PLOT_PERF_METRICS: bool = True
```

3. **Integrate into `SignalPlotWidget`**:

- Add a `PlotPerfStats` instance.
- Add a `get_perf_snapshot()` method.

Example (adapt names to your actual class):

```python
# inside signal_plot_widget.py

from .config import ENABLE_PLOT_PERF_METRICS
from .perf_metrics import PlotPerfStats
import time

class SignalPlotWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # ... existing init ...
        self._perf = PlotPerfStats() if ENABLE_PLOT_PERF_METRICS else None

    def get_perf_snapshot(self) -> dict:
        """Lightweight, safe to call from GUI thread at ~1 Hz."""
        if not (ENABLE_PLOT_PERF_METRICS and self._perf):
            return {
                "fps": 0.0,
                "avg_frame_ms": 0.0,
                "avg_latency_ms": 0.0,
                "max_latency_ms": 0.0,
            }

        return {
            "fps": self._perf.compute_fps(),
            "avg_frame_ms": self._perf.avg_frame_ms(),
            "avg_latency_ms": self._perf.avg_latency_ms(),
            "max_latency_ms": self._perf.max_latency_ms(),
        }
```

4. **Prepare for later integration**:
   - Do **not** call `record_frame` or `record_latency` yet – that will be done in later prompts.
   - Ensure you import `PlotPerfStats` only where needed to avoid circular imports.

---

## Output

When you’re done, the project should:

- Compile and run without changing behavior.
- Have a `PlotPerfStats` dataclass available.
- Have a `SignalPlotWidget.get_perf_snapshot()` API that returns basic metrics (currently zeros except FPS & avg_frame_ms once wired in later prompts).
