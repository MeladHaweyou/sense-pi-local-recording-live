
# Prompt: Enforce Separation of Recording, Streaming, and Visual Pipelines

You are an AI coding assistant. Your task is to **refactor and/or design** code to clearly separate:

1. **Recording fidelity**: Raw, full-rate sensor data, stored for later analysis.
2. **Streaming fidelity**: Decimated/filtered data for network transmission (e.g., over SSH or WebSocket).
3. **Visual fidelity**: Smoothed/enveloped data for **on-screen plotting** only.

This is for a SensePi-like project running on a Raspberry Pi Zero 2.

## Goals

- Ensure that:
  - **Recording** always receives **unmodified raw samples** (or as close as possible).
  - **Streaming** and **visualization** tap into the raw data but use their **own decimation and smoothing**.
  - Smoothing/decimation applied for visualization does **not affect** what gets stored or streamed.
- Provide a pipeline structure that is easy to reason about and extend.

## Your Tasks

1. Design a central data dispatcher module (e.g. `pipeline.py`) that:
   - Has one entry point: `on_new_sample(timestamp, value)` for each sensor (or vector).
   - Sends the sample to three independent sub-components:
     - `Recorder` (raw logging),
     - `Streamer` (network output),
     - `Plotter` (visualization).

2. Provide class skeletons and basic implementations:

```python
# pipeline.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Iterable, Tuple
import numpy as np

class SampleSink(Protocol):
    def handle_samples(self, t: np.ndarray, x: np.ndarray) -> None:
        ...

@dataclass
class Recorder(SampleSink):
    """Stores raw samples to disk or large ring buffer."""
    # e.g., file handle or ring buffer reference
    def handle_samples(self, t: np.ndarray, x: np.ndarray) -> None:
        # TODO: write to file / ring buffer without modifying x
        ...

@dataclass
class Streamer(SampleSink):
    """Decimates and sends samples over network (SSH/WebSocket/etc)."""
    sensor_fs: float
    stream_fs: float

    def __post_init__(self) -> None:
        # Initialize a decimator _only_ for streaming
        from decimation import DecimationConfig, Decimator
        cfg = DecimationConfig(sensor_fs=self.sensor_fs,
                               plot_fs=self.stream_fs,
                               use_envelope=False,
                               smoothing_alpha=None)
        self._dec = Decimator(cfg)

    def handle_samples(self, t: np.ndarray, x: np.ndarray) -> None:
        # Apply decimation for streaming
        t_dec, y_mean, _, _ = self._dec.process_block(x, start_time=float(t[0]))
        if t_dec.size == 0:
            return
        # TODO: serialize and send (t_dec, y_mean) over network
        ...

@dataclass
class Plotter(SampleSink):
    """Prepares decimated/smoothed data for live plotting."""
    sensor_fs: float
    plot_fs: float

    def __post_init__(self) -> None:
        from decimation import DecimationConfig, Decimator
        cfg = DecimationConfig(sensor_fs=self.sensor_fs,
                               plot_fs=self.plot_fs,
                               use_envelope=True,
                               smoothing_alpha=0.2)
        self._dec = Decimator(cfg)

    def handle_samples(self, t: np.ndarray, x: np.ndarray) -> None:
        t_dec, y_mean, y_min, y_max = self._dec.process_block(x, start_time=float(t[0]))
        if t_dec.size == 0:
            return
        # TODO: hand off to GUI thread / plotting buffers (thread-safe)
        ...

@dataclass
class Pipeline:
    recorder: Recorder
    streamer: Streamer
    plotter: Plotter

    def handle_samples(self, t: np.ndarray, x: np.ndarray) -> None:
        """Fan out raw samples to all sinks.

        Parameters
        ----------
        t : np.ndarray
            Timestamps at sensor_fs.
        x : np.ndarray
            Raw samples corresponding to t (1D for now).
        """
        # Recorder gets raw data
        self.recorder.handle_samples(t, x)
        # Streaming and plotting operate independently
        self.streamer.handle_samples(t, x)
        self.plotter.handle_samples(t, x)
```

3. Ensure that **Recorder** does not depend on any decimation logic.
   - If necessary, it can write in chunks (e.g. 1-second blocks) for efficiency, but it should not modify or downsample the data.

4. Ensure that **Streamer** and **Plotter** use **separate `Decimator` instances** so that tuning streaming frequency does not affect plotting.

5. Add configuration hooks:
   - A central config object or file that defines:
     - `recording_enabled`,
     - `stream_fs`,
     - `plot_fs`,
     - smoothing parameters, etc.

## Integration Notes

- Threading: actual sensor acquisition may be in one thread, while GUI is in another. Ensure that:
  - `Plotter.handle_samples` pushes data into a thread-safe queue/buffer for the GUI thread to consume.
  - Recorder and Streamer can either run in the same thread (if fast enough) or have their own worker threads.

Focus on:
- Clear separation of concerns.
- Readable, documented pipeline code.
- Keeping raw vs processed data paths clearly distinct.
