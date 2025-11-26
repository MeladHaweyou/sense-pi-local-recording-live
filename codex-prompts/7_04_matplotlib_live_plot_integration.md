
# Prompt: Integrate Decimated Data with Matplotlib Live Plot

You are an AI coding assistant. Your task is to integrate the decimation/envelope modules with a **Matplotlib-based live plot** in a SensePi-like GUI.

## System Context

- Raspberry Pi Zero 2.
- High-rate sensor data (500–1000 Hz), decimated internally to ~20–60 Hz.
- A `Plotter` component already exists (from previous prompts) and provides:
  - Decimated timestamps `t_dec`,
  - Mean values `y_mean`,
  - Optional envelope `y_min`, `y_max`.
- You must use **Matplotlib** for plotting (no PyQtGraph, etc., by default).

The GUI should display:
- A scrolling time axis (last N seconds),
- The smoothed mean trace,
- Optional min–max envelope band,
- Optional spike markers.

## Your Tasks

1. Implement a class, e.g. `LivePlot`, that:
   - Owns a Matplotlib `Figure` and `Axes`.
   - Initializes line, envelope, and spike marker artists (using `envelope_plot.py` helpers).
   - Provides a method `update_plot(data_chunk)` that:
     - Appends new decimated data into internal buffers.
     - Keeps only the last `window_seconds` of data.
     - Updates artists and triggers a redraw.

2. Integrate with Matplotlib's animation / timers (choose one):
   - Use `FuncAnimation` with a fixed interval (~20 ms to 50 ms),
   - Or use `FigureCanvas` timer events if embedded in a GUI toolkit.

## Important Code Snippets

Use the following skeleton as a base:

```python
# live_plot.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Deque, Tuple
from collections import deque
import numpy as np
import matplotlib.pyplot as plt

from envelope_plot import init_envelope_plot, update_envelope_plot, update_spike_markers

@dataclass
class LivePlot:
    window_seconds: float = 10.0
    spike_threshold: float = 0.5  # adjust to your signal units

    fig: plt.Figure = field(init=False)
    ax: plt.Axes = field(init=False)
    line = None
    envelope_coll = None
    spike_scatter = None

    # Internal buffers
    _t: Deque[float] = field(init=False, default_factory=deque)
    _y_mean: Deque[float] = field(init=False, default_factory=deque)
    _y_min: Deque[float] = field(init=False, default_factory=deque)
    _y_max: Deque[float] = field(init=False, default_factory=deque)

    def __post_init__(self):
        self.fig, self.ax = plt.subplots()
        self.line, self.envelope_coll = init_envelope_plot(self.ax, color="C0", alpha=0.2)
        self.spike_scatter = self.ax.scatter([], [], s=10, color="red", marker="x")
        self.ax.set_xlabel("Time [s]")
        self.ax.set_ylabel("Sensor value")
        self.ax.grid(True)

    def _trim_window(self):
        if not self._t:
            return
        t_now = self._t[-1]
        t_min = t_now - self.window_seconds
        while self._t and self._t[0] < t_min:
            self._t.popleft()
            self._y_mean.popleft()
            if self._y_min:
                self._y_min.popleft()
                self._y_max.popleft()

    def add_data(
        self,
        t_dec: np.ndarray,
        y_mean: np.ndarray,
        y_min: Optional[np.ndarray],
        y_max: Optional[np.ndarray],
    ):
        # Append new points
        for i, t_val in enumerate(t_dec):
            self._t.append(float(t_val))
            self._y_mean.append(float(y_mean[i]))
            if y_min is not None and y_max is not None:
                self._y_min.append(float(y_min[i]))
                self._y_max.append(float(y_max[i]))
            else:
                # maintain lengths; could also store None
                self._y_min.append(float(y_mean[i]))
                self._y_max.append(float(y_mean[i]))

        # Trim to window
        self._trim_window()

    def redraw(self):
        if not self._t:
            return

        t_arr = np.fromiter(self._t, dtype=float)
        y_mean_arr = np.fromiter(self._y_mean, dtype=float)
        y_min_arr = np.fromiter(self._y_min, dtype=float)
        y_max_arr = np.fromiter(self._y_max, dtype=float)

        # Update mean + envelope
        new_coll = update_envelope_plot(
            self.line,
            self.envelope_coll,
            t_arr,
            y_mean_arr,
            y_min_arr,
            y_max_arr,
        )
        if new_coll is not None:
            self.envelope_coll = new_coll

        # Update spike markers
        from envelope_plot import update_spike_markers
        update_spike_markers(
            self.spike_scatter,
            t_arr,
            y_mean_arr,
            y_max_arr,
            self.spike_threshold,
        )

        # Adjust axes limits
        self.ax.set_xlim(t_arr[0], t_arr[-1])
        # Optional: auto-scale y
        self.ax.set_ylim(y_min_arr.min(), y_max_arr.max())

        self.fig.canvas.draw_idle()
```

3. Provide an example `run_live_plot.py` that demonstrates wiring:

```python
# run_live_plot.py
import time
import numpy as np
import matplotlib.pyplot as plt
from live_plot import LivePlot

def fake_decimated_stream():
    # Example generator producing synthetic data at ~50 Hz
    t = 0.0
    dt = 0.02
    while True:
        t_vals = np.array([t])
        y = np.sin(2 * np.pi * 1.0 * t_vals) + 0.1 * np.random.randn(*t_vals.shape)
        yield t_vals, y, None, None
        t += dt
        time.sleep(dt)

if __name__ == "__main__":
    lp = LivePlot(window_seconds=5.0)
    plt.ion()
    plt.show(block=False)

    stream = fake_decimated_stream()
    try:
        while plt.fignum_exists(lp.fig.number):
            t_dec, y_mean, y_min, y_max = next(stream)
            lp.add_data(t_dec, y_mean, y_min, y_max)
            lp.redraw()
    except KeyboardInterrupt:
        pass
```

## Integration Notes

- When integrating with the real `Plotter` pipeline:
  - `Plotter.handle_samples` should hand off decimated arrays into a thread-safe queue.
  - The GUI loop (similar to `run_live_plot.py`) should pull from that queue and call `lp.add_data(...)`.
- Keep per-frame work light: avoid heavy recomputation or object creation.

Focus on:
- Smooth visual updates at 20–60 Hz.
- Simple, robust code appropriate for a Raspberry Pi Zero 2.
- Clear separation between data acquisition and plotting.
