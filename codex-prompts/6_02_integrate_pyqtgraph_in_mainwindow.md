# Task: Integrate PyQtGraph `SignalPlotWidget` into MainWindow

You are an AI coding assistant working in a PySide6 GUI application where a `MainWindow` (or similar) hosts the plotting tabs.

You already have a PyQtGraph-based `SignalPlotWidget` implementation (from a previous task).
Now you must replace the Matplotlib-based widget usage in the GUI with the new PyQtGraph version, without breaking the rest of the app.

---

## Goals

1. Use `SignalPlotWidget` (PyQtGraph implementation) in place of the old Matplotlib-based widget in the "Signals" tab or equivalent.
2. Wire it to the existing QTimer or refresh logic so it updates in sync with incoming sensor data.
3. Ensure the data flow from the data acquisition/ring buffer layer into the widget is preserved.

---

## Integration Steps

1. Locate the Signals tab construction:
   - Find where the main window creates and adds the existing `SignalPlotWidget` instance.
   - Example (rough):
     ```python
     self.signal_plot_widget = SignalPlotWidget(parent=self)
     self.signals_tab_layout.addWidget(self.signal_plot_widget)
     ```

2. Confirm the type:
   - Ensure that `SignalPlotWidget` now refers to your PyQtGraph-based class.
     - This may already be true if you replaced the original implementation.
     - If you created `SignalPlotWidgetPG`, you may need to alias:
       ```python
       from .signal_plot_pg import SignalPlotWidgetPG as SignalPlotWidget
       ```

3. Wire in data buffers:
   - Identify the object that owns the ring buffers or data model (for example `self.buffer_manager`).
   - Call `set_data_buffers(...)` on `SignalPlotWidget` from `MainWindow` after buffers are created or updated.

   Example pattern:
   ```python
   # after your data acquisition / buffer manager is set up
   self.signal_plot_widget.set_data_buffers(
       buffers=self.buffer_manager.signal_buffers,  # dict-like: sensor_id -> channel -> buffer
       sensor_ids=self.buffer_manager.sensor_ids,
       channel_names=self.buffer_manager.channel_names,
   )
   ```

4. Connect QTimer for regular updates:
   - Ensure there is a `QTimer` in the main window that periodically calls a method like `update_signal_plots()`.
   - Inside that method, call `self.signal_plot_widget.redraw()`.
   - If timer does not exist yet, create it.

---

## Example Code Snippets

### Create and embed the widget

```python
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from PySide6.QtCore import QTimer

from .signal_plot_widget import SignalPlotWidget  # PyQtGraph-based

class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Central widget and layout
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Create SignalPlotWidget for the "Signals" tab or main area
        self.signal_plot_widget = SignalPlotWidget(self)
        layout.addWidget(self.signal_plot_widget)

        # Data / buffers (example field names; adapt to your app)
        self.buffer_manager = None  # will be injected later

        # QTimer for periodic redraw
        self._signal_timer = QTimer(self)
        self._signal_timer.timeout.connect(self.update_signal_plots)
        self._signal_timer.start(50)  # for example, 50 ms => 20 FPS. Make configurable.

    def set_buffer_manager(self, buffer_manager):
        """
        Called from app bootstrap once the data acquisition/buffer layer is ready.
        """
        self.buffer_manager = buffer_manager

        # Assume buffer_manager has .signal_buffers, .sensor_ids, .channel_names
        self.signal_plot_widget.set_data_buffers(
            buffers=self.buffer_manager.signal_buffers,
            sensor_ids=self.buffer_manager.sensor_ids,
            channel_names=self.buffer_manager.channel_names,
        )

    def update_signal_plots(self):
        """
        Called by QTimer; delegates to the PyQtGraph-based widget.
        """
        if self.buffer_manager is None:
            return

        self.signal_plot_widget.redraw()
```

### Hooking up channel visibility controls

If the UI has checkboxes or menu entries to toggle channels on or off, call `set_visible_channels` on the widget when those change:

```python
def on_channel_visibility_changed(self):
    visible = []  # list of (sensor_id, channel_name)
    for sensor_id in self.buffer_manager.sensor_ids:
        for ch_name in self.buffer_manager.channel_names:
            checkbox = self._channel_checkbox_map[(sensor_id, ch_name)]
            if checkbox.isChecked():
                visible.append((sensor_id, ch_name))

    self.signal_plot_widget.set_visible_channels(visible)
```

---

## Acceptance Criteria

- The "Signals" tab (or equivalent) now uses the PyQtGraph-based `SignalPlotWidget`.
- Plots update smoothly at the configured timer rate.
- No other part of the app needs to be changed (for example, call sites still use `SignalPlotWidget`).
- Channel visibility toggles, sensor selection, etc., still function as before.

---

## What NOT to Do

- Do not change the data acquisition threads or SSH streaming logic.
- Do not introduce new timers in random places; use a single, centralized QTimer for signal updating.
- Do not re-implement FFT or other tabs in this task; focus only on integrating the PyQtGraph time-domain widget.
