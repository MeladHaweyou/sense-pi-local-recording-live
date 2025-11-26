
# Prompt: Instrument data pipeline to measure end-to-end latency

You are working on the same PySide6 + Matplotlib data plotting project.
From the previous task, `SignalPlotWidget` now has a `PlotPerfStats` instance and a `get_perf_snapshot()` method.

We now want to **measure end-to-end latency** from the time a sensor sample is received in the GUI to the time that sample is rendered in the plot.

---

## Assumed high-level flow

Roughly, the GUI data flow is:

1. Some receiver (thread / socket handler) in `mpu6050_multi_logger.py` or a related module receives an `MpuSample`.
2. It forwards the sample to the GUI side, e.g. to `SignalsTab.handle_sample(sample: MpuSample)`.
3. `SignalsTab` / `RecorderTab` forwards the sample to `SignalPlotWidget.add_sample(sample)` or similar.
4. A `QTimer` periodically calls `SignalPlotWidget.redraw()`, which pulls data from ring buffers and updates the Matplotlib figure.

We want to timestamp **when the GUI first sees the sample** and **when it is first drawn**.

---

## Your task

1. **Extend the sample object or wrap it so that we can store a GUI-receive timestamp**.
   - If `MpuSample` already has a timestamp field, *do not overwrite it* – add a new attribute for GUI receive time.
   - Use `time.perf_counter()` for high-resolution timing.

2. **At sample reception in the GUI**, set `sample.gui_receive_ts` (or similar).

3. **In `SignalPlotWidget.redraw()`**, when you draw the latest data, compute the latency between “now” and the latest sample’s `gui_receive_ts` and record it via `PlotPerfStats.record_latency()`.

4. Ensure that when metrics are disabled (`ENABLE_PLOT_PERF_METRICS = False`), any extra work is skipped.

---

## Implementation details

1. **Add timestamp at GUI reception**:

Locate the method that first receives `MpuSample` on the GUI thread, e.g.:

```python
class SignalsTab(QtWidgets.QWidget):
    # ...

    @QtCore.Slot(MpuSample)
    def handle_sample(self, sample: MpuSample) -> None:
        # existing behavior: append to buffers, update recorder, etc.
        ...
```

Modify it:

```python
import time
from .config import ENABLE_PLOT_PERF_METRICS

class SignalsTab(QtWidgets.QWidget):
    # ...

    @QtCore.Slot(MpuSample)
    def handle_sample(self, sample: MpuSample) -> None:
        if ENABLE_PLOT_PERF_METRICS:
            # Attach a GUI receive timestamp (on Python object, dynamic attribute is fine)
            try:
                sample.gui_receive_ts = time.perf_counter()
            except Exception:
                # If sample is a namedtuple / immutable, fall back to a side-channel
                pass

        # Existing logic (ensure this still runs)
        self._plot.add_sample(sample)
        # ... any other work ...
```

If `MpuSample` is immutable (e.g. namedtuple or dataclass with `frozen=True`), instead maintain a small side-channel mapping in `SignalsTab` keyed by an increasing sequence number or object id. For example:

```python
self._sample_ts: Deque[float] = deque(maxlen=10000)

# When receiving:
if ENABLE_PLOT_PERF_METRICS:
    self._sample_ts.append(time.perf_counter())
```

We’ll then only measure latency to “latest sample” rather than per-sample mapping. For an incremental implementation, **it’s acceptable to only track latency for the most recent sample visible**.

2. **Expose latest sample timestamp to the plot widget**:

If you can attach `gui_receive_ts` to the sample and the plot widget stores the samples (or their timestamps) in its buffers, the simplest is to keep the timestamp with the time-series.

For example, if `SignalPlotWidget` maintains per-channel deques of `(timestamp, value)` or just `value`, you can adapt it:

```python
class SignalPlotWidget(QtWidgets.QWidget):
    def __init__(...):
        # for each channel:
        self._time_buffers = {...}  # channel -> deque[float]
        self._value_buffers = {...}  # channel -> deque[float]

    def add_sample(self, sample: MpuSample) -> None:
        t_gui = getattr(sample, "gui_receive_ts", None)
        # Use sample sensor timestamp or t_gui as x-axis, depending on your design.
        # But for latency we only need t_gui later.
        # Example: store t_gui in a separate "latest per channel" dict:
        if t_gui is not None:
            self._latest_gui_receive_ts = t_gui

        # existing code that pushes sensor values into buffers...
```

If you don’t want to restructure buffers, a minimal approach is to store a single attribute in `SignalPlotWidget`:

```python
class SignalPlotWidget(QtWidgets.QWidget):
    def __init__(...):
        ...
        self._latest_gui_receive_ts: float | None = None

    def add_sample(self, sample: MpuSample) -> None:
        # called often
        if ENABLE_PLOT_PERF_METRICS:
            t_gui = getattr(sample, "gui_receive_ts", None)
            if t_gui is not None:
                self._latest_gui_receive_ts = t_gui
        # existing logic...
```

3. **Compute and record latency in `redraw()`**:

In `SignalPlotWidget.redraw()`, after you have updated all artists / lines with the latest data but before you call `canvas.draw_idle()`, compute latency:

```python
import time

class SignalPlotWidget(QtWidgets.QWidget):
    # ...

    def redraw(self) -> None:
        # This is called by a QTimer at a fixed refresh rate
        start_ts = time.perf_counter()

        # existing drawing logic: clear axes, update lines, etc.
        # ...
        # self._canvas.draw_idle()

        if ENABLE_PLOT_PERF_METRICS and self._perf:
            end_ts = time.perf_counter()
            # Record frame timing
            self._perf.record_frame(start_ts, end_ts)

            # Record sample-to-draw latency based on latest GUI receive time
            t_gui = getattr(self, "_latest_gui_receive_ts", None)
            if t_gui is not None:
                latency_s = end_ts - t_gui
                # Only record if non-negative and reasonably bounded
                if 0.0 <= latency_s < 60.0:
                    self._perf.record_latency(latency_s)

        self._canvas.draw_idle()
```

Notes:
- We’re using `end_ts` so latency ≈ time at which frame is ready to be drawn vs. when the sample hit the GUI.
- If you want “sensor timestamp → draw” latency instead, you can subtract `sample.sensor_ts` instead, but that requires those timestamps from the backend.

4. **Make sure metrics can be turned off cleanly**:

- Guard all expensive work with `if ENABLE_PLOT_PERF_METRICS:`.
- When disabled, there should be almost zero overhead (no extra attribute lookups or heavy collections).

---

## Output

After this task:

- Each redraw will record:
  - Frame timing into `PlotPerfStats`.
  - An approximate end-to-end latency from last sample arrival to draw.
- `get_perf_snapshot()` will now return non-zero values for FPS and frame durations, and latency fields will be meaningful when data is flowing.
