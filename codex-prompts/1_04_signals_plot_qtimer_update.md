# AI Prompt 04 – Signals Plot QTimer Update Logic

You are an AI coding assistant working on the **Sensors recording and plotting** project.
Implement the **time-domain signals plot** update logic using **QTimer** and ring buffers.

## Goals

- Keep the plot visually smooth and responsive using a fixed or adaptive refresh interval.
- On each timer tick:
  - Determine the current time window.
  - Fetch latest data from buffers for each visible channel.
  - Update the Matplotlib / pyqtgraph line objects efficiently.

## Constraints & Design

- GUI toolkit: **PySide6** with Matplotlib embedded (or pyqtgraph; adapt as needed).
- Refresh interval:
  - Fixed mode: typically 50 ms (20 Hz), configurable.
  - Adaptive mode: `interval_ms = max(1000 / stream_rate_hz, 20)`.
- Time window length: e.g. `time_window_s = 10.0`.
- Use **sensor timestamps**, not wall-clock, to define the x-axis.

## Tasks

1. In the `SignalsTab` (or equivalent widget):
   - Set up a `QTimer` for periodic updates.
   - Provide a method `set_refresh_mode(mode, stream_rate_hz=None)`.
2. Implement `on_timer()` / `update_plot()`:
   - Compute `latest_t_ns` across all visible buffers.
   - If `latest_t_ns` is `None`, skip drawing or clear plot.
   - Compute `t_start_ns = latest_t_ns - time_window_s * 1e9`.
   - For each line (sensor/channel):
     - `ts_ns, vs = buffer.get_window(t_start_ns, latest_t_ns)`.
     - Convert `ts_s = (ts_ns - latest_t_ns) / 1e9 + time_window_s` or similar to center window.
     - Update `line.set_data(ts_s, vs)`.
   - Adjust x-limits to `[0, time_window_s]` or `[t_start_s, latest_t_s]` consistent with your scheme.
   - Call `canvas.draw()` / `canvas.draw_idle()`.

## Important Code Skeleton (Python)

```python
from PySide6.QtCore import QTimer

class SignalsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # ... init Matplotlib Figure, Axes, etc.
        self.time_window_s = 10.0
        self.refresh_mode = "fixed"
        self.fixed_interval_ms = 50  # default 20 Hz
        self.stream_rate_hz = None
        self.buffers = {}  # (sensor_id, channel) -> TimeSeriesBufferWrapper
        self.lines = {}    # (sensor_id, channel) -> Line2D
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_plot)

    def set_refresh_mode(self, mode, stream_rate_hz=None):
        self.refresh_mode = mode
        self.stream_rate_hz = stream_rate_hz
        if mode == "adaptive" and stream_rate_hz:
            interval_ms = max(int(1000 / stream_rate_hz), 20)
        else:
            interval_ms = self.fixed_interval_ms
        self.timer.setInterval(interval_ms)

    def start(self):
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def update_plot(self):
        # find latest timestamp across all buffers
        latest_ns = None
        for buf in self.buffers.values():
            t_ns = buf.latest_timestamp_ns()
            if t_ns is not None and (latest_ns is None or t_ns > latest_ns):
                latest_ns = t_ns

        if latest_ns is None:
            # nothing to plot
            return

        t_start_ns = latest_ns - int(self.time_window_s * 1e9)

        for key, buf in self.buffers.items():
            ts_ns, vs = buf.get_window(t_start_ns, latest_ns)
            if ts_ns.size == 0:
                continue
            # x-axis in seconds relative to window start
            xs = (ts_ns - t_start_ns) / 1e9
            line = self.lines.get(key)
            if line is not None:
                line.set_data(xs, vs)

        self.ax.set_xlim(0, self.time_window_s)
        self.canvas.draw_idle()
```

## Notes for the AI

- Ensure `buffers` are only read here; writer thread should only append.
- Consider using `draw_idle()` to let Qt batch repaints.
- Optimize to avoid reallocating large arrays unnecessarily if performance is an issue.
