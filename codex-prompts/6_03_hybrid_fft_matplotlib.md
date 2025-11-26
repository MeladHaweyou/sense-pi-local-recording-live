# Task: Maintain Matplotlib-Based FFTTab in a Hybrid Setup

You are an AI coding assistant working in a PySide6 GUI app that now uses PyQtGraph for time-domain plots, but still uses Matplotlib for FFT plots.

Your job is to ensure that the FFT tab remains Matplotlib-based and continues to work correctly with the new data pipeline, in a hybrid setup.

---

## Goals

1. Keep the existing `FftTab` (or similar) class that uses Matplotlib (`FigureCanvasQTAgg`).
2. Make sure it still pulls data from the same ring buffers used by the new PyQtGraph `SignalPlotWidget`.
3. Maintain the update cadence (for example, update FFT every 0.75 s) via its own QTimer or shared scheduling.
4. Avoid refactoring the FFT code unless strictly necessary for integration.

---

## Integration Notes

- The FFT tab typically:
  - Retrieves a fixed-size window of recent samples from the buffers.
  - Runs `numpy.fft.rfft` or similar.
  - Plots the magnitude spectrum in Matplotlib axes.
- Since FFT updates are infrequent (for example, once every 750 ms), Matplotlib's slower rendering is acceptable.

---

## Example FFTTab Skeleton

Use this example as a reference and align it with your existing code. Do NOT blindly replace; adapt carefully.

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import QTimer

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class FftTab(QWidget):
    def __init__(self, parent=None, *, fft_interval_ms=750):
        super().__init__(parent)

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

        # Reference to the same buffers used by SignalPlotWidget
        self._buffers = None
        self._sensor_ids = []
        self._channel_names = []

        # Matplotlib axes per (sensor, channel)
        self._axes = {}
        self._lines = {}

        self._setup_axes()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update_fft)
        self._timer.start(fft_interval_ms)

    def set_data_buffers(self, buffers, sensor_ids, channel_names):
        """
        Same idea as SignalPlotWidget: inject data source references.
        """
        self._buffers = buffers
        self._sensor_ids = list(sensor_ids)
        self._channel_names = list(channel_names)
        self._setup_axes()

    def _setup_axes(self):
        """
        (Re)build the grid of Matplotlib axes and line objects for FFT plots.
        Call this whenever sensor/channel configuration changes.
        """
        self.figure.clf()
        self._axes.clear()
        self._lines.clear()

        if not self._sensor_ids or not self._channel_names:
            self.canvas.draw_idle()
            return

        n_rows = len(self._sensor_ids)
        n_cols = len(self._channel_names)

        for r, sensor_id in enumerate(self._sensor_ids):
            for c, ch_name in enumerate(self._channel_names):
                idx = r * n_cols + c + 1  # subplot index
                ax = self.figure.add_subplot(n_rows, n_cols, idx)
                ax.set_title(f"{sensor_id} {ch_name}")
                ax.set_xlabel("Frequency [Hz]")
                ax.set_ylabel("Amplitude")
                line, = ax.plot([], [])
                self._axes[(sensor_id, ch_name)] = ax
                self._lines[(sensor_id, ch_name)] = line

        self.figure.tight_layout()
        self.canvas.draw_idle()

    def update_fft(self):
        """
        Compute FFT for each (sensor, channel) from the current buffer content and update plots.
        """
        if self._buffers is None:
            return

        for (sensor_id, ch_name), line in self._lines.items():
            buf = self._buffers.get(sensor_id, {}).get(ch_name)
            if buf is None:
                continue

            # buf.get_y() should return the latest time-domain samples
            # or buf.get_xy() returns (t, y). Adapt to your buffer API.
            t, y = buf.get_xy()
            if y.size < 2:
                line.set_data([], [])
                continue

            # Assuming uniform sampling; compute dt from last two timestamps
            dt = t[1] - t[0]
            fs = 1.0 / dt

            # FFT
            n = y.size
            freqs = np.fft.rfftfreq(n, d=dt)
            fft_vals = np.fft.rfft(y)
            mag = np.abs(fft_vals)

            line.set_data(freqs, mag)

            ax = self._axes[(sensor_id, ch_name)]
            ax.set_xlim(0, fs / 2.0)
            # Optional: auto-y-scale
            ax.relim()
            ax.autoscale_view(scaley=True)

        self.canvas.draw_idle()
```

---

## How to Wire Buffers in MainWindow

In `MainWindow` (or your main controller), you should inject the same buffers into both `SignalPlotWidget` and `FftTab`:

```python
def set_buffer_manager(self, buffer_manager):
    self.buffer_manager = buffer_manager

    buffers = buffer_manager.signal_buffers
    sensor_ids = buffer_manager.sensor_ids
    channel_names = buffer_manager.channel_names

    self.signal_plot_widget.set_data_buffers(buffers, sensor_ids, channel_names)
    self.fft_tab.set_data_buffers(buffers, sensor_ids, channel_names)
```

---

## Acceptance Criteria

- The FFT tab continues to work after moving time-domain plots to PyQtGraph.
- FFT spectra update at the intended interval without noticeably affecting UI responsiveness.
- Both tabs share the same data source (buffers) and show consistent values.

---

## What NOT to Do

- Do not attempt to reimplement FFT tab using PyQtGraph in this task.
- Do not change the FFT computation math (window size, scaling) unless there is a clear bug.
- Do not change the user-facing FFT UI behaviour (sensor/channel layout, labels) unless required for integration.
