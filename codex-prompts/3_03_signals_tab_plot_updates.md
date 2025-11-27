# Task 3: Refactor `SignalsTab` for Timer-Driven Real-Time Plot Updates

You are an expert in **Qt-based plotting** (PySide6 + Matplotlib or PyQtGraph) and real-time GUI design.

Your job is to refactor `SignalsTab` so that it:

- **No longer receives per-sample signals.**
- **Updates plots on a fixed timer** (e.g. 10 Hz, every 100 ms).
- **Reads data from the central `StreamingDataBuffer`** (implemented in Task 2).

The focus is on **integration and update flow**, not full plotting aesthetics.

---

## Context

We now have:

- A `SensorIngestWorker` running in its own `QThread`, emitting batched `samples_batch` signals.
- `RecorderTab` receives these batches and pushes them into a `StreamingDataBuffer` (`self._data_buffer`).
- `RecorderTab` exposes `data_buffer()` so other tabs can access the buffer.

Previously, `SignalsTab` likely had something like:

- A slot `on_new_sample(MpuSample)` connected directly to the worker thread.
- Each incoming sample was appended to local arrays and the plot was updated frequently.

We want to change this to:

1. **Timer-driven refresh:** a `QTimer` inside `SignalsTab` that fires at a fixed rate (e.g. 10 Hz).
2. On each timer tick, `SignalsTab` **pulls the latest data** from `StreamingDataBuffer` and updates the plot.
3. The plotting backend should be compatible with the existing project (Matplotlib for now, but write code in a way that could later be swapped to PyQtGraph).

---

## Requirements

1. **Timer Setup**
   - Add a `QTimer` in `SignalsTab` to drive updates.
   - Default interval ~100 ms (10 Hz), configurable.
   - Timer should be started when recording is active and stopped when not (based on `RecorderTab` state or explicit methods).

2. **Data Access**
   - `SignalsTab` must have access to:
     - A reference to `RecorderTab` (or directly to the `StreamingDataBuffer`).
   - On each tick, `SignalsTab` queries the buffer for the latest samples per sensor (and per axis if needed).

3. **Plot Update**
   - Reuse existing plotting widgets (Matplotlib canvas) if already set up.
   - **Do not recreate axes/figures** on each update; only update the line data.
   - Use efficient Matplotlib patterns:
     - `line.set_xdata(...)`, `line.set_ydata(...)`
     - followed by `canvas.draw_idle()` or a similar optimized method.
   - Later, this backend can be swapped to PyQtGraph if needed.

4. **Clean Integration**
   - Avoid direct coupling to the worker thread.
   - Keep `SignalsTab` focused on **visualization of the current buffer state**.

---

## Suggested Refactor Sketch

Assume you have a `SignalsTab` class similar to:

```python
class SignalsTab(QWidget):
    def __init__(self, recorder_tab: RecorderTab, parent=None):
        super().__init__(parent)
        self._recorder_tab = recorder_tab
        # set up Matplotlib canvas / axes here
        self._plot_timer = None
```

### 1. Setup the timer

Add a method `_setup_timer` or similar:

```python
from PySide6.QtCore import QTimer

class SignalsTab(QWidget):
    UPDATE_INTERVAL_MS = 100  # 10 Hz

    def __init__(self, recorder_tab: RecorderTab, parent=None):
        super().__init__(parent)
        self._recorder_tab = recorder_tab
        self._plot_timer = QTimer(self)
        self._plot_timer.setInterval(self.UPDATE_INTERVAL_MS)
        self._plot_timer.timeout.connect(self._on_plot_timer)
        # Timer will be started/stopped based on recording state

        self._init_plot()

    def _init_plot(self) -> None:
        """Set up matplotlib figure, axes, and line objects.

        - Create one subplot per channel/sensor, or reuse the existing layout.
        - Store line references in self._lines dict/list.
        """
        pass  # implement using existing plotting code

    def start_updates(self) -> None:
        if not self._plot_timer.isActive():
            self._plot_timer.start()

    def stop_updates(self) -> None:
        if self._plot_timer.isActive():
            self._plot_timer.stop()

    def _on_plot_timer(self) -> None:
        self._update_plots_from_buffer()
```

### 2. Pull data from buffer and update plots

Implement `_update_plots_from_buffer` using the `StreamingDataBuffer`:

```python
    def _update_plots_from_buffer(self) -> None:
        buffer = self._recorder_tab.data_buffer()
        # Example: assume a fixed set of sensor_ids and axes.
        sensor_ids = buffer.get_all_sensor_ids()
        if not sensor_ids:
            return

        # For simplicity, plot the first sensor's 3 axes
        sensor_id = sensor_ids[0]
        samples = buffer.get_recent_samples(sensor_id, seconds=5.0)
        if not samples:
            return

        # Extract time and axes from samples
        t = [s.timestamp for s in samples]
        ax = [s.ax for s in samples]  # adapt to actual attribute names
        ay = [s.ay for s in samples]
        az = [s.az for s in samples]

        # Assume you have 3 line objects: self._line_x, self._line_y, self._line_z
        self._line_x.set_xdata(t)
        self._line_x.set_ydata(ax)
        self._line_y.set_xdata(t)
        self._line_y.set_ydata(ay)
        self._line_z.set_xdata(t)
        self._line_z.set_ydata(az)

        # Adjust axes limits if necessary
        self._axes.relim()
        self._axes.autoscale_view()

        # Efficient redraw
        self._canvas.draw_idle()
```

Adapt the actual line/axes names and layout to **match the existing `SignalsTab` implementation**.

### 3. Connect timer to recording lifecycle

Ensure that the timer is:

- Started when recording is started (e.g. from `RecorderTab` or via a signal).
- Stopped when recording stops.

Example wiring from `RecorderTab`:

```python
class RecorderTab(QWidget):
    recording_started = Signal()
    recording_stopped = Signal()

    def start_recording(self):
        # existing setup + data thread start
        self.recording_started.emit()

    def stop_recording(self):
        # stop worker/thread
        self.recording_stopped.emit()
```

In `SignalsTab`:

```python
class SignalsTab(QWidget):
    def __init__(self, recorder_tab: RecorderTab, parent=None):
        super().__init__(parent)
        self._recorder_tab = recorder_tab
        # ...
        self._recorder_tab.recording_started.connect(self.start_updates)
        self._recorder_tab.recording_stopped.connect(self.stop_updates)
```

If a similar mechanism already exists, adapt to that instead of adding new signals.

---

## What to Implement

1. Introduce a **QTimer-driven update loop** in `SignalsTab` (`_plot_timer`).
2. Make `SignalsTab` pull data from `RecorderTab.data_buffer()` on each timer tick.
3. Update the plot using efficient operations on existing line objects (no re-creation each frame).
4. Ensure that `SignalsTab` reacts appropriately to recording start/stop:
   - Timer starts on recording start.
   - Timer stops on recording stop.

Keep changes **focused on integration** with the new ingestion + buffer model. Do not alter how `SensorIngestWorker` or `StreamingDataBuffer` work beyond what’s necessary to read data.
