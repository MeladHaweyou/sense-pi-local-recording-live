
# Prompt: Introduce queue-based batching between `RecorderTab` and GUI tabs

You are editing the SensePi project. The goal is to **reduce overhead and jitter** from emitting a Qt signal for every single sample.

## Current architecture (simplified)

File: `src/sensepi/gui/tabs/tab_recorder.py`

```python
class RecorderTab(QWidget):
    sample_received = Signal(object)
    streaming_started = Signal()
    streaming_stopped = Signal()
    error_reported = Signal(str)
    rate_updated = Signal(str, float)

    def start_live_stream(self, recording: bool) -> None:
        # ...
        def _worker() -> None:
            try:
                lines = _iter_lines()
                rc = self._rate_controllers[sensor_type]
                rc.reset()

                def _callback(sample: object) -> None:
                    if stop_event.is_set():
                        raise _StopStreaming()
                    t = self._sample_time_seconds(sample)
                    if t is not None:
                        rc.add_sample_time(t)
                        self.rate_updated.emit(sensor_type, rc.estimated_hz)
                    self.sample_received.emit(sample)

                stream_lines(lines, parser, _callback)
                # ...
            except _StopStreaming:
                pass
            # ...
```

`SignalsTab` and `FftTab` connect to `sample_received` and update their ring buffers on each emission.

## Goal

Introduce a **producer–consumer pattern** using a thread-safe queue so that:

- The background thread **pushes samples into a queue**, instead of emitting Qt signals directly.
- A QTimer in the GUI thread periodically **drains the queue** and:
  - Emits a **single batched signal** like `samples_received(list[object])`, or
  - Directly updates the tabs' ring buffers via method calls (preferred).
- `RateController` still receives timestamps, but can optionally be updated based on batches.

The main focus is **integration** with existing classes (RecorderTab, SignalsTab, FftTab, MpuSample).

## Tasks for you

1. In `RecorderTab`:
   - Add a `queue.Queue` instance, e.g.:

     ```python
     import queue

     class RecorderTab(QWidget):
         def __init__(...):
             # ...
             self._sample_queue: "queue.Queue[object]" = queue.Queue(maxsize=10000)
     ```

   - In the background `_worker`:
     - Replace `self.sample_received.emit(sample)` with `self._sample_queue.put(sample, block=False)` (drop or log if full).
     - Keep `RateController` updated based on sample times as now.
   - Option A (cleaner): add a new signal `samples_received = Signal(list)` but we may not need it if tabs read the queue directly.

2. In `SignalsTab`:
   - Add a new QTimer, e.g. `self._ingest_timer`, separate from the plot refresh timer:

     ```python
     self._ingest_timer = QTimer(self)
     self._ingest_timer.setInterval(20)  # every 20 ms, tweakable
     self._ingest_timer.timeout.connect(self._drain_samples)
     self._ingest_timer.start()
     ```

   - Provide a method like `attach_recorder(self, recorder_tab: RecorderTab)` or reuse the existing `attach_recorder_controls` to obtain a reference to the `RecorderTab` instance and its queue.
   - Implement `_drain_samples`:

     ```python
     def _drain_samples(self) -> None:
         if self._recorder is None:
             return
         q = self._recorder.sample_queue  # expose via property
         drained: list[object] = []
         try:
             while True:
                 drained.append(q.get_nowait())
         except queue.Empty:
             pass

         for sample in drained:
             if isinstance(sample, MpuSample):
                 self._plot.add_sample(sample)
     ```

   - Remove or ignore the per-sample `sample_received` connection for SignalsTab; rely on the queue-driven ingestion instead.

3. In `FftTab`:
   - Apply the same pattern as `SignalsTab`:
     - Either share the same ingestion timer and call `FftTab.handle_sample` from `SignalsTab._drain_samples` **once per sample** (still cheaper than two Qt signals), or
     - Give `FftTab` a reference to the queue and let it use its own ingestion timer.

   - A simple approach that integrates well:
     - Keep `RecorderTab.sample_received` connected to a *lightweight* `RecorderTab._on_sample_for_fft`, which just calls a **static method** in `FftTab` or places a reference in a second queue.

   - For this task, you can choose the cleaner design; favour readability.

4. RecorderTab API changes:

   - Add a property:

     ```python
     @property
     def sample_queue(self) -> "queue.Queue[object]":
         return self._sample_queue
     ```

   - Ensure `stop_live_stream()` clears the queue or lets it drain naturally.

5. RateController integration:

   - Continue to call `rc.add_sample_time(t)` in the worker thread.
   - `rate_updated` can still be emitted periodically (e.g. once every N samples) from the worker thread, or you can:
     - Store the rate in a thread-safe variable.
     - Emit the Qt signal from the GUI thread (e.g. via a small QTimer that reads the last rate).

   - For this implementation prompt, it is acceptable to still emit `rate_updated` from the worker as now; the main change is batching samples.

## Constraints

- Keep public signals `streaming_started`, `streaming_stopped`, `error_reported`, and `rate_updated` unchanged.
- Preserve the behaviour of `SignalsTab.on_stream_started/on_stream_stopped` and `FftTab.on_stream_started/on_stream_stopped`.

## Deliverables

- Changes in `RecorderTab`:
  - New queue.
  - Modified worker callback to enqueue samples instead of emitting per-sample signals.
  - A small accessor for the queue.
- Changes in `SignalsTab` (and optionally `FftTab`):
  - QTimer-based `_drain_samples` that pulls from the queue and calls `.add_sample(...)`.
  - Wiring so that `SignalsTab` knows about the `RecorderTab` instance.

Produce final code patches for `tab_recorder.py` and `tab_signals.py` that can be applied directly, with minimal extra edits.
