# Task: Migrate `SignalPlotWidget` to PyQtGraph (Real-Time Time-Domain Plots)

You are an AI coding assistant working inside an existing PySide6 project (SensePi-like).
The current `SignalPlotWidget` uses Matplotlib and is a performance bottleneck.
Your job is to reimplement it using PyQtGraph while preserving the external API so other parts of the app do not break.

---

## Goals

1. Replace the Matplotlib-based implementation of `SignalPlotWidget` with a PyQtGraph-based one.
2. Keep the public interface identical (methods, signals, constructor signature).
3. Use `GraphicsLayoutWidget` + `PlotItem` + `PlotDataItem` to build a grid of subplots:
   - Up to 3 sensors x 6 channels = 18 plots.
4. Use `setData()` to update line data efficiently.
5. Support a fixed rolling time window (for example, last 10 seconds) per channel.

---

## Integration Constraints

- Do NOT change call sites that reference `SignalPlotWidget`:
  - Keep the same constructor parameters.
  - Keep public methods like (examples) `set_buffers(...)`, `set_visible_channels(...)`, `redraw()` or similar.
- Assume ring buffers or similar data providers already exist and provide NumPy arrays `(t, y)` for each sensor/channel.
- All updates must happen on the Qt main thread.
- Layout: use `QVBoxLayout` (or the existing layout) to embed the new PyQtGraph widget.

---

## Implementation Steps

1. Locate the existing widget:
   - Find the current `SignalPlotWidget` class (Matplotlib-based).
   - Identify its public API: constructor, update methods, any signals emitted.

2. Create a new implementation:
   - Option A: Replace the body of `SignalPlotWidget` with a PyQtGraph version.
   - Option B: Create `SignalPlotWidgetPG` and then alias `SignalPlotWidget = SignalPlotWidgetPG` to keep imports unchanged.

3. Embed PyQtGraph:
   - Use `pyqtgraph.GraphicsLayoutWidget` as the main plotting area.
   - Add it to the widget's layout (for example, `QVBoxLayout`).

4. Create plot grid:
   - For each sensor row and channel column, create a `PlotItem` with `addPlot(row=row_idx, col=col_idx)`.
   - For each plot, create a `PlotDataItem` and store references in a dictionary keyed by `(sensor_id, channel_name)`.

5. Update logic:
   - Implement or update `redraw()` (or equivalent) to:
     - Pull the time/value arrays for each channel from ring buffers.
     - Call `line.setData(t, y)` for each `PlotDataItem`.
   - Ensure the X-axis shows only the last N seconds (for example, 10 seconds):
     - Either slice the arrays before `setData` or set manual X range on the `PlotItem`.

---

## Important Code Skeleton

Use this as a strong starting point and adapt it to the actual project structure and names.

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout
import pyqtgraph as pg
from pyqtgraph import GraphicsLayoutWidget

class SignalPlotWidget(QWidget):
    """
    PyQtGraph-based replacement for the previous Matplotlib-based SignalPlotWidget.
    Public API must remain compatible with existing call sites.
    """
    def __init__(self, parent=None, *, max_sensors=3, max_channels=6, time_window_s=10.0):
        super().__init__(parent)
        self._max_sensors = max_sensors
        self._max_channels = max_channels
        self._time_window_s = time_window_s

        # Data source injected from outside (for example, ring buffer manager)
        # Expect something like: self._buffers[sensor_id][channel_name] -> buffer with get_xy()
        self._buffers = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._glw = GraphicsLayoutWidget()
        layout.addWidget(self._glw)

        # Dicts: (sensor_id, channel_name) -> PlotItem / PlotDataItem
        self._plots = {}
        self._lines = {}

        self._setup_plots()

    def _setup_plots(self):
        """
        Create the grid of PlotItems and PlotDataItems.
        Adapt sensor IDs and channel names to your project's conventions.
        """
        self._glw.clear()
        self._plots.clear()
        self._lines.clear()

        # Example assumptions - you must adapt to real IDs and channel names.
        # For example, maybe sensor_ids = ["S1", "S2", "S3"]
        # and channel_names = ["ax", "ay", "az", "gx", "gy", "gz"]
        sensor_ids = getattr(self, "_sensor_ids", [0, 1, 2])[:self._max_sensors]
        channel_names = getattr(self, "_channel_names", list(range(self._max_channels)))

        for row, sensor_id in enumerate(sensor_ids):
            for col, ch_name in enumerate(channel_names):
                plot = self._glw.addPlot(row=row, col=col)
                plot.showGrid(x=True, y=True)
                plot.setLabel("left", f"{sensor_id} {ch_name}")
                plot.setLabel("bottom", "Time", units="s")

                # Create the line item
                line = plot.plot([], [], pen=pg.mkPen(width=1))
                self._plots[(sensor_id, ch_name)] = plot
                self._lines[(sensor_id, ch_name)] = line

    def set_data_buffers(self, buffers, sensor_ids, channel_names):
        """
        Inject the ring buffer manager / data structure.

        `buffers` should be indexable like buffers[sensor_id][channel_name].get_xy()
        where get_xy() returns (t: np.ndarray, y: np.ndarray).
        """
        self._buffers = buffers
        self._sensor_ids = list(sensor_ids)
        self._channel_names = list(channel_names)
        self._setup_plots()

    def set_visible_channels(self, visible_channels):
        """
        Optional: visible_channels is an iterable of (sensor_id, channel_name) that should be shown.
        Others can be hidden using PlotDataItem.setVisible(False).
        """
        for key, line in self._lines.items():
            line.setVisible(key in visible_channels)

    def redraw(self):
        """
        Called by a QTimer in the main window to update all plots from current buffers.
        """
        if self._buffers is None:
            return

        for (sensor_id, ch_name), line in self._lines.items():
            buf = self._buffers.get(sensor_id, {}).get(ch_name)
            if buf is None:
                continue

            # Expect buf.get_xy() -> (t, y) NumPy arrays
            t, y = buf.get_xy()

            if t.size == 0:
                line.setData([], [])
                continue

            # Enforce rolling window in time
            t_max = t[-1]
            t_min = max(t_max - self._time_window_s, t[0])
            mask = t >= t_min
            t_win = t[mask]
            y_win = y[mask]

            line.setData(t_win, y_win)

            # Optional: set fixed X range for consistent scrolling behaviour
            plot = self._plots[(sensor_id, ch_name)]
            plot.setXRange(t_min, t_min + self._time_window_s, padding=0.0)
```

---

## Acceptance Criteria

- The application compiles and runs without changing any code that uses `SignalPlotWidget`.
- Live time-domain plots are smooth and responsive at high refresh rates (for example, 20 to 50 ms timer).
- CPU usage for plotting is significantly lower than with the Matplotlib-based implementation.
- Changing the visible sensors/channels still works as before (via the public API).

---

## What NOT to Do

- Do not modify unrelated widgets or business logic.
- Do not remove or change the ring buffer logic; only consume it.
- Do not introduce threading in the plotting layer; keep all UI operations in the main thread.
