# Task: Add Configurable Backend Switch (Matplotlib vs PyQtGraph for Signals)

You are an AI coding assistant working on a PySide6 app that historically used Matplotlib for all plots.
The project now has a PyQtGraph-based implementation of the time-domain `SignalPlotWidget`.

Your job is to add a configuration toggle that selects the backend for signal plots:
- `matplotlib` (legacy, slower)
- `pyqtgraph` (new, real-time optimized)

This allows easy fallback and A/B comparison.

---

## Goals

1. Introduce a configuration option (CLI flag, config file, or GUI setting) to choose the signal plotting backend.
2. Instantiate either the Matplotlib-based or PyQtGraph-based `SignalPlotWidget` depending on that setting.
3. Ensure the public API of the two implementations is identical, so `MainWindow` logic remains unchanged.

---

## Implementation Steps

1. Ensure both implementations exist:
   - Matplotlib version: for example `SignalPlotWidgetMatplotlib` (original implementation).
   - PyQtGraph version: `SignalPlotWidgetPyQtGraph` (from earlier tasks).
   - Both must implement the same public methods: for example, `set_data_buffers`, `set_visible_channels`, `redraw`.

2. Create a small factory function:
   - Based on configuration, return an instance of the appropriate class.

3. Wire config source:
   - Could be:
     - Command-line argument: `--signal-backend=matplotlib|pyqtgraph`.
     - Config file entry.
     - GUI option (for example, combo box).
   - For now, assume there is a central `AppConfig` object accessible from `MainWindow`.

4. Use the factory in `MainWindow` instead of directly instantiating the widget.

---

## Example Code Snippets

### Step 1: two implementations (simplified names)

```python
# signal_plot_matplotlib.py
class SignalPlotWidgetMatplotlib(QWidget):
    # Existing implementation (Matplotlib-based)
    ...

# signal_plot_pyqtgraph.py
class SignalPlotWidgetPyQtGraph(QWidget):
    # New, fast implementation (PyQtGraph-based)
    ...
```

### Step 2: Backend selection in config

```python
# config.py (example)
from dataclasses import dataclass

@dataclass
class AppConfig:
    signal_backend: str = "pyqtgraph"  # or "matplotlib"
```

### Step 3: factory function

```python
# plot_factory.py
from .signal_plot_matplotlib import SignalPlotWidgetMatplotlib
from .signal_plot_pyqtgraph import SignalPlotWidgetPyQtGraph

def create_signal_plot_widget(parent, backend: str):
    backend = (backend or "pyqtgraph").lower()
    if backend == "matplotlib":
        return SignalPlotWidgetMatplotlib(parent)
    elif backend == "pyqtgraph":
        return SignalPlotWidgetPyQtGraph(parent)
    else:
        # Fallback to pyqtgraph if unknown
        return SignalPlotWidgetPyQtGraph(parent)
```

### Step 4: use factory from MainWindow

```python
from .config import AppConfig
from .plot_factory import create_signal_plot_widget

class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)

        self.config = config

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Create signal plot widget via factory
        self.signal_plot_widget = create_signal_plot_widget(
            parent=self,
            backend=self.config.signal_backend,
        )
        layout.addWidget(self.signal_plot_widget)

        # Timers and buffer injection as before
        # ...
```

You may need to adapt constructor signatures to match the real code.

---

## Acceptance Criteria

- Changing `AppConfig.signal_backend` switches the implementation used for time-domain plots.
- Both backends work without requiring changes elsewhere in the code (thanks to consistent API).
- The app starts and runs with either backend selected.
- Users can, in principle, test both and compare performance.

---

## What NOT to Do

- Do not duplicate business logic between the two widgets; only the plotting layer should differ.
- Do not modify unrelated tabs (for example, FFT) in this task.
- Do not silently ignore a broken backend; if instantiation fails, log or raise a clear error.
