# Task: Refactor FFT Tab to Use Persistent Axes and Lines

Optimize frequency-domain plotting so FFT plots update in place rather than recreating axes each time.

## Files to Modify

- `src/sensepi/gui/tabs/tab_fft.py`

There is an `_update_mpu6050_fft()` method (and possibly similar ones) that currently:
- Clears the figure or axes.
- Recreates subplots and calls `plot()` anew every update.

---

## Requirements

1. **Create FFT axes and lines in initialization**

   - In the FFT tab class (e.g. `FftTab.__init__` or a setup method), create the figure, canvas, axes, and lines once.
   - Prepare the frequency axis using sampling rate and FFT size:
     ```python
     import numpy as np

     self.fs = mpu6050_sample_rate_hz  # integrate with actual sensor config
     self.fft_size = desired_fft_size   # e.g. 512 or 1024
     self.freqs = np.fft.rfftfreq(self.fft_size, 1.0 / self.fs)

     self.fig = Figure(figsize=(5, 4), dpi=100)
     self.canvas = FigureCanvasQTAgg(self.fig)

     self.fft_axes = [self.fig.add_subplot(1, 3, i + 1) for i in range(num_sensors)]
     self.fft_lines = []

     for ax in self.fft_axes:
         line, = ax.plot(self.freqs, np.zeros_like(self.freqs))
         ax.set_xlim(0, self.freqs[-1])
         ax.set_ylim(0, 1.0)  # temporary; will update based on data
         ax.set_xlabel("Frequency [Hz]")
         self.fft_lines.append(line)
     ```

2. **Compute FFT from existing time-domain buffers**

   - Use the existing signal buffers used by the time-domain widget, or local buffers in the FFT tab.
   - For each sensor, compute the magnitude spectrum for the most recent `fft_size` samples:
     ```python
     def _compute_fft_mag(self, samples: np.ndarray) -> np.ndarray:
         # samples: 1D array length >= self.fft_size
         window = samples[-self.fft_size:]
         fft_vals = np.fft.rfft(window * np.hanning(len(window)))
         mag = np.abs(fft_vals)
         return mag
     ```

3. **Update only y-data in `_update_mpu6050_fft()`**

   - Replace clearing logic with in-place updates:
     ```python
     def _update_mpu6050_fft(self):
         for idx, sensor in enumerate(self.sensors):
             # assume sensor.buffer is a 1D np.array of recent samples
             mag = self._compute_fft_mag(sensor.buffer)
             line = self.fft_lines[idx]
             line.set_ydata(mag)

             ax = self.fft_axes[idx]
             # optional: simple overflow-driven y-limit
             if mag.max() > ax.get_ylim()[1]:
                 ax.set_ylim(top=mag.max() * 1.1)

         self.canvas.draw_idle()
     ```

4. **Avoid `figure.clear()` and `tight_layout()` per update**

   - If you need layout adjustment, call `tight_layout()` once after initializing the axes, not every update.

---

## Acceptance Criteria

- FFT plots update in place without clearing axes.
- The x-axis (frequency) stays fixed; only the spectrum line changes shape.
- Y-limits expand when needed but do not autoscale every frame.
- `_update_mpu6050_fft()` runs quickly enough for real-time use.
