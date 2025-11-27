# AI Prompt 02 – PC Stream Reader & Dispatch to GUI

You are an AI coding assistant working on the **Sensors recording and plotting** project.
Implement the **stream reader** on the PC side that ingests JSON lines from the Pi (over SSH/STDIN or socket) and dispatches them to plotting components.

## Goals

- Read a continuous JSONL stream from the Pi.
- Parse each line into a Python dict with at least:
  - `sensor_id`
  - `t_s` (nanoseconds since epoch)
  - sensor values (`ax, ay, az, gx, gy, gz`, etc.).
- Push parsed samples into **thread-safe ring buffers** (one per sensor/channel) used by the GUI.

## Constraints & Integration

- GUI is in **PySide6**.
- Use an existing `RingBuffer` class from `src/sensepi/core/ringbuffer.py` (assume interface similar to `append(timestamp, value)` and window retrieval).
- Data arrives on a background thread; GUI updates happen on the main Qt thread.

## Tasks

1. Implement a small module, e.g. `stream_reader.py`, that:
   - Reads from a text stream (file-like: `sys.stdin` or socket file descriptor).
   - For each line:
     - Parse JSON.
     - Route by `sensor_id` and channel name (e.g., `ax`, `ay`, ...).
2. Maintain a mapping:
   - `buffers[(sensor_id, channel_name)] -> RingBuffer instance`.
3. For each record:
   - For every numeric field representing a channel:
     - Append `(t_s, value)` into the corresponding buffer.
4. Use a **producer/consumer** design:
   - Reader thread: only parses and appends to buffers.
   - GUI thread: reads from buffers during QTimer callbacks.

## Important Code Skeleton (Python)

```python
import json
import sys
import threading
from collections import defaultdict
# Assume RingBuffer has interface: append(t, v), get_window(t_start, t_end)
from src.sensepi.core.ringbuffer import RingBuffer

# Global / shared buffers (could be encapsulated in a class instead)
buffers = defaultdict(lambda: RingBuffer(capacity=5000))  # 10s @ 500 Hz example

def reader_loop(stream):
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            # TODO: log and skip
            continue

        t_ns = record.get("t_s")
        sid = record.get("sensor_id")
        if t_ns is None or sid is None:
            continue

        # For all sensor value fields
        for key, val in record.items():
            if key in ("t_s", "sensor_id"):
                continue
            if not isinstance(val, (int, float)):
                continue

            buf_key = (sid, key)
            buffers[buf_key].append(t_ns, float(val))

def start_reader_on_stdin():
    t = threading.Thread(target=reader_loop, args=(sys.stdin,), daemon=True)
    t.start()
    return t
```

## Notes for the AI

- Ensure `RingBuffer` usage is thread‑safe or guard with a simple lock if needed.
- No GUI code here – just ingestion and buffering.
- The GUI layer will later access `buffers` read‑only on the main thread.
