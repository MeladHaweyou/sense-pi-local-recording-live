# Prompt: Implement GUI-Side Decimation in `SignalsTab` Time-Domain Plots

You are working inside the **SensePi** repository. The goal of this task is to integrate **real-time decimation / downsampling** into the existing time-domain plotting pipeline so that live plots remain smooth and CPU usage stays reasonable at high sample rates and with many channels.

Focus on **integration with the existing architecture**, not redesign:

- Keep using `RecorderTab` for streaming from the Pi.
- Keep using `SignalPlotWidget` + `SignalsTab` for plotting.
- Reuse the existing `RingBuffer`-based storage.
- Do *not* change public Qt signal/slot APIs unless necessary.

Repository layout (relevant bits):

- `src/sensepi/gui/tabs/tab_signals.py` – time-domain live plots (SignalPlotWidget + SignalsTab)
- `src/sensepi/core/ringbuffer.py` – fixed-size ring buffer
- `src/sensepi/sensors/mpu6050.py` – `MpuSample` model
- `src/sensepi/gui/tabs/tab_recorder.py` – streamer that emits `sample_received` and `rate_updated`

## 1. Current code to study

### `SignalPlotWidget` (excerpt)

```python
class SignalPlotWidget(QWidget):
    """
    Matplotlib widget that shows a grid of time‑domain plots:

        - one row per sensor_id
        - one column per channel

    Example with 3 sensors and channels ax, ay, gz:
        3 rows x 3 columns = 9 subplots
    """

    def __init__(self, parent: Optional[QWidget] = None, max_seconds: float = 10.0):
        super().__init__(parent)

        self._max_seconds = float(max_seconds)
        self._max_rate_hz = 500.0
        # key = (sensor_id, channel)  -> RingBuffer[(t, value)]
        self._buffers: Dict[Tuple[int, str], RingBuffer[Tuple[float, float]]] = {}
        self._buffer_capacity = max(1, int(self._max_seconds * self._max_rate_hz))

        # Channels currently visible & their preferred order (columns)
        self._visible_channels: Set[str] = set()
        self._channel_order: list[str] = []

        # Appearance
        self._line_width: float = 0.8  # thinner than Matplotlib default
        ...
```

```python
    def add_sample(self, sample: MpuSample) -> None:
        """Append a sample from the MPU6050 sensor."""
        # Use sensor_id as row index; default to 1 if missing
        sensor_id = int(sample.sensor_id) if sample.sensor_id is not None else 1
        t = (
            float(sample.t_s)
            if sample.t_s is not None
            else sample.timestamp_ns * 1e-9
        )
        for ch in ("ax", "ay", "az", "gx", "gy", "gz"):
            val = getattr(sample, ch, None)
            if val is None:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            if math.isnan(v):
                continue
            self._append_point(sensor_id, ch, t, v)
```

```python
    def redraw(self) -> None:
        """Refresh the Matplotlib plot (intended to be driven by a QTimer)."""
        # Determine which channels are visible (columns)
        visible_channels = [
            ch for ch in self._channel_order if ch in self._visible_channels
        ]
        if not visible_channels:
            self._figure.clear()
            self._canvas.draw_idle()
            return

        # Active buffers that actually have data
        active_buffers = [
            buf
            for (sid, ch), buf in self._buffers.items()
            if ch in visible_channels and len(buf) > 0
        ]
        if not active_buffers:
            self._figure.clear()
            self._canvas.draw_idle()
            return

        # Time window: last max_seconds across all sensors/channels.
        # Clamp to 0 so a fresh stream starts at t = 0 on the x-axis.
        latest = max(buf[-1][0] for buf in active_buffers)
        cutoff = max(0.0, latest - self._max_seconds)

        # Sensor rows
        sensor_ids = sorted(
            {
                sid
                for (sid, ch) in self._buffers.keys()
                if ch in visible_channels
            }
        )
        if not sensor_ids:
            self._figure.clear()
            self._canvas.draw_idle()
            return

        nrows = len(sensor_ids)
        ncols = len(visible_channels)

        self._figure.clear()

        for row_idx, sid in enumerate(sensor_ids):
            for col_idx, ch in enumerate(visible_channels):
                subplot_index = row_idx * ncols + col_idx + 1
                ax = self._figure.add_subplot(nrows, ncols, subplot_index)

                buf = self._buffers.get((sid, ch))
                if buf is None or len(buf) == 0:
                    ax.set_visible(False)
                    continue

                points = [(t, v) for (t, v) in buf if t >= cutoff]
                if not points:
                    ax.set_visible(False)
                    continue

                times = [t - cutoff for (t, v) in points]
                raw_values = [v for (_t, v) in points]

                offset = 0.0
                if self._base_correction_enabled:
                    offset = self._baseline_offsets.get((sid, ch), 0.0)
                values = [v - offset for v in raw_values]

                ax.plot(times, values, linewidth=self._line_width)
                ...
```

Currently, **every point** inside the window is plotted, which can be thousands of points per line when sampling at 200–500 Hz for 10 seconds, across many channels and sensors.

## 2. Task: Add decimation for plotting

Implement **plot-time decimation** so that for each `(sensor_id, channel)`:

- Only up to a configurable maximum number of points per trace are drawn per frame (e.g. 1–2k points).
- For shorter series, use all points.
- For longer series, reduce the number of points using a *simple but robust* strategy that preserves visual shape.

### Requirements

1. **New configuration attributes** on `SignalPlotWidget`:

   - `self._max_points_per_trace: int = 2000` (or similar default).
   - Public setter method:

     ```python
     def set_max_points_per_trace(self, max_points: int) -> None:
         self._max_points_per_trace = max(100, int(max_points))
     ```

   This will allow future UI controls to tweak it, but for now just set a good default.

2. **Helper method for decimation** inside `SignalPlotWidget`:

   Implement a method like:

   ```python
   from typing import Sequence, Tuple

   def _decimate_for_plot(
       self,
       times: Sequence[float],
       values: Sequence[float],
       max_points: int,
   ) -> Tuple[list[float], list[float]]:
       """
       Downsample (times, values) to at most max_points samples, preserving
       the overall shape as much as reasonably possible without heavy CPU.
       """
       ...
   ```

   Suggested algorithm (keep it simple and fast, no heavy dependencies):

   - If `len(times) <= max_points`, return copies unchanged.
   - Else compute a step size `step = len(times) // max_points`.
   - Iterate in chunks of size `step` over the arrays and for each chunk:
     - Option A (recommended): take **min & max** envelope:
       - Find the index of min and max within the chunk and append both points (time & value).
       - This preserves spikes that might be missed by a simple sub-sampling.
     - Option B (fallback if you want simpler): take the middle sample.

   Ensure the output lists are ordered by time.

   Pseudocode suggestion:

   ```python
   if n <= max_points:
       return list(times), list(values)

   step = max(1, n // max_points)
   out_t: list[float] = []
   out_v: list[float] = []

   for start in range(0, n, step):
       end = min(n, start + step)
       chunk_t = times[start:end]
       chunk_v = values[start:end]

       # envelope
       if not chunk_t:
           continue
       min_idx = start + int(np.argmin(chunk_v))
       max_idx = start + int(np.argmax(chunk_v))

       for idx in sorted({min_idx, max_idx}):
           out_t.append(times[idx])
           out_v.append(values[idx])

   return out_t, out_v
   ```

   Use `numpy` if you like, but keep it lightweight (no extra imports beyond what this module already uses or standard `numpy`).

3. **Integrate decimation into `redraw()`**

   In the main loop inside `redraw`, after computing `times` and `values` but **before** calling `ax.plot`, apply the decimator:

   ```python
   times = [t - cutoff for (t, v) in points]
   raw_values = [v for (_t, v) in points]

   offset = 0.0
   if self._base_correction_enabled:
       offset = self._baseline_offsets.get((sid, ch), 0.0)
   values = [v - offset for v in raw_values]

   times_dec, values_dec = self._decimate_for_plot(
       times, values, self._max_points_per_trace
   )

   ax.plot(times_dec, values_dec, linewidth=self._line_width)
   ```

4. **Maintain behaviour and appearance**

   - Do not change the externally visible API of `SignalsTab`.
   - Preserve existing baseline-correction semantics.
   - Keep grid, labels, and layout behaviour unchanged.
   - Ensure no crashes when buffers are short or empty.

5. **Performance considerations**

   - Avoid re-allocating large lists unnecessarily where possible.
   - Do not introduce an O(N²) algorithm; keep it O(N).
   - The decimation should run every redraw, so it must be relatively cheap.

## 3. Acceptance criteria

- With a simulated high-rate stream (e.g. 200–500 Hz) and 10s window, the UI remains responsive and CPU usage noticeably lower than with full plotting.
- The waveforms still visually represent spikes and trends (no flat, misleading lines).
- No regressions when sample rates are low or only a few points are present.
- The code stays idiomatic and consistent with the existing style in `tab_signals.py`.

Please implement these changes directly in `src/sensepi/gui/tabs/tab_signals.py` and add any small helper code needed. Do **not** add new third-party dependencies. 
