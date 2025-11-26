
# Prompt: Optimize `FftTab` to reuse axes and lines for live FFT

You are editing an existing PySide6 + Matplotlib GUI project (SensePi). The file of interest is:

- `src/sensepi/gui/tabs/tab_fft.py`

This tab displays live FFTs over sliding windows of data from MPU6050 sensors. Right now, the code **clears the entire figure and re-creates axes and lines on each timer tick**, which is expensive.

## Current simplified implementation (excerpt)

```python
class FftTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._buffers: Dict[Tuple[str, int, str], RingBuffer[Tuple[float, float]]] = {}
        self._max_window_seconds = 10.0
        self._max_rate_hz = 500.0
        self._buffer_capacity = max(1, int(self._max_window_seconds * self._max_rate_hz * 2))

        self._figure = Figure(figsize=(5, 3), tight_layout=True)
        self._axes = self._figure.add_subplot(111)
        self._canvas = FigureCanvasQTAgg(self._figure)

        # QTimer
        self._timer = QTimer(self)
        self._timer.setInterval(750)  # ms
        self._timer.timeout.connect(self._update_fft)
        self._timer.start()

    def _update_fft(self) -> None:
        sensor_key = self.sensor_combo.currentData()
        if sensor_key == "mpu6050":
            self._update_mpu6050_fft()
        else:
            self._update_generic_fft()

    def _update_mpu6050_fft(self) -> None:
        view_mode = self.view_mode_combo.currentData()
        if view_mode == "default3":
            channels = ["ax", "ay", "gz"]
        else:
        # ...

        keys = [
            key
            for key in self._buffers.keys()
            if key[0] == "mpu6050" and key[2] in channels and len(self._buffers[key]) > 0
        ]
        sensor_ids = sorted({sensor_id for (_sensor, sensor_id, _ch) in keys})
        if not sensor_ids:
            self._draw_waiting()
            return

        window_s = float(self.window_spin.value())

        self._figure.clear()

        nrows = len(sensor_ids)
        ncols = len(channels)

        subplot_index = 1
        for row_idx, sensor_id in enumerate(sensor_ids):
            for col_idx, ch in enumerate(channels):
                buf = self._buffers.get(("mpu6050", sensor_id, ch))
                ax = self._figure.add_subplot(nrows, ncols, subplot_index)
                subplot_index += 1

                if buf is None or len(buf) < 4:
                    ax.set_visible(False)
                    continue

                points = list(buf)
                # slice window, build arrays, compute FFT
                freqs, mag = compute_fft(signal, sample_rate_hz)
                if freqs.size == 0:
                    ax.setVisible(False)
                    continue

                ax.plot(freqs, mag)
                ax.set_xlim(0.0, freqs[-1])
                # set labels & grid...
        self._figure.tight_layout()
        self._canvas.draw_idle()
```

`_update_generic_fft()` has a similar pattern: clear + new axes + new line each time.

## Goal

Refactor `FftTab` so that:

- Axes and line objects are **created once** (or only when configuration changes).
- On each timer tick, only the data (x/y arrays) are updated.
- We avoid `figure.clear()` and `tight_layout()` on every frame.

Constraints:

- The **grid layout** is determined by:
  - Available `sensor_ids` that have buffer data.
  - Selected channels (via `view_mode_combo`).
- For each subplot: a single line showing the magnitude spectrum.

## Tasks for you

1. Introduce internal caches:
   - `self._fft_axes: Dict[Tuple[int, str], matplotlib.axes.Axes]`
   - `self._fft_lines: Dict[Tuple[int, str], matplotlib.lines.Line2D]`
   - Possibly `self._current_layout: Tuple[Tuple[int, ...], Tuple[str, ...]]` to know when the grid shape changes.

2. Implement a helper `_ensure_fft_layout(sensor_ids, channels)` that:
   - Compares `(tuple(sensor_ids), tuple(channels))` with `self._current_layout`.
   - If different, rebuilds the figure (clear + subplots) once:
     - For each `(sensor_id, channel)`:
       - Create an Axes in the proper row/col.
       - Call `ax.plot([], [], ...)` to create a Line2D.
       - Store in `_fft_axes` and `_fft_lines`.
   - Runs `tight_layout()` once after layout creation.
   - Updates `self._current_layout`.

3. Update `_update_mpu6050_fft` to:
   - Call `_ensure_fft_layout(sensor_ids, channels)` first.
   - For each `(sensor_id, channel)`:
     - Extract the recent window (`window_s`) of points from the `RingBuffer`.
     - Compute FFT and get `freqs, mag`.
     - Use `line = self._fft_lines[(sensor_id, channel)]` and `line.set_data(freqs, mag)`.
     - Update x-limits using `ax.set_xlim(...)` only if needed (e.g. if max frequency changed significantly).
   - Call `self._canvas.draw_idle()` at the end.

4. Update `_update_generic_fft` similarly:
   - Maintain a single axes + line for the first available generic channel.
   - Reuse them on each update.

5. Keep existing public behaviour:
   - `window_spin`, `detrend_check`, `lowpass_check`, and `lowpass_cutoff` still work.
   - `on_stream_started` and `on_stream_stopped` remain the same interface.

6. Implement small internal helper functions where useful, e.g.:
   - `_extract_windowed_signal(buf, window_s) -> (times, values, sample_rate_hz)`
   - `_apply_optional_filters(signal, sample_rate_hz)`

## Deliverables

- A patch to `src/sensepi/gui/tabs/tab_fft.py` that:
  - Adds the layout/line caching described above.
  - Eliminates per-frame `figure.clear()` in the common case.
  - Keeps logic readable and documented with comments.

Produce final code ready to paste into `FftTab` with minimal adjustments.
