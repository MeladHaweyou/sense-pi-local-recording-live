# Task: Implement Efficient Data Buffering and Time Axis for `SignalPlotWidget`

You will ensure that `SignalPlotWidget` uses a fixed-length rolling buffer and a precomputed time axis.

## Files to Modify

- `src/sensepi/gui/tabs/tab_signals.py`

Use the refactored structure from the previous task (persistent axes and lines).

---

## Requirements

1. **Add rolling buffers per sensor/channel**

   - For each sensor/channel, maintain a fixed-length 1D buffer (e.g. last N samples).
   - You can use NumPy arrays plus an index, or `collections.deque(maxlen=N)`.
   - Example using NumPy ring buffer:
     ```python
     import numpy as np

     self.sample_rate_hz = 200.0
     self.window_seconds = 2.0
     self.window_samples = int(self.sample_rate_hz * self.window_seconds)

     # shape: [num_sensors][num_channels][window_samples]
     self.buffers = np.zeros((num_sensors, num_channels, self.window_samples), dtype=float)
     self.write_index = 0
     ```

2. **Define a static time axis for the window**

   - Precompute time array once (0 .. window_seconds) and reuse:
     ```python
     self.time_axis = np.arange(self.window_samples) / self.sample_rate_hz
     ```

3. **On each update, write new samples into the buffers**

   - Integrate with the existing sensor readout mechanism.
   - Assume you get one new sample per channel per update, or a small block.
   - For a single-sample update:
     ```python
     # inside redraw() before setting line data
     idx = self.write_index % self.window_samples
     for sensor_idx, sensor in enumerate(self.sensors):
         for ch_idx in range(num_channels):
             new_val = sensor.get_latest_sample(ch_idx)
             self.buffers[sensor_idx, ch_idx, idx] = new_val
     self.write_index += 1
     ```

4. **Use the rolling buffer to generate y-data for plotting**

   - Convert the ring buffer into contiguous data for plotting:
     ```python
     def _get_window(self, sensor_idx, ch_idx):
         idx = self.write_index % self.window_samples
         buf = self.buffers[sensor_idx, ch_idx]
         # roll so the newest sample is at the end
         return np.roll(buf, -idx)
     ```

   - In `redraw()`:
     ```python
     for sensor_idx in range(num_sensors):
         for ch_idx in range(num_channels):
             line = self.lines[sensor_idx][ch_idx]
             ydata = self._get_window(sensor_idx, ch_idx)
             line.set_data(self.time_axis, ydata)
     ```

5. **Keep x-axis limits fixed**

   - Set x-limits once after initializing axes:
     ```python
     for row_axes in self.axes:
         for ax in row_axes:
             ax.set_xlim(self.time_axis[0], self.time_axis[-1])
     ```

---

## Acceptance Criteria

- The time-domain plots show a fixed-size sliding window in time (e.g. last 2 seconds).
- New data scrolls smoothly across the plots without re-creating axes.
- The time axis does not jump or rescale each frame.
