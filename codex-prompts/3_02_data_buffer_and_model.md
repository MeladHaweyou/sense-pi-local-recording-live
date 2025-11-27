# Task 2: Implement Central Data Buffer / Ring Buffer Model

You are an expert **Python** and **real-time data processing** engineer working on a PySide6/Qt application.

Your job is to implement a **central data buffer** (ring buffer) that stores recent sensor samples ingested by the new `SensorIngestWorker` (from Task 1), and exposes a clean API for the GUI tabs (`SignalsTab`, `FftTab`) to retrieve data.

The focus is on **integration and structure**, not fancy algorithms.

---

## Context

From Task 1, we now have:

- `SensorIngestWorker` running in a `QThread`.
- It emits `samples_batch` signals with a list of `MpuSample` instances.
- `RecorderTab._on_samples_batch(samples)` is the **single entry point** in the GUI for newly ingested data.

We want:

- A shared data model that **buffers recent samples**.
- Plotting tabs to **pull data** from this model on a fixed timer (not receive per-sample signals).

Sampling characteristics:

- ~200 Hz per channel.
- Typically 3 channels per sensor.
- Typically 3 sensors.
- GUI refresh target: **5–10 Hz** (every 100–200 ms).

---

## Requirements

Implement a small data model (e.g. `DataBuffer` or `StreamingDataModel`) with the following characteristics:

1. **Ring buffer behavior**:
   - Store only the last **N seconds** (e.g. 5–10 seconds) of data per sensor/channel, configurable.
   - When full, old data is discarded (no unbounded growth).
2. **Multi-sensor support**:
   - Store samples keyed by sensor ID and axis/channel if relevant.
   - API should allow retrieving data either:
     - per sensor and channel, or
     - as a single list of samples (depending on how `MpuSample` is structured and how existing plots work).
3. **Main-thread only**:
   - All buffer modifications happen in **Qt main thread** (in `RecorderTab._on_samples_batch`).
   - No direct access from worker threads.
   - This allows simple Python data structures without locks.
4. **Convenient query methods** for plotting:
   - Get last N samples or last T seconds for a given sensor/channel.
   - Optionally: get combined data for all active sensors for SignalsTab/FftTab.

You may place this in a module such as:

- `src/sensepi/data/stream_buffer.py`
- or another appropriate package.

---

## Suggested Data Structures

You can assume `MpuSample` has at least:

- a timestamp (`sample.timestamp` or similar),
- sensor identifier (`sample.sensor_id` or equivalent),
- three axes (`ax`, `ay`, `az`) or similar.

Use `collections.deque` as a ring buffer.

Example design sketch:

```python
# src/sensepi/data/stream_buffer.py

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List, Tuple

from ..models import MpuSample  # adjust to real path


@dataclass
class BufferConfig:
    max_seconds: float = 5.0
    sample_rate_hz: float = 200.0  # per channel
    # Derived max size (per sensor) can be computed from these if desired.


class StreamingDataBuffer:
    """Ring buffer storing recent MpuSample objects for multiple sensors."""

    def __init__(self, config: BufferConfig | None = None) -> None:
        self._config = config or BufferConfig()
        # key: sensor_id (str/int) -> deque[MpuSample]
        self._buffers: Dict[str, Deque[MpuSample]] = {}

    # --- Ingestion API (called from RecorderTab in main thread) ---

    def add_samples(self, samples: Iterable[MpuSample]) -> None:
        for sample in samples:
            sensor_id = self._get_sensor_id(sample)
            buf = self._buffers.setdefault(sensor_id, deque())
            buf.append(sample)
            self._truncate_buffer(buf)

    # --- Query API (called from SignalsTab/FftTab timers in main thread) ---

    def get_recent_samples(self, sensor_id: str, seconds: float | None = None) -> List[MpuSample]:
        """Return samples from the last `seconds` for given sensor.

        If seconds is None, use config.max_seconds.
        """
        if seconds is None:
            seconds = self._config.max_seconds

        buf = self._buffers.get(sensor_id)
        if not buf:
            return []

        # Simple slice-from-the-end approach; optimize if needed.
        threshold_ts = buf[-1].timestamp - seconds
        result: List[MpuSample] = []
        for sample in reversed(buf):
            if sample.timestamp < threshold_ts:
                break
            result.append(sample)
        result.reverse()
        return result

    def get_all_sensor_ids(self) -> List[str]:
        return list(self._buffers.keys())

    # --- Internal helpers ---

    def _get_sensor_id(self, sample: MpuSample) -> str:
        # Adjust to the real attribute on MpuSample
        return str(getattr(sample, "sensor_id", "default"))

    def _truncate_buffer(self, buf: Deque[MpuSample]) -> None:
        # Option 1: size-based truncation using maxlen
        # Option 2: timestamp-based truncation.
        # Start simple: size-based, then optionally improve.
        max_len = int(self._config.max_seconds * self._config.sample_rate_hz) * 2
        while len(buf) > max_len:
            buf.popleft()
```

You may extend this with more convenience methods if needed (for example, per-axis extraction).

---

## Integration with `RecorderTab`

Modify `RecorderTab` so that:

1. It owns a `StreamingDataBuffer` instance, e.g. `self._data_buffer`.
2. The `_on_samples_batch` slot (from Task 1) feeds data into the buffer:

```python
# in RecorderTab.__init__
from sensepi.data.stream_buffer import StreamingDataBuffer, BufferConfig

class RecorderTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data_buffer = StreamingDataBuffer(BufferConfig(
            max_seconds=5.0,
            sample_rate_hz=200.0,
        ))
        # ... rest of init ...

    def _on_samples_batch(self, samples: list[MpuSample]) -> None:
        # Called in main thread via Qt signal
        self._data_buffer.add_samples(samples)
```

3. Expose a **read-only accessor** for the buffer so other tabs can query it:

```python
    def data_buffer(self) -> StreamingDataBuffer:
        return self._data_buffer
```

Later tasks (SignalsTab and FftTab) will call `recorder_tab.data_buffer()` in their timers to fetch the latest samples.

---

## What to Implement

1. Create a `StreamingDataBuffer` (or similarly named) class as a small **in-memory ring buffer** for `MpuSample`.
2. Integrate it into `RecorderTab` so `_on_samples_batch` pushes data into it.
3. Ensure the buffer:
   - does **not** grow without bound,
   - supports multiple sensors,
   - is easy to query from other components.
4. Avoid any cross-thread access: all modifications and reads happen in the **Qt main thread**.

Focus on clear, well-documented APIs so the following tasks can easily use this buffer for plotting and FFT.
