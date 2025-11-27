# AI Prompt 05 – FFT Pipeline & Refresh Logic

You are an AI coding assistant working on the **Sensors recording and plotting** project.
Implement the **FFT computation and plotting** pipeline using the existing ring buffers.

## Goals

- Compute a frequency spectrum for each selected sensor axis using a sliding time window (e.g. last 1s of data).
- Update the FFT plot at a **slower rate** than the time-domain plot (e.g. every 500–1000 ms).
- Integrate with PySide6 GUI (separate tab like `FftTab`).

## Constraints & Design

- Use the **same buffers** as time-domain plotting; no extra data acquisition.
- FFT window length: ~1s worth of samples (e.g. if stream_rate_hz = 200, use 200 samples).
- Use `scipy.fft.rfft` or `numpy.fft.rfft` for real-valued signals.
- Frequency axis in Hz: `freqs = np.fft.rfftfreq(N, d=1.0/stream_rate_hz)`.

## Tasks

1. Add a `QTimer` in `FftTab`:
   - Interval around 750 ms (configurable).
2. On each FFT timer tick:
   - Determine `latest_t_ns` for the selected channel(s).
   - Compute `t_start_ns = latest_t_ns - fft_window_s * 1e9` (e.g. `fft_window_s = 1.0`).
   - Retrieve `(ts_ns, vs)` from the corresponding buffer.
   - If not enough points (e.g. < 0.5*expected_samples), skip or show placeholder.
   - Compute FFT magnitudes and update FFT plot lines.
3. Keep CPU usage modest by:
   - Using a single dominant channel for FFT, or a small set of channels.
   - Skipping computation when there is no new data.

## Important Code Skeleton (Python)

```python
import numpy as np
from PySide6.QtCore import QTimer

class FftTab(QWidget):
    def __init__(self, buffers, stream_rate_hz, parent=None):
        super().__init__(parent)
        self.buffers = buffers  # same mapping used by SignalsTab
        self.stream_rate_hz = stream_rate_hz
        self.fft_window_s = 1.0
        self.timer = QTimer(self)
        self.timer.setInterval(750)  # ms
        self.timer.timeout.connect(self.update_fft)
        # init matplotlib axes, line objects, etc.

    def start(self):
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def update_fft(self):
        channel_key = self.get_selected_channel_key()
        buf = self.buffers.get(channel_key)
        if buf is None:
            return

        latest_ns = buf.latest_timestamp_ns()
        if latest_ns is None:
            return

        t_start_ns = latest_ns - int(self.fft_window_s * 1e9)
        ts_ns, vs = buf.get_window(t_start_ns, latest_ns)
        if vs.size < int(0.5 * self.stream_rate_hz * self.fft_window_s):
            # not enough samples yet
            return

        # Resample or assume uniform spacing based on stream_rate_hz
        # Use vs directly if approximate uniform spacing is OK.
        vs_window = vs

        N = vs_window.size
        freqs = np.fft.rfftfreq(N, d=1.0 / self.stream_rate_hz)
        fft_vals = np.fft.rfft(vs_window)
        mags = np.abs(fft_vals)

        self.fft_line.set_data(freqs, mags)
        self.ax.set_xlim(0, self.stream_rate_hz / 2.0)
        self.canvas.draw_idle()
```

## Notes for the AI

- If actual timing gaps are important, you may want to resample to an evenly spaced grid before FFT.
- For most vibration visualization, assuming constant `stream_rate_hz` is adequate.
- Consider log-scale (dB) for magnitude for better visualization if needed.
