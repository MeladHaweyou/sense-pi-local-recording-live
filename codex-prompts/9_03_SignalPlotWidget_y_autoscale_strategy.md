# Task: Implement Overflow-Driven Y-Axis Autoscaling for `SignalPlotWidget`

The user wants mostly fixed y-limits, but they should expand automatically when data exceeds them.

## Files to Modify

- `src/sensepi/gui/tabs/tab_signals.py`

This builds on the refactored `SignalPlotWidget` with persistent lines and buffers.

---

## Requirements

1. **Initial y-limits per channel**

   - When you create each axis in `__init__`, set sensible initial y-limits for that channel.
   - Either use static values (e.g. [-1, 1]) or load from configuration.
   - Store per-axis limits so you can adjust them:
     ```python
     self.initial_ylim = (-1.0, 1.0)
     for row_axes in self.axes:
         for ax in row_axes:
             ax.set_ylim(*self.initial_ylim)
     ```

2. **Overflow-driven autoscale in `redraw()`**

   - For each line, compute min/max of the new y-data (or at least the new sample).
   - If it exceeds +/- some threshold of current limits, expand the limits.
   - Example:
     ```python
     def _update_y_limits(self, ax, ydata, margin_factor=0.1):
         ymin, ymax = ax.get_ylim()
         data_min = float(np.nanmin(ydata))
         data_max = float(np.nanmax(ydata))

         new_ymin, new_ymax = ymin, ymax
         changed = False

         # expand upward
         if data_max > ymax:
             span = max(ymax - ymin, 1e-6)
             new_ymax = data_max + span * margin_factor
             changed = True

         # expand downward
         if data_min < ymin:
             span = max(ymax - ymin, 1e-6)
             new_ymin = data_min - span * margin_factor
             changed = True

         if changed:
             ax.set_ylim(new_ymin, new_ymax)
     ```

   - Call this after `line.set_data(...)` for each axis:
     ```python
     line.set_data(self.time_axis, ydata)
     self._update_y_limits(line.axes, ydata)
     ```

3. **Avoid shrinking limits automatically**

   - Do **not** shrink y-limits when values come back into range.
   - Only expand as needed, unless the user explicitly resets via a control you expose.

4. **Do not use `ax.autoscale()` or `ax.autoscale_view()` per frame**

   - All scaling logic should be manual and minimal, based on min/max of the current window data.

---

## Acceptance Criteria

- Y-limits stay constant while the data stays within initial bounds.
- If the signal spikes beyond current limits, the axis expands once to fit it plus a small margin.
- There is no jittery rescaling or per-frame autoscale overhead.
