
# Prompt: Implement Decimation and Smoothing Module for SensePi

You are an AI coding assistant helping to implement a **decimation and smoothing module** for a Raspberry Pi Zero 2–based sensor system (SensePi).

## System Context

- Hardware: Raspberry Pi Zero 2 WH (1GHz Quad-Core, 512MB RAM).
- Sensors: High-rate IMU (accelerometer/gyroscope) at **500–1000 Hz**.
- Existing architecture:
  - A **ring buffer** that stores recent raw sensor samples at full rate.
  - Separate **recording**, **streaming**, and **plotting** paths.
- Plot refresh rate: **20–60 Hz** (typically ~50 Hz).
- Goal: Provide a **clean API** to convert high-rate raw samples into plot-ready data with:
  - Proper **decimation** (downsampling),
  - **Anti-aliasing** low-pass filtering,
  - Optional **min/max envelopes** for spike visibility.

Assume:
- Python 3.9+
- NumPy is available.
- Matplotlib and GUI integration are handled in a separate module.

## Your Tasks

1. Implement a small Python module, e.g. `decimation.py`, with:
   - A `Decimator` class that:
     - Accepts parameters: `sensor_fs`, `plot_fs`, `use_envelope: bool`, `window_mode: str` (`"block"` or `"sliding"`).
     - Computes and stores a **decimation factor** `D = int(sensor_fs / plot_fs)`.
     - Exposes a method to feed new high-rate samples and produce decimated outputs.
   - The API should support:
     - **Non-overlapping blocks** (simple decimation).
     - Optional **sliding window** mode (for smoother behavior).

2. Expose a function (or method) that, given a 1D numpy array of raw samples, returns:
   - `t_decimated`: times for each decimated interval.
   - `y_mean`: mean per interval.
   - Optionally, `y_min`, `y_max` if `use_envelope=True`.

3. Include a **lightweight IIR low-pass filter** option (first-order exponential smoothing) that can be applied sample-by-sample, with configurable `alpha`.

4. Pay attention to:
   - **CPU efficiency** on the Pi.
   - The ability to **run in real-time**: all operations for one plot interval must be fast.
   - Avoid unnecessary allocations in tight loops.

## Important Implementation Snippets and Structure

Use the following skeletons and extend them, focusing on integration and robustness (add docstrings, type hints, error checks):

```python
# decimation.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple, Iterable
import numpy as np

@dataclass
class DecimationConfig:
    sensor_fs: float          # e.g. 500.0 or 1000.0
    plot_fs: float            # e.g. 50.0
    use_envelope: bool = True
    window_mode: str = "block"  # "block" or "sliding"
    smoothing_alpha: Optional[float] = None  # for IIR low-pass, e.g. 0.2

    def decimation_factor(self) -> int:
        D = int(self.sensor_fs / self.plot_fs)
        if D <= 0:
            raise ValueError(f"Invalid decimation factor: {D}")
        return D

@dataclass
class Decimator:
    config: DecimationConfig
    _buffer: np.ndarray = field(init=False)
    _idx: int = field(init=False, default=0)
    _y_lp: Optional[float] = field(init=False, default=None)  # for IIR

    def __post_init__(self) -> None:
        D = self.config.decimation_factor()
        self._buffer = np.empty(D, dtype=np.float32)
        self._idx = 0
        if self.config.smoothing_alpha is not None:
            self._y_lp = 0.0

    def reset(self) -> None:
        """Reset internal buffer and filter state."""
        self._idx = 0
        if self._y_lp is not None:
            self._y_lp = 0.0

    def process_block(
        self,
        samples: np.ndarray,
        start_time: float,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]:
        """Decimate a 1D array of samples into plot-ready series.

        Parameters
        ----------
        samples : np.ndarray
            Raw samples at sensor_fs.
        start_time : float
            Time of the first sample in this block (seconds).

        Returns
        -------
        t_dec : np.ndarray
            Timestamps for each decimated interval.
        y_mean : np.ndarray
            Mean value in each interval.
        y_min : Optional[np.ndarray]
            Min in each interval (if use_envelope=True).
        y_max : Optional[np.ndarray]
            Max in each interval (if use_envelope=True).
        """
        # TODO: implement decimation logic (non-overlapping blocks)
        raise NotImplementedError
```

Implement `process_block` such that:

- It computes decimation factor `D = config.decimation_factor()`.
- It reshapes `samples` into shape `(num_blocks, D)` (truncate leftover).
- Computes `mean`, `min`, `max` along axis 1.
- Builds `t_dec` assuming uniform spacing: `t0 + (block_idx + 0.5) * (D / sensor_fs)`.

Example logic for block processing (you can refine & optimize):

```python
def process_block(self, samples: np.ndarray, start_time: float):
    D = self.config.decimation_factor()
    n = len(samples)
    if n < D:
        # Not enough samples for a full block; skip or buffer for next call
        return np.array([]), np.array([]), None, None

    # Truncate to multiple of D
    n_blocks = n // D
    trimmed = samples[:n_blocks * D]
    blocks = trimmed.reshape(n_blocks, D)

    # Basic mean / min / max
    y_mean = blocks.mean(axis=1)
    y_min = blocks.min(axis=1) if self.config.use_envelope else None
    y_max = blocks.max(axis=1) if self.config.use_envelope else None

    # Optional IIR smoothing of mean
    if self.config.smoothing_alpha is not None:
        alpha = self.config.smoothing_alpha
        if self._y_lp is None:
            self._y_lp = float(y_mean[0])
        smoothed = np.empty_like(y_mean)
        y_prev = self._y_lp
        for i, v in enumerate(y_mean):
            y_prev = y_prev + alpha * (v - y_prev)
            smoothed[i] = y_prev
        self._y_lp = float(smoothed[-1])
        y_mean = smoothed

    # Time axis for block centers
    dt = 1.0 / self.config.sensor_fs
    block_duration = D * dt
    t_dec = start_time + (np.arange(n_blocks) + 0.5) * block_duration

    return t_dec, y_mean, y_min, y_max
```

## Integration Notes

- Design the module to be **stateless** at the function level (for batch processing)
  and **stateful** in the `Decimator` class (for streaming / live plots).
- The rest of the system (plotting module) should call `Decimator.process_block`
  at each GUI update, passing the relevant slice of the ring buffer.
- Make sure the module is safe to use from a separate thread (read-only NumPy arrays, no shared mutable global state).

Focus on:
- Clean, documented API.
- Efficient NumPy usage.
- Correct handling of partial blocks and edge cases.
