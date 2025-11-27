# Task: Centralize and Control Refresh Rate via QTimer

You are an AI coding assistant working in a PySide6 app with live plots (PyQtGraph time-domain, Matplotlib FFT).
Your job is to ensure all live plot updates are driven by QTimer(s) and that the refresh rate can be adjusted via the GUI or config.

---

## Goals

1. Use one QTimer for time-domain plots (PyQtGraph `SignalPlotWidget`).
2. Use a separate or shared timer for FFT updates (Matplotlib `FftTab`), at a slower rate.
3. Allow the user to choose refresh rates (for example, "Low CPU: 250 ms", "Medium: 100 ms", "High: 20 ms") and apply them without restarting the app.
4. Keep all UI updates in the main thread.

---

## Implementation Steps

1. Locate existing timers:
   - Search for `QTimer` usage in the project (especially in `MainWindow` or controller modules).
   - Identify existing `update()` or `redraw()` style methods for plots.

2. Define refresh profiles (optional):
   - Map human-friendly labels to timer intervals:
     ```python
     REFRESH_PROFILES = {
         "Low (CPU friendly)": 250,
         "Medium": 100,
         "High (CPU heavy)": 20,
     }
     ```

3. Create and configure QTimers:
   - In `MainWindow`, define timers as instance attributes.
   - Connect them to the appropriate slots.

4. Wire timers to GUI controls:
   - If you have a combo box or menu for refresh rate, update the timer interval in its slot.

---

## Example Code Snippets

### MainWindow: timers and slots

```python
from PySide6.QtCore import QTimer

REFRESH_PROFILES = {
    "Low (CPU friendly)": 250,
    "Medium": 100,
    "High (CPU heavy)": 20,
}

class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        # ... create widgets, including self.signal_plot_widget and self.fft_tab ...

        # Timer for time-domain signal plots (PyQtGraph)
        self._signal_timer = QTimer(self)
        self._signal_timer.timeout.connect(self.update_signal_plots)
        self._signal_timer.start(REFRESH_PROFILES["Medium"])

        # Timer for FFT plots (Matplotlib), slower
        self._fft_timer = QTimer(self)
        self._fft_timer.timeout.connect(self.update_fft_plots)
        self._fft_timer.start(750)  # ms

    def update_signal_plots(self):
        if getattr(self, "signal_plot_widget", None) is not None:
            self.signal_plot_widget.redraw()

    def update_fft_plots(self):
        if getattr(self, "fft_tab", None) is not None:
            self.fft_tab.update_fft()
```

### GUI Control: refresh rate selector

Assume you have a `QComboBox` named `refreshRateCombo` with the profile labels.

```python
def _init_refresh_rate_combo(self):
    self.refreshRateCombo.clear()
    for label in REFRESH_PROFILES.keys():
        self.refreshRateCombo.addItem(label)
    self.refreshRateCombo.setCurrentText("Medium")
    self.refreshRateCombo.currentTextChanged.connect(self.on_refresh_rate_changed)

def on_refresh_rate_changed(self, profile_label: str):
    interval = REFRESH_PROFILES.get(profile_label, 100)
    self._signal_timer.setInterval(interval)
```

If the FFT refresh rate should also change based on profile, adjust `_fft_timer` as well.

---

## Acceptance Criteria

- Time-domain plots update at the interval indicated in the UI or config.
- Changing the refresh rate in the GUI takes effect immediately without restarting.
- FFT plots continue to update at their configured rate.
- No extra threads are introduced for updating plots; all updates happen via QTimers.

---

## What NOT to Do

- Do not call heavy plotting code directly from worker threads.
- Do not create multiple timers with overlapping responsibilities for the same plot; keep it centralized.
- Do not leave magic numbers in code; define named constants or maps for refresh profiles.
