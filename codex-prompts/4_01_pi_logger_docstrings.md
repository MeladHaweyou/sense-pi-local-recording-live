# SensePi teaching comments – Raspberry Pi logger (`raspberrypi_scripts/mpu6050_multi_logger.py`)

You are editing the SensePi Raspberry Pi logger. Your task is to add short, teaching-oriented docstrings and comments
to make the timing and streaming logic easier for students to understand.

## General rules

- Do not change any behaviour or control flow; only add / adjust comments and docstrings.
- Keep each new comment to at most 1–3 lines.
- Prefer explaining *why* a pattern exists (drift-free timing, async writer, decimation) instead of restating
  what the code obviously does.
- If a similar explanation already exists in the docstring or nearby comments, either keep it or lightly refine it
  instead of duplicating text.

---

## 1. `monotonic_controller` – explain drift-free timing

Goal: Explain that this generator keeps sampling on a fixed schedule and avoids long-term drift.

Current snippet (for context – do not paste this verbatim back into the file):

```python
def monotonic_controller(rate_hz: float):
    """Generator yielding next target monotonic_ns tick for drift-corrected scheduling."""
    period = int(1e9 / rate_hz)
    next_t = time.monotonic_ns()
    while True:
        next_t += period
        yield next_t
```

Edit: Replace the existing one-line docstring with this more teaching-oriented version
(keep the function body exactly as it is):

```python
def monotonic_controller(rate_hz: float):
    """Yield target monotonic_ns timestamps for a fixed sampling rate.

    Each step adds a fixed period to the *previous target* time, which keeps the
    long-term rate stable and avoids drift from small sleep() errors.
    """
    period = int(1e9 / rate_hz)
    next_t = time.monotonic_ns()
    while True:
        next_t += period
        yield next_t
```

If the current docstring already explains drift-free timing in similar words, you can just tweak it
to match the intent above.

---

## 2. Main sampling loop – relate `target_next` and `overruns` to the controller

Goal: Clarify how `target_next` and `overruns` track timing and scheduling.

Look for the main sampling loop that uses `monotonic_controller`, which should look broadly like:

```python
controller = monotonic_controller(req_rate)
target_next = next(controller)
overruns = 0
...
while True:
    now_ns = time.monotonic_ns()
    sleep_ns = target_next - now_ns
    if sleep_ns > 0:
        time.sleep(sleep_ns / 1e9)
    else:
        overruns += 1
        ...
    target_next = next(controller)
    # read sensors, write rows, maybe stream stdout, ...
```

Edit: Add this comment immediately above the `now_ns = time.monotonic_ns()` line inside the loop:

```python
        # Sleep until the next *target* tick from monotonic_controller so the
        # loop tracks the requested sample rate, counting overruns instead of
        # silently drifting when iterations run late.
        now_ns = time.monotonic_ns()
```

Keep the rest of the loop intact.

---

## 3. `AsyncWriter` – explain decoupling of I/O via a background thread

Goal: Emphasize that each sensor uses a background writer with a queue so that sampling never blocks on disk I/O.

Locate the `AsyncWriter` class (in the same logger module). It will look roughly like:

```python
class AsyncWriter:
    """Async CSV/JSONL writer with periodic flush.

    Changes:
        - ...
    """

    def __init__(...):
        ...
        self._q: "queue.Queue[Optional[dict]]" = queue.Queue()
        self._t = threading.Thread(target=self._run, daemon=True)
        ...
```

### 3.1 Extend the class docstring

Edit: Extend the existing docstring by appending this short paragraph (do not delete the existing content;
just add this before the closing triple quotes):

```python
    """Async CSV/JSONL writer with periodic flush.

    ... existing notes / bullet points ...

    One AsyncWriter instance runs in a background thread per sensor. The main
    sampling loop only enqueues rows into a queue, so slow disks cannot stall
    time-critical sensor reads.
    """
```

Adapt the `... existing notes / bullet points ...` placeholder to preserve whatever content is already present.

### 3.2 Explain the `None` sentinel in `_run`

In the `_run` method there will be a loop that reads from `self._q` and treats `None` as a stop signal, for example:

```python
    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                break
            ...
        self._fh.flush()
        self._fh.close()
```

Edit: Replace the bare `if item is None:` block with the following (logic unchanged, just an extra comment):

```python
            if item is None:
                # None is a sentinel pushed by stop(): flush any pending rows
                # and exit the writer thread cleanly.
                break
```

Leave the final flush/close logic as it is.

---

## 4. Per-sensor error isolation in the sensor setup loop

Goal: Explain why each sensor init is wrapped in its own try/except.

Find the sensor setup loop that looks similar to:

```python
for sensor_id, mapping in sensor_map.items():
    try:
        with SMBus(bus_id) as bus:
            ...
            sensors.append(sensor)
    except FileNotFoundError as exc:
        logger.error("...")
    except OSError as exc:
        logger.error("...")
```

Edit: Add this 1–2 line comment at the top of the `try:` block, just before opening the bus:

```python
        # Each sensor is initialised in its own try/except block so that a
        # single failing device or I2C bus does not abort the entire run.
```

---

## 5. `--stream-every` / meta header for stdout streaming

Goal: Make it obvious that the Pi streams only every N-th sample and advertises that via a JSON meta header.

Locate the block that conditionally writes JSON to `sys.stdout` when `args.stream_stdout` is true. It builds a meta
dictionary containing keys such as `pi_device_sample_rate_hz`, `pi_stream_decimation`, `pi_stream_rate_hz` and
possibly `sensor_ids`, and prints those lines before the main loop.

Edit: Add the following comment immediately above the meta-header `print` calls:

```python
    # Advertise the Pi-side stream configuration as an initial JSON header so
    # the desktop GUI knows the device rate and how many samples are skipped
    # by --stream-every when estimating the live stream rate.
```

Do not modify the meta fields themselves – only add the comment.

---

After adding these docstrings and comments, run your usual tests or at least `python -m compileall .` on the project
to confirm there are no syntax errors from indentation or quoting.
