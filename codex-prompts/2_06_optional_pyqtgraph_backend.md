
# Prompt (optional): Prototype a PyQtGraph-based SignalPlotWidget for higher FPS

This task is **optional** and is meant for later experimentation.

The current project uses Matplotlib in `SignalPlotWidget` for live plotting. Matplotlib is flexible and good for publication-quality plots, but it can struggle to maintain high FPS with many subplots and frequent updates.

PyQtGraph, built on top of Qt and NumPy, is optimized for real-time plotting and can reach hundreds of FPS on typical desktops.

We want you to **prototype an alternative `SignalPlotWidget` implementation using PyQtGraph**, behind a simple runtime switch, while reusing as much of the existing interface as possible.

---

## Your task

1. **Introduce a configuration flag** (e.g. `PLOT_BACKEND = "mpl"` or `"pyqtgraph"`) in your config module.

2. **Extract an interface for the plot widget** (or simply keep the same public methods) so that the rest of the GUI doesn’t need to know which backend is used:

   - Required methods / attributes:
     - `add_sample(sample: MpuSample) -> None`
     - `redraw() -> None` (even if PyQtGraph doesn’t strictly need it, for symmetry).
     - `set_target_refresh_rate(hz: float | None) -> None`
     - `get_perf_snapshot() -> dict`

3. **Implement `PyQtGraphSignalPlotWidget`**:
   - Use `pyqtgraph.PlotWidget` or `GraphicsLayoutWidget` internally.
   - Create one subplot per channel / sensor as you currently do with Matplotlib.
   - Reuse the existing ring buffers or new `numpy` arrays for the plotted data.
   - Update curves by calling `.setData(x, y)` instead of re-creating plots each frame.

4. **Wire up the backend selection** in `SignalsTab`:
   - If config says `"mpl"`, create the current `SignalPlotWidget`.
   - If `"pyqtgraph"`, create `PyQtGraphSignalPlotWidget` instead.

5. **Ensure the performance metrics are still available**:
   - You can reuse `PlotPerfStats` in the PyQtGraph variant, recording frame times in `redraw()`.
   - Latency measurement logic from previous tasks should be reused.

---

## Implementation sketch

1. **Config flag**:

```python
# config.py
PLOT_BACKEND = "mpl"  # or "pyqtgraph"
```

2. **Backend selection in `SignalsTab`**:

```python
from .config import PLOT_BACKEND

class SignalsTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        if PLOT_BACKEND == "pyqtgraph":
            from .pg_signal_plot_widget import PyQtGraphSignalPlotWidget as PlotWidgetCls
        else:
            from .mpl_signal_plot_widget import MatplotlibSignalPlotWidget as PlotWidgetCls

        self._plot = PlotWidgetCls(self)
        # rest of init...
```

3. **PyQtGraph-based widget** (new file `pg_signal_plot_widget.py`):

```python
# pg_signal_plot_widget.py
from PySide6 import QtWidgets, QtCore
import pyqtgraph as pg
import numpy as np
import time
from collections import deque
from .config import ENABLE_PLOT_PERF_METRICS
from .perf_metrics import PlotPerfStats

class PyQtGraphSignalPlotWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        self._glw = pg.GraphicsLayoutWidget(self)
        layout.addWidget(self._glw)

        self._plots = []   # list[pg.PlotItem]
        self._curves = []  # list[pg.PlotDataItem]

        self._target_refresh_hz = None
        self._perf = PlotPerfStats() if ENABLE_PLOT_PERF_METRICS else None

        # buffers: channel -> deque of (t, value)
        self._buffers = {}  # type: dict[str, deque[tuple[float, float]]]

        # TODO: initialize plots/curves based on current channel configuration / presets
        # Example skeleton:
        for i, channel_name in enumerate(self._initial_channel_list()):
            p = self._glw.addPlot(row=i, col=0, title=channel_name)
            c = p.plot()
            self._plots.append(p)
            self._curves.append(c)
            self._buffers[channel_name] = deque(maxlen=5000)

    def set_target_refresh_rate(self, hz: float | None) -> None:
        self._target_refresh_hz = hz

    def add_sample(self, sample) -> None:
        # Map sample fields to channels; adapt to your actual MpuSample structure
        t_gui = getattr(sample, "gui_receive_ts", time.perf_counter())
        # Example: channels ax/ay/az/gx/gy/gz for sensor 0 only
        values_by_channel = {
            "ax": sample.ax,
            "ay": sample.ay,
            "az": sample.az,
            "gx": sample.gx,
            "gy": sample.gy,
            "gz": sample.gz,
        }
        for ch, v in values_by_channel.items():
            buf = self._buffers[ch]
            buf.append((t_gui, v))
        # Track latest gui_receive_ts for latency
        self._latest_gui_receive_ts = t_gui

    def redraw(self) -> None:
        start_ts = time.perf_counter()
        # Convert buffers to numpy arrays and update curves
        for (ch, curve) in zip(self._buffers.keys(), self._curves):
            buf = self._buffers[ch]
            if not buf:
                continue
            t_arr, v_arr = zip(*buf)
            t_arr = np.asarray(t_arr, dtype=float)
            v_arr = np.asarray(v_arr, dtype=float)
            # Optionally shift t_arr so that x-axis is "seconds ago"
            t_rel = t_arr - t_arr[-1]
            curve.setData(t_rel, v_arr)

        end_ts = time.perf_counter()

        if ENABLE_PLOT_PERF_METRICS and self._perf:
            self._perf.record_frame(start_ts, end_ts)
            t_gui = getattr(self, "_latest_gui_receive_ts", None)
            if t_gui is not None:
                latency_s = end_ts - t_gui
                if 0.0 <= latency_s < 60.0:
                    self._perf.record_latency(latency_s)

    def get_perf_snapshot(self) -> dict:
        if not (ENABLE_PLOT_PERF_METRICS and self._perf):
            return {
                "fps": 0.0,
                "avg_frame_ms": 0.0,
                "avg_latency_ms": 0.0,
                "max_latency_ms": 0.0,
                "target_fps": self._target_refresh_hz or 0.0,
                "approx_dropped_fps": 0.0,
            }

        fps = self._perf.compute_fps()
        target = self._target_refresh_hz or 0.0
        approx_dropped = max(0.0, target - fps) if target > 0 and fps > 0 else 0.0

        return {
            "fps": fps,
            "avg_frame_ms": self._perf.avg_frame_ms(),
            "avg_latency_ms": self._perf.avg_latency_ms(),
            "max_latency_ms": self._perf.max_latency_ms(),
            "target_fps": target,
            "approx_dropped_fps": approx_dropped,
        }

    def _initial_channel_list(self):
        # TODO: derive from your app's channel configuration / presets
        return ["ax", "ay", "az", "gx", "gy", "gz"]
```

4. **Redraw strategy**:

Even though PyQtGraph can update continuously, you’ll still call `.redraw()` from the same QTimer you already have. This keeps the performance metrics consistent across backends.

---

## Output

After implementing this prototype:

- You can toggle backends by setting `PLOT_BACKEND` in `config.py`.
- The rest of the application doesn’t need to care which backend is used.
- You can run your benchmark mode under both backends and compare:
  - FPS,
  - CPU%,
  - Latency,
  - Dropped frame estimates.

This will give you quantitative evidence for how much smoother PyQtGraph is for your workload.
