
# Prompt: Measure FPS and estimate dropped frames in the Qt + Matplotlib loop

You have already:

- A `PlotPerfStats` dataclass attached to `SignalPlotWidget` with:
  - `frame_times`, `frame_durations`, and `sample_to_draw_latencies`.
- A `SignalPlotWidget.redraw()` implementation that calls `record_frame(...)` and `record_latency(...)`.

Now we want to **approximate effective FPS and detect “dropped” / skipped frames** by comparing:

- The **target timer interval** (e.g. 50 Hz → 20 ms).
- The **actual frame times** (how often `redraw()` is called).
- The **Qt timer tick frequency** (how often the `QTimer.timeout` signal fires).

---

## Your task

1. **Store the configured refresh interval / target FPS** in `SignalPlotWidget`.
2. **Instrument the QTimer handler (in `SignalsTab` or wherever the timer is created)** to count timer ticks per second.
3. **Add logic to compute:**
   - Actual FPS from `PlotPerfStats.compute_fps()`.
   - Timer tick rate.
   - A “drop ratio” or similar: how many timer ticks did not result in distinct frame renderings.

4. **Expose this in the `get_perf_snapshot()` API** so an overlay / logger can read:
   - `target_fps`
   - `achieved_fps`
   - `timer_hz`
   - `approx_dropped_frames_per_sec` (or `drop_ratio`).

---

## Implementation details

1. **Store target FPS / interval in `SignalPlotWidget`**:

When you create the `QTimer`, you likely use constants 4 Hz / 20 Hz / 50 Hz or “follow device rate”. Make sure the plot widget knows the target:

```python
class SignalsTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._plot = SignalPlotWidget(self)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._on_timer_timeout)

        # Example: 50 Hz → 20 ms
        self._refresh_hz = 20.0  # set this from config/UI
        self._timer.setInterval(int(1000.0 / self._refresh_hz))

        self._timer_tick_counter = 0
        self._timer_measure_window_start = time.perf_counter()
        self._timer_stats_hz = 0.0

    def _on_timer_timeout(self) -> None:
        # Count ticks
        if ENABLE_PLOT_PERF_METRICS:
            self._timer_tick_counter += 1
            now = time.perf_counter()
            if now - self._timer_measure_window_start >= 1.0:
                self._timer_stats_hz = self._timer_tick_counter / (now - self._timer_measure_window_start)
                self._timer_tick_counter = 0
                self._timer_measure_window_start = now

        # Delegate to plot widget
        self._plot.redraw()
```

Then, pass the target refresh rate into the plot widget:

```python
self._plot.set_target_refresh_rate(self._refresh_hz)
```

Add this method to `SignalPlotWidget`:

```python
class SignalPlotWidget(QtWidgets.QWidget):
    def __init__(...):
        ...
        self._target_refresh_hz: float | None = None

    def set_target_refresh_rate(self, hz: float | None) -> None:
        self._target_refresh_hz = hz
```

2. **Expose timer stats from `SignalsTab` to the plot widget** (optional but convenient):

You have two options:

- (a) Let `SignalsTab` own the timer stats and offer a small method `get_timer_stats()` that the overlay can query directly.
- (b) Push the timer Hz into the plot widget once per second.

For simplicity, option (a) is fine:

```python
class SignalsTab(QtWidgets.QWidget):
    # ...

    def get_perf_snapshot(self) -> dict:
        snap = self._plot.get_perf_snapshot()
        if ENABLE_PLOT_PERF_METRICS:
            snap.update({
                "timer_hz": self._timer_stats_hz,
                "target_fps": self._refresh_hz,
            })
        else:
            snap.update({
                "timer_hz": 0.0,
                "target_fps": 0.0,
            })
        return snap
```

3. **Compute an approximate drop metric**:

In `SignalPlotWidget.get_perf_snapshot()`, when metrics are enabled, you can estimate how many frames are “missing” compared to the timer:

```python
class SignalPlotWidget(QtWidgets.QWidget):
    # existing get_perf_snapshot...

    def get_perf_snapshot(self) -> dict:
        if not (ENABLE_PLOT_PERF_METRICS and self._perf):
            return {
                "fps": 0.0,
                "avg_frame_ms": 0.0,
                "avg_latency_ms": 0.0,
                "max_latency_ms": 0.0,
                "target_fps": 0.0,
                "approx_dropped_fps": 0.0,
            }

        fps = self._perf.compute_fps()
        avg_frame_ms = self._perf.avg_frame_ms()
        avg_latency_ms = self._perf.avg_latency_ms()
        max_latency_ms = self._perf.max_latency_ms()

        target = self._target_refresh_hz or 0.0
        approx_dropped_fps = 0.0
        if target > 0 and fps > 0:
            # If timer fires 'target' times per second and we render 'fps',
            # then drops ≈ max(0, target - fps)
            approx_dropped_fps = max(0.0, target - fps)

        return {
            "fps": fps,
            "avg_frame_ms": avg_frame_ms,
            "avg_latency_ms": avg_latency_ms,
            "max_latency_ms": max_latency_ms,
            "target_fps": target,
            "approx_dropped_fps": approx_dropped_fps,
        }
```

You can later refine this using the `timer_hz` value from `SignalsTab` if needed.

4. **Handle “follow sampling rate” mode**:

If you have a mode where the timer interval follows the device sampling rate, you can:

- Set `_refresh_hz` accordingly from the device rate.
- Mark `set_target_refresh_rate(None)` or a special flag if it’s not fixed.
- In that mode, FPS vs. target is less meaningful, but you can still show actual FPS and latency.

---

## Output

After implementing this:

- Each second, you’ll have a reasonable estimate of:
  - Target FPS (from UI),
  - Actual FPS (from frame times),
  - Timer Hz (from tick counting, if you expose it),
  - Approximate dropped frames per second.
- The `SignalsTab.get_perf_snapshot()` (or similar) method will provide a combined dict ready to be used by a GUI overlay or logger.
