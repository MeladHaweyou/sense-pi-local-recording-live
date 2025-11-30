# SensePi teaching comments – buffers and stream reader
Files:
- `src/sensepi/core/ringbuffer.py`
- `src/sensepi/core/stream_reader.py`

The goal here is to clarify how sliding windows and per-channel buffers work, and how they are safely
accessed from different threads.

## General rules

- Only add / adjust docstrings and comments; no behaviour changes.
- New comments should be short (1–3 lines) and focused on intent and usage.
- If the code already contains a similar explanation, refine it instead of repeating it.

---

## 1. `ChannelBuffer` – call out the lock and purpose

In `src/sensepi/core/stream_reader.py`, find `ChannelBuffer`:

```python
class ChannelBuffer:
    """Ring buffer plus lock for one channel of streaming data."""

    def __init__(self, capacity: int) -> None:
        self._buf = RingBuffer[Tuple[int, float]](capacity)
        self._lock = threading.RLock()
```

Edit: Expand the docstring to mention the lock and expected threading pattern:

```python
class ChannelBuffer:
    """Ring buffer plus lock for one channel of streaming data.

    The RLock allows a producer thread to append samples while consumer
    threads take snapshots without corrupting the underlying RingBuffer.
    """
```

Keep the rest of the class unchanged.

---

## 2. `ChannelBuffer.snapshot` – explain snapshot semantics

Still in `ChannelBuffer`, locate `snapshot`:

```python
    def snapshot(self) -> RingBuffer[Tuple[int, float]]:
        with self._lock:
            return self._buf.copy()
```

Edit: Add a short docstring just above the method if it does not already have one:

```python
    def snapshot(self) -> RingBuffer[Tuple[int, float]]:
        """Return a thread-safe copy of the logical contents for read-only use."""
        with self._lock:
            return self._buf.copy()
```

---

## 3. `ChannelBufferStore` – describe multi-channel, multi-thread usage

Locate `ChannelBufferStore` in the same file:

```python
class ChannelBufferStore:
    """Mapping of channel name -> ChannelBuffer."""

    def __init__(self, capacity: int = DEFAULT_RINGBUFFER_CAPACITY) -> None:
        self._capacity = int(capacity)
        self._buffers: Dict[str, ChannelBuffer] = {}
        self._lock = threading.RLock()
```

Edit: Replace the one-line class docstring with this slightly richer version:

```python
class ChannelBufferStore:
    """Mapping of channel name -> ChannelBuffer used by the stream reader.

    A single writer thread appends samples, while readers take snapshots
    for plotting or analysis without blocking the ingest loop.
    """
```

No behaviour changes – only the docstring.

---

## 4. `ChannelBufferStore.append_sample` – comment on lazy buffer creation

Find `append_sample`:

```python
    def append_sample(self, channel: str, timestamp_ns: int, value: float) -> None:
        with self._lock:
            buf = self._buffers.get(channel)
            if buf is None:
                buf = ChannelBuffer(self._capacity)
                self._buffers[channel] = buf
        buf.append(timestamp_ns, value)
```

Edit: Add this comment just before `buf = self._buffers.get(channel)`:

```python
        # Lazily create per-channel buffers so only channels that actually
        # appear in the stream consume memory.
```

---

## 5. `reader_loop` – clarify that it is intended for a background thread

At the bottom of `stream_reader.py`, find `reader_loop`:

```python
def reader_loop(
    stream: Iterable[str],
    buffers: ChannelBufferStore,
    stop_event: threading.Event | None = None,
) -> None:
    """Read JSONL records and append values into channel buffers."""
    for line in stream:
        ...
```

Edit: Expand the docstring to describe thread usage and the purpose of `stop_event`:

```python
def reader_loop(...):
    """Read JSONL records from a line-oriented stream and fill channel buffers.

    This is intended to run in a background thread: it stops when the input
    stream is exhausted or when an optional stop_event is set.
    """
```

---

## 6. `RingBuffer.__getitem__` – reinforce logical indexing

In `src/sensepi/core/ringbuffer.py`, locate the `__getitem__` method. It already has a docstring like:

```python
    def __getitem__(self, idx: int) -> T:
        """Support buf[i] and buf[-1] indexing over the *logical* contents."""
        ...
```

Edit: If that docstring does not already mention that index `0` refers to the oldest item,
extend it to:

```python
    def __getitem__(self, idx: int) -> T:
        """Support buf[i] and buf[-1] indexing over the logical contents (0 = oldest)."""
        ...
```

Do not change any of the indexing arithmetic.

---

After applying these edits, you can optionally run a quick unit or smoke test that exercises the stream reader
and live plot to ensure only comments changed.
