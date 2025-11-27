
# Prompt: Tune live FFT windowing and update logic in `FftTab`

You are editing `src/sensepi/gui/tabs/tab_fft.py` to improve **responsiveness and usefulness** of live FFT plots for MPU6050 data.

We already optimized axes/line reuse in another prompt. Here, focus on **windowing strategy and update cadence**.

## Current behaviour (summary)

- Uses a `RingBuffer[(t, value)]` per `(sensor_key, sensor_id, channel)`.
- Window length is selected via `self.window_spin` (0.5–10 s).
- QTimer interval is fixed at 750 ms.
- On each update:
  - Extracts data in last `window_s` seconds.
  - Computes FFT via `compute_fft(signal, sample_rate_hz)`.
  - Plots full spectrum up to Nyquist.

## Goal

Implement a more deliberate strategy:

- Reasonable defaults for FFT window length and update rate.
- Optionally limit max frequency plotted (e.g. to a config value or Nyquist).
- Minimize overhead via small helper functions.

## Tasks for you

1. **Add configuration constants**

   Near the top of `tab_fft.py`, add:

   ```python
   DEFAULT_FFT_WINDOW_S = 2.0
   MIN_FFT_WINDOW_S = 0.5
   MAX_FFT_WINDOW_S = 10.0

   DEFAULT_FFT_UPDATE_MS = 500  # how often to recompute FFT
   MIN_FFT_UPDATE_MS = 200
   MAX_FFT_UPDATE_MS = 2000

   DEFAULT_MAX_FREQUENCY_HZ = 200.0  # cap plotted frequency if useful
   ```

   And use these to initialize `window_spin` and the QTimer interval.

2. **Factor out a helper to extract windowed signal**

   Add a method in `FftTab`:

   ```python
   def _window_signal(
       self,
       buf: RingBuffer[Tuple[float, float]],
       window_s: float,
   ) -> tuple[np.ndarray, np.ndarray, float] | None:
       if len(buf) < 4:
           return None
       points = list(buf)
       t_latest = points[-1][0]
       t_min = t_latest - window_s

       times = [t for (t, _v) in points if t >= t_min]
       values = [v for (t, v) in points if t >= t_min]
       if len(values) < 4 or times[-1] <= times[0]:
           return None

       times_arr = np.asarray(times, dtype=float)
       values_arr = np.asarray(values, dtype=float)

       dt = times_arr[-1] - times_arr[0]
       sample_rate_hz = (len(times_arr) - 1) / dt if dt > 0 else 1.0
       return times_arr, values_arr, sample_rate_hz
   ```

3. **Factor out optional detrend/low-pass**

   Add:

   ```python
   def _preprocess_signal(
       self,
       values: np.ndarray,
       sample_rate_hz: float,
   ) -> np.ndarray:
       signal = values.copy()
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
       return signal
   ```

4. **Limit plotted frequency range**

   - After computing `freqs, mag = compute_fft(signal, sample_rate_hz)`, apply a max frequency cap:

     ```python
     max_f = float(DEFAULT_MAX_FREQUENCY_HZ)
     if freqs.size > 0:
         if max_f > 0.0:
             mask = freqs <= max_f
             freqs = freqs[mask]
             mag = mag[mask]
     ```

   - Use this in both MPU6050 and generic FFT paths.

5. **Use helpers in `_update_mpu6050_fft` and `_update_generic_fft`**

   - Replace inline windowing logic with calls to `_window_signal` and `_preprocess_signal`.
   - Ensure that if `_window_signal` returns `None`, you hide or clear that subplot (but keep axes structure intact if you already implemented caching).

6. **Adjust QTimer interval based on window length (optional)**

   - You can make FFT update interval a function of window length to avoid recomputing too frequently, e.g.:

     ```python
     def _update_fft_timer_interval(self) -> None:
         window_s = float(self.window_spin.value())
         # E.g., update about twice per window
         interval_ms = int(1000.0 * max(MIN_FFT_UPDATE_MS / 1000.0, min(window_s / 2.0, MAX_FFT_UPDATE_MS / 1000.0)))
         self._timer.setInterval(interval_ms)
     ```

   - Connect `window_spin.valueChanged` to `_update_fft_timer_interval`.

## Constraints

- Keep existing public behaviour and UI elements (window_spin, detrend_check, lowpass_check, etc.).
- Integrate smoothly with any axes/line caching refactor you have from the other prompt.

## Deliverables

- Updated `tab_fft.py` with:
  - New constants for window & update configuration.
  - `_window_signal` and `_preprocess_signal` helpers.
  - Frequency cap logic.
  - Slightly smarter QTimer interval management (if implemented).

Produce final code ready to be pasted into `FftTab`, focusing on correct integration with the existing code.
