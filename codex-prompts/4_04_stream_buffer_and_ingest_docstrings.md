# SensePi teaching comments – streaming data buffer & ingest worker

Files:
- `src/sensepi/data/stream_buffer.py`
- `src/sensepi/remote/sensor_ingest_worker.py`
- `src/sensepi/gui/tabs/tab_recorder.py` (for the ingest slot)

The goal is to document how live samples move from the Pi into the shared buffer without blocking the GUI.

## General rules

- Only touch comments and docstrings – no behaviour changes.
- New comments should be 1–3 lines, explaining intent and threading patterns.
- If an explanation already exists, refine it instead of duplicating text.

---

## 1. `StreamingDataBuffer.add_samples` – multi-sensor ring behavior

In `src/sensepi/data/stream_buffer.py`, locate `StreamingDataBuffer.add_samples`:

```python
class StreamingDataBuffer:
    ...
    def add_samples(self, samples: Iterable[MpuSample]) -> None:
        """Append samples to their sensor-specific buffers."""
        for sample in samples:
            if sample is None:
                continue
            sensor_id = self._sensor_key_from_sample(sample)
            buf = self._buffers.setdefault(sensor_id, deque())
            buf.append(sample)
            self._truncate(sensor_id)
```

Edit: Replace the short docstring with this slightly richer explanation:

```python
    def add_samples(self, samples: Iterable[MpuSample]) -> None:
        """Append samples to per-sensor deques, enforcing a sliding time window.

        Each sensor_id gets its own ring-like deque; `_truncate` keeps the
        buffer size bounded so recent data is available without unbounded growth.
        """
        ...
```

Keep the loop logic exactly as it is.

---

## 2. `StreamingDataBuffer.get_recent_samples` – clarify time-window semantics

Find `get_recent_samples` in the same file:

```python
    def get_recent_samples(
        self,
        sensor_id: SensorKey,
        seconds: float | None = None,
        max_samples: int | None = None,
    ) -> List[MpuSample]:
        """Return recent samples for ``sensor_id``."""
        ...
```

Edit: Replace or extend the docstring to explain the cut-off behaviour:

```python
    def get_recent_samples(...):
        """Return recent samples for ``sensor_id`` ordered by time.

        The optional ``seconds`` limit trims older samples using their
        timestamps, while ``max_samples`` caps how many points are returned.
        """
        ...
```

---

## 3. `SensorIngestWorker` – highlight batching and thread usage

In `src/sensepi/remote/sensor_ingest_worker.py` you will find `SensorIngestWorker`:

```python
class SensorIngestWorker(QObject):
    """
    QObject-based worker that pulls data from a PiRecorder stream and batches samples.
    """
    ...
```

Edit: Expand the class docstring as follows:

```python
class SensorIngestWorker(QObject):
    """QObject-based worker that pulls data from a PiRecorder stream and batches samples.

    It is meant to live in its own QThread: lines are parsed in the worker
    thread and emitted as small batches to the GUI via the samples_batch signal.
    """
```

Then in the `start` slot:

```python
    @Slot()
    def start(self) -> None:
        """Entry point for the QThread: consume the remote stream and emit batches."""
        self._running = True
        buffer: list[MpuSample] = []
        last_emit = time.monotonic()
        ...
        for line in lines:
            ...
            buffer.append(sample)
            ...
            should_emit = len(buffer) >= self._batch_size
            if not should_emit and self._max_latency_ms > 0.0:
                should_emit = latency_elapsed >= self._max_latency_ms

            if should_emit and buffer:
                self.samples_batch.emit(list(buffer))
                buffer.clear()
                last_emit = now
```

Edit: Add this 2-line comment immediately before `should_emit = len(buffer) >= self._batch_size`:

```python
            # Emit a batch either when we have enough samples or when the
            # oldest one has been waiting longer than max_latency_ms.
            should_emit = len(buffer) >= self._batch_size
```

---

## 4. `RecorderTab._on_samples_batch` – glue from ingest worker into buffer + queue

In `src/sensepi/gui/tabs/tab_recorder.py`, locate `_on_samples_batch`:

```python
    @Slot(list)
    def _on_samples_batch(self, samples: list[MpuSample]) -> None:
        if not samples:
            return

        self._data_buffer.add_samples(samples)

        rc = self._rate_controllers.get("mpu6050")
        updated_rate = False

        for sample in samples:
            ...
            self._enqueue_sample(sample)

        if rc is not None and updated_rate:
            self.rate_updated.emit("mpu6050", rc.estimated_hz)
```

Edit: Add this short comment just after the `add_samples` call:

```python
        # Store the batch in the shared StreamingDataBuffer (for Signals/FFT)
        # and also push individual samples into the GUI queue for live plots.
```

Place it between `self._data_buffer.add_samples(samples)` and `rc = ...`.

---

After applying these edits, run a quick manual test of live streaming from a Pi
to confirm only comments/docstrings changed.
