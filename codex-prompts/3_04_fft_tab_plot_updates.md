# Task 4: Refactor `FftTab` for Timer-Driven FFT & Plot Updates

You are an expert in **signal processing** and **Qt-based GUI development** (PySide6).

Your job is to refactor `FftTab` so that it:

- Uses a **timer-driven update loop** (e.g. 5–10 Hz).
- Pulls data from the shared `StreamingDataBuffer`.
- Computes an FFT over a configurable time window (e.g. last 1 second of data).
- Updates the FFT plot efficiently.

The focus is on integrating with the existing architecture, not on sophisticated DSP.

---

## Context

We now have:

- `SensorIngestWorker` (QThread) ingesting sensor data and emitting batches.
- `RecorderTab` receiving batches and updating a `StreamingDataBuffer` (`self._data_buffer`).
- `SignalsTab` using a `QTimer` to update time-domain plots from `data_buffer` (Task 3).

Previously, `FftTab` may have been connected directly to per-sample signals from the worker. We want to decouple it from the ingestion thread and instead:

1. Use a **QTimer** to periodically recompute the FFT.
2. Use a **fixed-length window** of recent samples from `StreamingDataBuffer`.

---

## Requirements

1. **Timer Setup**
   - Add a `QTimer` inside `FftTab`.
   - Reasonable default interval: **200 ms** (5 Hz) or **100 ms** (10 Hz), but configurable.
   - Timer is started/stopped based on recording state from `RecorderTab`.

2. **Data Selection**
   - Use `RecorderTab.data_buffer()` to fetch recent samples for a selected sensor.
   - Choose a window length for FFT, e.g. **1.0 second** of data.
   - Handle the case where there is not yet enough data by skipping the update.

3. **FFT Computation**
   - Use **NumPy** (e.g. `numpy.fft.rfft`) for FFT.
   - Compute FFT magnitude (and optionally power) for 1 or more channels.
   - Consider the sampling rate (e.g. 200 Hz) to compute frequency bins.

4. **Plot Update**
   - Reuse existing plotting widgets (Matplotlib or whatever is already used).
   - Do not recreate the figure on each tick; only update data of the relevant curves.
   - Axes: x-axis is frequency (Hz), y-axis is magnitude or power.

---

## Suggested Implementation Sketch

Assume there is a `FftTab` class structured like:

```python
class FftTab(QWidget):
    def __init__(self, recorder_tab: RecorderTab, parent=None):
        super().__init__(parent)
        self._recorder_tab = recorder_tab
        # create figure/canvas here
        self._fft_timer = None
```

### 1. Timer setup

```python
from PySide6.QtCore import QTimer
import numpy as np

class FftTab(QWidget):
    UPDATE_INTERVAL_MS = 200  # 5 Hz by default
    FFT_WINDOW_SECONDS = 1.0  # 1-second window

    def __init__(self, recorder_tab: RecorderTab, parent=None):
        super().__init__(parent)
        self._recorder_tab = recorder_tab

        self._fft_timer = QTimer(self)
        self._fft_timer.setInterval(self.UPDATE_INTERVAL_MS)
        self._fft_timer.timeout.connect(self._on_fft_timer)

        self._init_fft_plot()

        # Wire to recording lifecycle
        self._recorder_tab.recording_started.connect(self.start_updates)
        self._recorder_tab.recording_stopped.connect(self.stop_updates)

    def _init_fft_plot(self) -> None:
        """Set up Matplotlib (or other) figure, axes, and line objects for FFT."""
        # Example: self._fft_axes, self._fft_line = ...
        pass  # adapt to existing code

    def start_updates(self) -> None:
        if not self._fft_timer.isActive():
            self._fft_timer.start()

    def stop_updates(self) -> None:
        if self._fft_timer.isActive():
            self._fft_timer.stop()

    def _on_fft_timer(self) -> None:
        self._update_fft_from_buffer()
```

### 2. Fetch data and compute FFT

```python
    def _update_fft_from_buffer(self) -> None:
        buffer = self._recorder_tab.data_buffer()
        sensor_ids = buffer.get_all_sensor_ids()
        if not sensor_ids:
            return

        sensor_id = sensor_ids[0]  # for now, pick the first; later allow user selection
        samples = buffer.get_recent_samples(sensor_id, seconds=self.FFT_WINDOW_SECONDS)
        if not samples:
            return

        # Assume MpuSample has .ax, .ay, .az and we choose one axis for FFT (e.g. ax)
        # Extract values and ensure we have enough points
        values = np.array([s.ax for s in samples], dtype=float)
        if values.size < 4:
            # Not enough points to compute meaningful FFT
            return

        # Use known sampling rate for frequency axis
        fs = buffer._config.sample_rate_hz  # or expose a getter instead of accessing config directly
        n = values.size
        # Optionally apply windowing (e.g. Hann)
        window = np.hanning(n)
        values_win = values * window

        freqs = np.fft.rfftfreq(n, d=1.0 / fs)
        fft_vals = np.fft.rfft(values_win)
        magnitude = np.abs(fft_vals)

        # Update plot line
        self._fft_line.set_xdata(freqs)
        self._fft_line.set_ydata(magnitude)

        self._fft_axes.relim()
        self._fft_axes.autoscale_view()

        self._canvas.draw_idle()
```

Adapt attribute access (e.g. `.ax`) and the plotting objects to match your existing `FftTab` implementation.

### 3. Handling Multi-Channel / Multi-Sensor FFT

For now, keep it simple:

- Either show FFT for a **single sensor and axis** (e.g. sensor 0, axis X).
- Or, reuse whatever selection mechanism already exists in `FftTab` (dropdowns, radio buttons) to choose which sensor/axis to analyze.

If `FftTab` already has UI elements to select channel/sensor, integrate with those when deciding which data to pull from `StreamingDataBuffer`.

---

## What to Implement

1. Add a **QTimer** in `FftTab` to trigger FFT updates at a fixed rate.
2. Implement `_update_fft_from_buffer` to:
   - Pull recent samples from `RecorderTab.data_buffer()`.
   - Compute FFT using NumPy over the desired window.
   - Update the FFT plot curves efficiently.
3. Wire the timer to recording start/stop signals (or equivalent existing mechanisms).
4. Ensure that `FftTab` no longer depends on per-sample or per-batch signals from the ingestion worker.

Keep the changes focused on:
- integrating with the `StreamingDataBuffer`,
- using timer-driven updates, and
- efficient plotting updates.

Leave advanced DSP or fancy UI controls for future tasks.
