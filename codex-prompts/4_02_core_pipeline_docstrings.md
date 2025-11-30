# SensePi teaching comments – core pipeline (`src/sensepi/core/pipeline.py`, `pipeline_wiring.py`)

You are editing the core fan-out pipeline that connects recording, streaming, and plotting.
The aim is to explain the multi-rate design and queue usage without changing behaviour.

## General rules

- Only adjust / add comments and docstrings – no logic changes.
- Keep new comments to 1–3 lines.
- Focus on *why* we decimate or use queues, rather than restating trivial operations.
- If a similar explanation already exists, tweak it instead of duplicating it.

---

## 1. `_offer_queue` – clarify queue behaviour for GUI paths

In `src/sensepi/core/pipeline.py` locate `_offer_queue`:

```python
def _offer_queue(queue: Queue, item: object) -> None:
    """Best-effort put that drops the oldest payload when the queue is full."""
    try:
        queue.put_nowait(item)
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
        queue.put_nowait(item)
```

Edit: Replace the one-line docstring with this more explicit version (function body unchanged):

```python
def _offer_queue(queue: Queue, item: object) -> None:
    """Best-effort put used for GUI-facing queues.

    When the queue is full we drop the oldest item and keep the newest one
    instead, which keeps the UI responsive under back-pressure.
    """
    ...
```

Keep the try/except logic exactly as it is.

---

## 2. `Streamer.handle_samples` – explain decimation before transport/queue

Find the `Streamer` sink in `pipeline.py` and its `handle_samples` method. It looks similar to:

```python
@dataclass(slots=True)
class Streamer(SampleSink):
    ...
    def handle_samples(self, t: np.ndarray, x: np.ndarray) -> None:
        if x is None or t is None:
            return
        values = np.asarray(x, dtype=np.float32).reshape(-1)
        times = np.asarray(t, dtype=np.float64).reshape(-1)
        if values.size == 0 or times.size == 0:
            return
        start_time = float(times[0])
        t_dec, y_mean, _, _ = self._decimator.process_block(
            values, start_time=start_time
        )
        if t_dec.size == 0:
            return
        payload = (t_dec, y_mean)
        if self.transport is not None:
            self.transport(t_dec, y_mean)
        if self.queue is not None:
            _offer_queue(self.queue, payload)
```

Edits:

1. Add this comment immediately before the `process_block` call:

```python
        # Convert the high-rate sensor stream into a lighter, decimated stream
        # before shipping it across the network or into the GUI queue.
        t_dec, y_mean, _, _ = self._decimator.process_block(
            values, start_time=start_time
        )
```

2. Add this comment before the `if self.transport is not None:` line:

```python
        # The same decimated payload can be sent immediately over the transport
        # and/or handed to a queue that another thread (e.g. Qt) will drain.
```

---

## 3. `PlotUpdate` and `Plotter.handle_samples` – describe the plot-rate decimation

In `pipeline.py`, locate `PlotUpdate` and `Plotter`.

`PlotUpdate` currently has a short docstring like:

```python
@dataclass(slots=True)
class PlotUpdate:
    """Container with decimated plot data."""
    timestamps: np.ndarray
    mean: np.ndarray
    y_min: np.ndarray | None
    y_max: np.ndarray | None
    spike_mask: np.ndarray | None
```

Edit: Replace the docstring with:

```python
@dataclass(slots=True)
class PlotUpdate:
    """Decimated plot data (mean/envelope/spikes) for the Signals tab."""
```

Then in `Plotter.handle_samples` you should see something like:

```python
    def handle_samples(self, t: np.ndarray, x: np.ndarray) -> None:
        if x is None or t is None:
            return
        values = np.asarray(x, dtype=np.float32).reshape(-1)
        times = np.asarray(t, dtype=np.float64).reshape(-1)
        if values.size == 0 or times.size == 0:
            return
        t_dec, y_mean, y_min, y_max = self._decimator.process_block(
            values, start_time=float(times[0])
        )
        if t_dec.size == 0:
            return
        update = PlotUpdate(...)
        ...
```

Edit: Add this comment immediately before the `process_block` call:

```python
        # Second decimation stage: compress the raw stream into a small
        # mean/envelope representation that the GUI can draw every refresh.
        t_dec, y_mean, y_min, y_max = self._decimator.process_block(
            values, start_time=float(times[0])
        )
```

---

## 4. `Pipeline.handle_samples` – highlight fan-out to multi-rate sinks

At the bottom of `pipeline.py` you should see the `Pipeline` dataclass:

```python
@dataclass(slots=True)
class Pipeline:
    """Fan out raw samples to recorder/streamer/plotter sinks."""

    recorder: SampleSink = field(default_factory=NullSink)
    streamer: SampleSink = field(default_factory=NullSink)
    plotter: SampleSink = field(default_factory=NullSink)

    def handle_samples(self, t: Sequence[float] | np.ndarray, x: Sequence[float] | np.ndarray) -> None:
        times = np.asarray(t, dtype=np.float64).reshape(-1)
        values = np.asarray(x).reshape(-1)
        if times.size != values.size:
            raise ValueError("t and x must have the same number of elements.")
        self.recorder.handle_samples(times, values)
        self.streamer.handle_samples(times, values)
        self.plotter.handle_samples(times, values)
```

Edit: Add this comment just before the three sink calls inside `handle_samples`:

```python
        # Fan out the same block of samples to each sink; each sink can apply
        # its own decimation or buffering policy (recording, streaming, plotting).
        self.recorder.handle_samples(times, values)
        self.streamer.handle_samples(times, values)
        self.plotter.handle_samples(times, values)
```

---

## 5. `PipelineHandles` and `build_pipeline` – describe the queues that bridge into Qt

In `src/sensepi/core/pipeline_wiring.py` locate `PipelineHandles`:

```python
@dataclass(slots=True)
class PipelineHandles:
    """Return value from :func:`build_pipeline` containing ready-to-use pieces."""

    pipeline: Pipeline
    stream_queue: Queue[StreamPayload] | None = None
    plot_queue: Queue[PlotUpdate] | None = None
```

Edit: Keep the class docstring and add brief field comments (inline comments are fine) to explain how
these queues are used:

```python
    pipeline: Pipeline
    # Queue drained by the networking / Qt layer for live streaming (optional).
    stream_queue: Queue[StreamPayload] | None = None
    # Queue drained by the plotting layer to update live plots (optional).
    plot_queue: Queue[PlotUpdate] | None = None
```

Then, in the `build_pipeline` function docstring (also in `pipeline_wiring.py`), append a short sentence that
calls out the multi-rate design. For example, if the docstring currently says:

```python
def build_pipeline(...):
    """Construct a Pipeline and any queues needed for streaming/plotting."""
```

change it to:

```python
def build_pipeline(...):
    """Construct a Pipeline and any queues needed for streaming/plotting.

    Recording sees the full device sample rate, while streaming and plotting
    use decimated views to keep network and GUI load manageable.
    """
```

Keep all parameters and return types as they are.

---

After applying these edits, re-run tests that exercise live streaming and plotting to confirm nothing but comments
and docstrings changed.
