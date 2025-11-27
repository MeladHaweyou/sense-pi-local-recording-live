# AI Prompt 03 – RingBuffer Integration & Time Windowing

You are an AI coding assistant working on the **Sensors recording and plotting** project.
Integrate `RingBuffer` usage for **sliding time windows** in the GUI’s plotting layer.

## Goals

- Maintain a rolling window of recent data per channel (e.g. last **10 seconds**).
- Provide efficient access to `(t, value)` pairs within a `[t_start, t_end]` window.
- Ensure memory/cpu usage stays bounded and predictable.

## Constraints & Design

- Use the existing `RingBuffer` class from `src/sensepi/core/ringbuffer.py`.
- Typical max stream rate is ≤ 500 Hz; for 10s you need up to 5000 samples per channel (plus margin).
- Time axis uses **sensor timestamps** (`t_s` in ns) converted to seconds or `float` where needed.

## Tasks

1. Create a helper to **initialize buffers** for expected channels:
   - For each `(sensor_id, channel_name)` combination, create a `RingBuffer` with capacity for at least `time_window_s * max_stream_rate`.
2. Extend `RingBuffer` or wrap it to provide:
   - `append(t_ns, value)`
   - `get_window(t_start_ns, t_end_ns) -> (times_array, values_array)`
   - `latest_timestamp_ns()`
3. Use these buffers in the plot update logic (see Prompt 04) to:
   - Determine `latest_t` across all relevant channels.
   - Compute `cutoff_t = latest_t - window_length_ns`.
   - Plot only data within `[cutoff_t, latest_t]`.

## Important Code Skeleton (Python)

```python
import numpy as np

class TimeSeriesBufferWrapper:
    def __init__(self, capacity):
        self._buf = RingBuffer(capacity=capacity)

    def append(self, t_ns, v):
        # Store as a tuple or two parallel buffers depending on RingBuffer API
        self._buf.append((t_ns, v))

    def get_window(self, t_start_ns, t_end_ns):
        data = self._buf.get_all()   # or similar
        if not data:
            return np.array([]), np.array([])
        ts = np.array([d[0] for d in data])
        vs = np.array([d[1] for d in data])
        mask = (ts >= t_start_ns) & (ts <= t_end_ns)
        return ts[mask], vs[mask]

    def latest_timestamp_ns(self):
        data = self._buf.get_all()
        if not data:
            return None
        return data[-1][0]
```

## Notes for the AI

- Adapt the wrapper to the exact `RingBuffer` API in this project.
- Make `get_window` efficient; if `RingBuffer` already supports slicing by index, use that instead of scanning.
- Time conversion: optionally provide helper `to_seconds(ts_ns)` as `ts_ns / 1e9` for plotting x-axis.
