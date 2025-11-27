# Prompt: Implement GUI-Side Decimation and Max-Window Handling in `FftTab`

You are working inside the **SensePi** repository. The goal is to make the live FFT tab more efficient and robust at high data rates by:

1. Ensuring that FFT windows do not grow beyond a reasonable number of samples.
2. Adding decimation before computing the FFT when necessary (for heavy loads).

Focus on **integration with the existing architecture** of `FftTab` and `RingBuffer`.

Relevant files:

- `src/sensepi/gui/tabs/tab_fft.py`
- `src/sensepi/core/ringbuffer.py`

## 1. Current code to study

`FftTab` keeps its own buffers using `RingBuffer[(t, value)]` keyed by `(sensor_key, sensor_id, channel)`:

```python
class FftTab(QWidget):
    """
    Tab that computes a frequency spectrum over a sliding window of
    recent samples from the live stream.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._buffers: Dict[Tuple[str, int, str], RingBuffer[Tuple[float, float]]] = {}
        self._max_window_seconds = 10.0  # longest supported FFT window
        self._max_rate_hz = 500.0
        self._buffer_capacity = max(1, int(self._max_window_seconds * self._max_rate_hz * 2))
        ...
```

Points are appended via `_append_point`:

```python
    def _append_point(
        self, sensor_key: str, sensor_id: int, channel: str, t: float, value: float
    ) -> None:
        key = (sensor_key, sensor_id, channel)
        buf = self._buffers.get(key)
        if buf is None:
            buf = RingBuffer(self._buffer_capacity)
            self._buffers[key] = buf

        buf.append((t, value))
```

The FFT update methods (simplified) are:

```python
    def _update_mpu6050_fft(self) -> None:
        ...
        window_s = float(self.window_spin.value())

        self._figure.clear()

        nrows = len(sensor_ids)
        ncols = len(channels)

        # Stats for status label (take from first populated subplot)
        stats_samples = None
        stats_fs = None

        subplot_index = 1
        for row_idx, sensor_id in enumerate(sensor_ids):
            for col_idx, ch in enumerate(channels):
                buf = self._buffers.get(("mpu6050", sensor_id, ch))
                ax = self._figure.add_subplot(nrows, ncols, subplot_index)
                subplot_index += 1

                if buf is None or len(buf) < 4:
                    ax.setVisible(False)
                    continue

                points = list(buf)
                t_latest = points[-1][0]
                t_min = t_latest - window_s

                times = [t for (t, _v) in points if t >= t_min]
                values = [v for (t, v) in points if t >= t_min]

                if len(values) < 4 or times[-1] == times[0]:
                    ax.setVisible(False)
                    continue

                times_arr = np.asarray(times, dtype=float)
                values_arr = np.asarray(values, dtype=float)

                dt = times_arr[-1] - times_arr[0]
                sample_rate_hz = (len(times_arr) - 1) / dt if dt > 0 else 1.0

                signal = values_arr.copy()

                # Optional detrend / lowpass
                if self.detrend_check.isChecked():
                    signal = filters.detrend(signal)

                if self.lowpass_check.isChecked():
                    cutoff = float(self.lowpass_cutoff.value())
                    nyquist = 0.5 * sample_rate_hz
                    if 0.0 < cutoff < nyquist:
                        signal = filters.butter_lowpass(
                            signal,
                            cutoff_hz=cutoff,
                            sample_rate_hz=sample_rate_hz,
                        )

                freqs, mag = compute_fft(signal, sample_rate_hz)
                if freqs.size == 0:
                    ax.setVisible(False)
                    continue

                ax.plot(freqs, mag)
                ...
```

There is no explicit limit on **how many samples** can go into the FFT. At 500 Hz with a 10 s window, that’s ~5000 samples per channel per sensor; with many sensors and channels, this can become expensive.

## 2. Task A: Max samples per FFT

Introduce a **maximum number of time-domain samples** that will be used for FFT computation per channel per update. Example default: `self._max_fft_samples = 4096`.

### Implementation steps

1. Add new attribute(s) in `__init__`:

   ```python
   self._max_fft_samples = 4096  # or a similar power-of-two default
   ```

   Optionally add a setter if you want configuration later:

   ```python
   def set_max_fft_samples(self, n: int) -> None:
       self._max_fft_samples = max(256, int(n))
   ```

2. In both `_update_mpu6050_fft` and `_update_generic_fft`, after computing `times_arr` / `values_arr` and before filtering/detrending, **limit** input length:

   - If `len(values_arr) > self._max_fft_samples`:
     - Keep only the **most recent** `self._max_fft_samples` samples (the tail of the arrays).
     - Slice `times_arr` and `values_arr` accordingly.

   Example:

   ```python
   if values_arr.size > self._max_fft_samples:
       values_arr = values_arr[-self._max_fft_samples:]
       times_arr = times_arr[-self._max_fft_samples:]
   ```

3. Recompute `dt` and `sample_rate_hz` if necessary after slicing, to keep consistency.

## 3. Task B: Optional pre-FFT decimation

Beyond the hard cap, add a **simple decimation** step to reduce data when the sample rate is very high.

### Requirements

1. Create a helper method inside `FftTab`, similar in spirit to the one for `SignalPlotWidget` (but you can keep it simpler):

   ```python
   def _decimate_signal_for_fft(
       self,
       times: np.ndarray,
       values: np.ndarray,
       target_points: int,
   ) -> tuple[np.ndarray, np.ndarray]:
       """
       Downsample times/values to at most target_points while preserving
       overall shape reasonably for FFT (no aliasing-critical guarantees).
       """
       ...
   ```

   Suggested algorithm:

   - If `len(values) <= target_points`, return as-is.
   - Else compute `step = len(values) // target_points` and take every `step` sample (simple sub-sampling is OK here because FFT is already a smoothing / global operation).
   - Ensure at least the last sample is included.

2. Integrate into both `_update_mpu6050_fft` and `_update_generic_fft`:

   - After slicing for `_max_fft_samples` but before detrend/lowpass:
     - Optionally call `_decimate_signal_for_fft` if `values_arr.size` is still large (e.g. > 2k). You can re-use `_max_fft_samples` or introduce a separate `_target_fft_points`.

   Example integration:

   ```python
   # After enforcing self._max_fft_samples
   if values_arr.size > 2000:
       times_arr, values_arr = self._decimate_signal_for_fft(
           times_arr, values_arr, 2000
       )
   ```

3. Keep the rest of the pipeline (detrend, lowpass, `compute_fft`) unchanged.

## 4. Task C: Status label and documentation

1. Currently, `_status_label` shows:

   ```python
   self._status_label.setText(
       f"Window: {window_s:.1f} s, samples: {stats_samples}, fs≈{stats_fs:.1f} Hz"
   )
   ```

   Update the status label to reflect the **actual number of samples used in the FFT** (after slicing / decimation). For example:

   ```python
   self._status_label.setText(
       f"Window: {window_s:.1f} s, FFT samples: {stats_samples}, fs≈{stats_fs:.1f} Hz"
   )
   ```

   Where `stats_samples` is set from the post-decimation array length.

2. Add short comments/docstrings near new attributes and helper(s) explaining that the aim is to keep FFT computations bounded and responsive in a live GUI.

## 5. Acceptance criteria

- At high stream rates and longer windows, the FFT tab remains responsive and CPU usage is significantly lower than with unbounded window lengths.
- The maximum number of samples used per FFT is limited (e.g. <= 4096) and clearly reflected in the status label.
- Frequency-domain plots remain visually reasonable; no obvious artifacts from decimation in typical usage.
- No regressions in low-rate / small-window scenarios.

Please implement all changes in `src/sensepi/gui/tabs/tab_fft.py`. Avoid adding new external dependencies. 
