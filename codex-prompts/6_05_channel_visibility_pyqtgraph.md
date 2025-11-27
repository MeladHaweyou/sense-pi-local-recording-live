# Task: Implement Channel Visibility Control in PyQtGraph Plots

You are an AI coding assistant working on a PySide6 app that uses PyQtGraph for time-domain plots.
The UI has controls (for example, checkboxes or menus) to toggle visibility of each sensor/channel combination.

Your job is to implement show/hide behaviour for PyQtGraph plots based on these controls.

---

## Goals

1. For each `(sensor_id, channel_name)` line in `SignalPlotWidget`, allow toggling visibility without destroying the plot.
2. Integrate with existing UI controls (checkboxes, menu actions, etc.).
3. Preserve performance: avoid recreating PlotItems; just hide/show `PlotDataItem` or entire subplot.

---

## Internal Data Structures

Assume `SignalPlotWidget` maintains:

- `self._lines[(sensor_id, channel_name)] -> PlotDataItem`
- Optionally, `self._plots[(sensor_id, channel_name)] -> PlotItem`

Visibility can be controlled at either level:

- Hide/show only the `PlotDataItem` (keeps axes visible), or
- Hide/show the entire `PlotItem` (for example, `plot.hide()` / `plot.show()`).

Choose whichever matches existing UX (for example, hide just the curve, keep axes visible).

---

## Implementation Steps

1. Extend `SignalPlotWidget` with a method such as:
   ```python
   def set_visible_channels(self, visible_keys: Iterable[tuple]):
       ...
   ```
   where each key is `(sensor_id, channel_name)`.

2. Maintain a visibility set internally:
   ```python
   self._visible_keys = set(visible_keys)
   ```

3. In `set_visible_channels`, iterate over all known keys and toggle visibility:

   - For each key in `self._lines`:
     - `line.setVisible(key in visible_keys)`

4. MainWindow / Controller side:
   - Whenever the user toggles a checkbox/menu for a channel, recompute the list of visible keys and pass it to `SignalPlotWidget.set_visible_channels(...)`.

---

## Example Code Snippets

### In `SignalPlotWidget` (PyQtGraph)

```python
class SignalPlotWidget(QWidget):
    # ... existing __init__, _setup_plots, redraw, etc. ...

    def set_visible_channels(self, visible_keys):
        """
        visible_keys: iterable of (sensor_id, channel_name) pairs that should be visible.
        Others are hidden.
        """
        visible_set = set(visible_keys)

        for key, line in self._lines.items():
            line.setVisible(key in visible_set)

        # Optionally: hide/show whole PlotItem instead of just the line
        # for key, plot in self._plots.items():
        #     plot.setVisible(key in visible_set)
```

### In `MainWindow`: building the visibility list from checkboxes

```python
def on_channel_checkbox_toggled(self, checked: bool, sensor_id, channel_name):
    """
    Slot connected to each checkbox's toggled(bool) signal.
    """
    # Recompute list of visible keys
    visible = []

    for s_id in self.buffer_manager.sensor_ids:
        for ch_name in self.buffer_manager.channel_names:
            cb = self._channel_checkbox_map[(s_id, ch_name)]
            if cb.isChecked():
                visible.append((s_id, ch_name))

    self.signal_plot_widget.set_visible_channels(visible)
```

If your UI uses actions instead of checkboxes, adapt the slot accordingly.

---

## Acceptance Criteria

- Toggling a channel off hides its line from the time-domain plot without affecting others.
- Toggling it back on shows the line again with continuity (no reset of history if buffers still hold data).
- Performance remains good even when toggling channels frequently.

---

## What NOT to Do

- Do not recreate plots or lines on every toggle; use `setVisible()`.
- Do not manipulate the ring buffers themselves for visibility; only the rendering layer should change.
- Do not block the UI thread with heavy recomputation upon toggling; only line visibility should be updated.
