
# Prompt: Add a small GUI overlay to display FPS, latency, CPU%

You now have:

- `SignalPlotWidget.get_perf_snapshot()` returning a dict with:
  - `fps`, `avg_frame_ms`, `avg_latency_ms`, `max_latency_ms`,
  - `target_fps`, `approx_dropped_fps`, etc.
- `SignalsTab.get_perf_snapshot()` optionally enriches this with timer stats.
- A global `ENABLE_PLOT_PERF_METRICS` flag.

We want a **lightweight, optional GUI overlay** that shows:

- FPS and target FPS,
- Average frame time,
- Average & max end-to-end latency,
- CPU usage of the GUI process.

This should be unobtrusive and update about once per second.

---

## Your task

1. **Introduce a small “performance HUD” label overlay** on the plot tab:
   - Implemented as a `QLabel` over the existing layout.
   - Semi-transparent background so it doesn’t fully obscure the plot.
   - Updatable text block.

2. **Add a QTimer (1 Hz) to refresh this label** from `get_perf_snapshot()` and `psutil` CPU stats.

3. **Make it toggleable** via:
   - A checkable QAction (e.g. in a “View → Show Performance HUD” menu), or
   - A toggle button in the tab (e.g. “Show perf stats”).

---

## Implementation details

1. **Install psutil and add CPU usage helper**:

Ensure `psutil` is in your environment, then in a suitable module:

```python
# perf_system.py
import os
import psutil

_process = psutil.Process(os.getpid())

def get_process_cpu_percent() -> float:
    # Note: first call may return 0.0; repeated calls are meaningful
    try:
        return _process.cpu_percent(interval=None)
    except Exception:
        return 0.0
```

2. **Create the HUD label in `SignalsTab` init**:

Assuming `SignalsTab` owns the `SignalPlotWidget` and a layout:

```python
class SignalsTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # existing layout code...

        self._plot = SignalPlotWidget(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._plot)

        # Perf HUD
        self._perf_hud_label = QtWidgets.QLabel(self)
        self._perf_hud_label.setText("")
        self._perf_hud_label.setVisible(False)
        self._perf_hud_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self._perf_hud_label.setMargin(4)

        # Semi-transparent background (using a single-quoted Python string)
        self._perf_hud_label.setStyleSheet(
            "QLabel {"
            "background-color: rgba(0, 0, 0, 150);"
            "color: white;"
            "font-family: monospace;"
            "font-size: 9pt;"
            "}"
        )

        # Use a layout trick or an overlay container; simplest is a QStackedLayout or a custom overlay.
        # Minimal approach: add it to layout and use move() in resizeEvent:
        layout.addWidget(self._perf_hud_label, alignment=QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)

        # 1 Hz timer for HUD updates
        self._perf_hud_timer = QtCore.QTimer(self)
        self._perf_hud_timer.setInterval(1000)
        self._perf_hud_timer.timeout.connect(self._update_perf_hud)
        self._perf_hud_timer.start()
```

3. **Implement `_update_perf_hud`**:

```python
from .config import ENABLE_PLOT_PERF_METRICS
from .perf_system import get_process_cpu_percent

class SignalsTab(QtWidgets.QWidget):
    # ...

    def _update_perf_hud(self) -> None:
        if not self._perf_hud_label.isVisible():
            # Still call cpu_percent so it's primed, but don't build string
            _ = get_process_cpu_percent()
            return

        snap = self.get_perf_snapshot() if ENABLE_PLOT_PERF_METRICS else {}
        cpu = get_process_cpu_percent()

        fps = snap.get("fps", 0.0)
        target_fps = snap.get("target_fps", 0.0)
        avg_frame_ms = snap.get("avg_frame_ms", 0.0)
        avg_latency_ms = snap.get("avg_latency_ms", 0.0)
        max_latency_ms = snap.get("max_latency_ms", 0.0)
        approx_dropped = snap.get("approx_dropped_fps", 0.0)
        timer_hz = snap.get("timer_hz", 0.0)

        text = (
            f"CPU: {cpu:5.1f}%\n"
            f"FPS: {fps:5.1f} / target {target_fps:4.1f}  (timer: {timer_hz:4.1f} Hz)\n"
            f"Frame: {avg_frame_ms:5.1f} ms\n"
            f"Latency: avg {avg_latency_ms:5.1f} ms, max {max_latency_ms:5.1f} ms\n"
            f"Dropped: ~{approx_dropped:4.1f} fps"
        )

        self._perf_hud_label.setText(text)
```

4. **Add a toggle**:

In your main window or tab UI, add a QAction / checkbox to show/hide the HUD.

Example in main window:

```python
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        # existing setup ...

        view_menu = self.menuBar().addMenu("&View")
        self._act_show_perf_hud = QtGui.QAction("Show Performance HUD", self)
        self._act_show_perf_hud.setCheckable(True)
        self._act_show_perf_hud.setChecked(False)
        self._act_show_perf_hud.toggled.connect(self._on_toggle_perf_hud)
        view_menu.addAction(self._act_show_perf_hud)

    def _on_toggle_perf_hud(self, checked: bool) -> None:
        self.signals_tab.set_perf_hud_visible(checked)
```

And in `SignalsTab`:

```python
class SignalsTab(QtWidgets.QWidget):
    # ...

    def set_perf_hud_visible(self, visible: bool) -> None:
        self._perf_hud_label.setVisible(visible)
```

5. **Performance considerations**:

- The HUD update happens once per second; the string build and CPU query overhead is negligible.
- When the HUD is hidden, the timer still runs but `_update_perf_hud` returns quickly.
- Make sure `ENABLE_PLOT_PERF_METRICS` can be false without breaking the HUD (it should simply show zeros or a simpler message).

---

## Output

After this task, when you toggle “Show Performance HUD”:

- A small overlay appears in the plot area.
- It updates once per second with FPS, latency, dropped frames estimate, and CPU%.
- The core drawing performance is unaffected aside from minimal overhead.
