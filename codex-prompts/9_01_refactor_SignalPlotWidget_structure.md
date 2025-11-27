# Task: Refactor `SignalPlotWidget` to Use Persistent Axes and Lines

You are editing a PySide6 + Matplotlib project. The goal is to optimize live time-domain plotting.

## Files to Modify

- `src/sensepi/gui/tabs/tab_signals.py`

In this file, there is a `SignalPlotWidget` whose `redraw()` method currently:
- Calls `figure.clear()`
- Recreates subplots and lines on every timer tick

This is too slow. You must refactor it to use persistent axes and `Line2D` objects.

---

## Requirements

1. **Create figure, axes, and lines once in `__init__` (or an init helper)**

   - Do **not** call `figure.clear()` or recreate subplots in `redraw()`.
   - Use a grid like `nrows = 6`, `ncols = 3` (adjust to actual layout):
     ```python
     # inside SignalPlotWidget.__init__
     self.fig = Figure(figsize=(5, 4), dpi=100)
     self.canvas = FigureCanvasQTAgg(self.fig)

     # example: 6 rows (channels) x 3 columns (sensors)
     self.axes = self.fig.subplots(nrows=6, ncols=3, sharex="col")
     self.lines = []  # shape: [sensor_index][channel_index]

     for sensor_idx in range(num_sensors):
         sensor_lines = []
         for ch_idx in range(num_channels):
             ax = self.axes[ch_idx][sensor_idx]
             line, = ax.plot([], [], lw=1)
             sensor_lines.append(line)
         self.lines.append(sensor_lines)
     ```

   - Wire `self.canvas` into the widget layout as it is currently done.

2. **Update data in `redraw()` instead of clearing**

   - Replace the existing `figure.clear()` + replot logic.
   - For each sensor/channel, set the data on the corresponding line:
     ```python
     # inside SignalPlotWidget.redraw()
     # assume: self.time_axis is a 1D np.array of time values
     for sensor_idx, sensor in enumerate(self.sensors):
         for ch_idx in range(num_channels):
             line = self.lines[sensor_idx][ch_idx]
             ydata = sensor.get_recent_samples(ch_idx)  # integrate with existing data source
             line.set_data(self.time_axis, ydata)
     ```

3. **Use `draw_idle()` not a full redraw per call**

   - At the end of `redraw()`:
     ```python
     self.canvas.draw_idle()
     ```

4. **Preserve existing public API and connections**

   - Do not break the places where `SignalPlotWidget` is instantiated or where `redraw()` is connected to a QTimer.
   - Keep constructor parameters and signals the same unless absolutely necessary.

---

## Acceptance Criteria

- `SignalPlotWidget.redraw()` no longer calls `figure.clear()` or recreates subplots/lines.
- All subplots and `Line2D` objects are created only once in initialization.
- The GUI still displays all expected subplots and updates correctly.
- CPU load at 50 Hz update is significantly reduced compared to the old approach.
