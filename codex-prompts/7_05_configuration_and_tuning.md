
# Prompt: Add Configuration and Tuning for Decimation and Smoothing

You are an AI coding assistant. Your task is to add a **configuration system** and tuning knobs for decimation and smoothing in a SensePi-like project.

## System Context

- Sensors at 500–1000 Hz.
- Plot refresh at 20–60 Hz.
- Modules already implemented:
  - `decimation.Decimator`
  - `envelope_plot` utilities
  - `Pipeline` with `Recorder`, `Streamer`, `Plotter`
  - `LivePlot` for Matplotlib visualization.

We now want:
- A single configuration source (file or object) controlling:
  - Sensor sample rate,
  - Recording enable/disable,
  - Streaming target rate and enable/disable,
  - Plot refresh rate,
  - Smoothing strength (e.g., IIR alpha, window length),
  - Spike threshold,
  - Window duration for plots.

## Your Tasks

1. Create a config dataclass, e.g. `config.py`:

```python
# config.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class SensePiConfig:
    sensor_fs: float = 500.0
    recording_enabled: bool = True

    # Streaming
    streaming_enabled: bool = True
    stream_fs: float = 50.0

    # Plotting
    plotting_enabled: bool = True
    plot_fs: float = 50.0
    plot_window_seconds: float = 10.0

    # Smoothing
    smoothing_alpha: float = 0.2  # IIR low-pass factor for plotting
    use_envelope: bool = True
    spike_threshold: float = 0.5  # units of signal amplitude
```

2. Provide helper functions to construct pipeline components from config:

```python
# wiring.py
from __future__ import annotations
from typing import Optional
from config import SensePiConfig
from pipeline import Pipeline, Recorder, Streamer, Plotter
from decimation import DecimationConfig, Decimator

def build_pipeline(cfg: SensePiConfig) -> Pipeline:
    recorder = Recorder() if cfg.recording_enabled else Recorder()  # possibly no-op implementation

    streamer = Streamer(
        sensor_fs=cfg.sensor_fs,
        stream_fs=cfg.stream_fs,
    ) if cfg.streaming_enabled else Streamer(sensor_fs=cfg.sensor_fs, stream_fs=cfg.stream_fs)  # could be a NullStreamer

    plotter = Plotter(
        sensor_fs=cfg.sensor_fs,
        plot_fs=cfg.plot_fs,
    ) if cfg.plotting_enabled else Plotter(sensor_fs=cfg.sensor_fs, plot_fs=cfg.plot_fs)  # could be a NullPlotter

    return Pipeline(recorder=recorder, streamer=streamer, plotter=plotter)
```

(Improve the above so that disabled components use proper Null-object implementations with empty `handle_samples`.)

3. Ensure that the `Plotter` and `LivePlot` use config values:
   - `plot_fs` for decimation factor,
   - `smoothing_alpha` for IIR low-pass,
   - `use_envelope` for envelope plotting,
   - `spike_threshold` for spike markers,
   - `plot_window_seconds` for time window length.

4. Optionally add **command-line arguments** or a simple **YAML/JSON config file** loader:
   - Example of parsing a YAML file and creating `SensePiConfig` instance.
   - Be lightweight (safe for Pi Zero 2).

5. Document recommended default values, based on human-perception heuristics:
   - `plot_fs` ≈ 50 Hz for smooth motion.
   - `smoothing_alpha` ≈ 0.2 as a good starting point (20–50 ms effective smoothing).
   - `plot_window_seconds` ≈ 5–10 s for typical monitoring.
   - `spike_threshold` tuned per sensor; start with ≈ 3× typical noise std.

## Integration Notes

- Ensure that changing config values does **not** require deep code changes.
- Wherever possible, read the configuration once at startup, then pass it down via constructors.
- Keep the config layer simple and focused on decimation/smoothing/visualization; avoid mixing unrelated settings.

Focus on:
- Clean configuration design.
- Easy tuning of decimation and smoothing parameters.
- Minimal overhead suitable for Raspberry Pi Zero 2.
