# Task: Add Optional Blitting Support for Time-Domain Plots

This is an advanced optimization: use Matplotlib blitting to update only the changing artists instead of redrawing the whole figure.

## Files to Modify

- `src/sensepi/gui/tabs/tab_signals.py`

Assume `SignalPlotWidget` already uses persistent axes and lines, and no longer clears the figure each frame.

---

## Requirements

1. **Add background caching on draw**

   - Connect to the canvas `draw_event` and cache the figure background:
     ```python
     class SignalPlotWidget(...):
         def __init__(self, parent=None):
             ...
             self.bg_cache = None
             self.canvas.mpl_connect("draw_event", self._on_draw)

         def _on_draw(self, event):
             # Cache the full figure background
             self.bg_cache = self.canvas.copy_from_bbox(self.fig.bbox)
     ```

2. **Modify `redraw()` to use blitting when possible**

   - If `self.bg_cache` is available, use `restore_region` + `draw_artist` + `blit`:
     ```python
     def redraw(self):
         # update data first
         for sensor_idx in range(num_sensors):
             for ch_idx in range(num_channels):
                 line = self.lines[sensor_idx][ch_idx]
                 ydata = self._get_window(sensor_idx, ch_idx)
                 line.set_data(self.time_axis, ydata)
                 # optional: update y-limits here (may require full redraw when changed)

         if self.bg_cache is None:
             # Fallback: full redraw
             self.canvas.draw()
             return

         # Blitting path
         self.canvas.restore_region(self.bg_cache)
         for sensor_lines in self.lines:
             for line in sensor_lines:
                 ax = line.axes
                 ax.draw_artist(line)

         self.canvas.blit(self.fig.bbox)
     ```

3. **Handle axis limit changes**

   - If you change any axis limits (e.g. overflow-driven y-autoscale), the cached background becomes invalid.
   - In that case, perform a full `self.canvas.draw()` once, which will trigger `_on_draw` and refresh `self.bg_cache`.
   - You can detect this by having `_update_y_limits()` return a boolean indicating whether limits changed.

4. **Provide a flag to enable/disable blitting**

   - Add a configuration or attribute, e.g. `self.use_blit = True`, so you can easily turn off blitting if it causes issues.

---

## Acceptance Criteria

- When no axis limits change, redraws use blitting and are noticeably faster.
- When axis limits change, a full redraw happens once and blitting resumes afterward.
- The feature can be toggled via a simple attribute or configuration flag.
