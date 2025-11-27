# Task: Add Performance Configuration and Limits for Live Plots

Provide configuration points for controlling performance-related parameters and ensure the system stays within reasonable limits.

## Files to Modify

- `src/sensepi/gui/tabs/tab_signals.py`
- `src/sensepi/gui/tabs/tab_fft.py`
- Any central configuration module (if present).

---

## Requirements

1. **Add configuration for update rate and window size**

   - Expose parameters like:
     - `signal_update_hz` (e.g. 50 Hz)
     - `time_window_seconds` (e.g. 2–5 seconds)
     - `fft_update_hz` (can be lower than time-domain)
   - Use these values for QTimer intervals and buffer sizes:
     ```python
     self.signal_update_hz = 50.0
     self.time_window_seconds = 2.0

     interval_ms = int(1000.0 / self.signal_update_hz)
     self.timer = QTimer(self)
     self.timer.setInterval(interval_ms)
     self.timer.timeout.connect(self.redraw)
     ```

2. **Limit number of subplots and lines**

   - For real-time use, enforce an upper bound (e.g. 18 subplots, 1–2 lines each).
   - If the configuration would exceed these limits, log a warning or clamp the values.

3. **Optionally downsample data for plotting**

   - If the internal sampling rate is much higher than the display rate, consider decimation for the plotting path.
   - Example: display at most `max_points_per_line` points:
     ```python
     def _decimate_for_plot(self, ydata, max_points=2000):
         if ydata.size <= max_points:
             return ydata
         factor = int(np.ceil(ydata.size / max_points))
         return ydata[::factor]
     ```

4. **Hook configuration into FFT tab**

   - Use a separate timer or trigger for FFT updates (e.g. 10–20 Hz) to reduce CPU load:
     ```python
     self.fft_update_hz = 20.0
     fft_interval_ms = int(1000.0 / self.fft_update_hz)
     self.fft_timer = QTimer(self)
     self.fft_timer.setInterval(fft_interval_ms)
     self.fft_timer.timeout.connect(self._update_mpu6050_fft)
     ```

---

## Acceptance Criteria

- Update rates and window sizes can be tuned without code changes (via constants or config).
- The number of subplots/lines used for real-time plotting respects defined limits.
- Optional downsampling prevents excessive point counts from degrading performance.
- Time-domain and FFT plots can run at different update rates to balance CPU usage.
