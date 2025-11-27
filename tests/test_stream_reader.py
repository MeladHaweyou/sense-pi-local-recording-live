from __future__ import annotations

import io
import json
import time

from sensepi.core.stream_reader import (
    ChannelBufferStore,
    DEFAULT_RINGBUFFER_CAPACITY,
    reader_loop,
    start_reader,
)


def _build_line(sensor_id: int, timestamp: float, **channels: float) -> str:
    payload = {"sensor_id": sensor_id, "t_s": timestamp}
    payload.update(channels)
    return json.dumps(payload)


def test_reader_loop_populates_channel_buffers() -> None:
    store = ChannelBufferStore(capacity=4)
    lines = [
        _build_line(1, 0.001, ax=0.1, ay=0.2),
        _build_line(1, 0.002, ax=0.3, ay=0.4),
    ]
    reader_loop(lines, store)

    ax_buffer = store.get("1", "ax")
    assert ax_buffer is not None
    assert ax_buffer.snapshot() == [(0.001, 0.1), (0.002, 0.3)]

    ay_buffer = store.get("1", "ay")
    assert ay_buffer is not None
    assert ay_buffer.snapshot() == [(0.001, 0.2), (0.002, 0.4)]


def test_reader_loop_ignores_invalid_records() -> None:
    store = ChannelBufferStore(capacity=2)
    lines = [
        "not-json",
        json.dumps({"sensor_id": 1, "ax": 1.0}),  # missing timestamp
        json.dumps({"t_s": 0.1, "ax": 1.0}),  # missing sensor_id
        json.dumps({"sensor_id": 1, "t_s": 0.2, "ax": "not-a-number"}),
        _build_line(2, 0.3, ax=2.5),
    ]
    reader_loop(lines, store)

    assert store.get("2", "ax").snapshot() == [(0.3, 2.5)]


def test_start_reader_background_thread() -> None:
    buffer = io.StringIO("\n".join([_build_line(3, 0.1, ax=1.5)]) + "\n")
    handle = start_reader(buffer, capacity=DEFAULT_RINGBUFFER_CAPACITY)

    # Allow background thread to process the single line
    timeout = time.time() + 1.0
    while time.time() < timeout:
        buf = handle.buffers.get("3", "ax")
        if buf and len(buf) == 1:
            break
        time.sleep(0.01)

    handle.stop(join=True, timeout=1.0)

    buf = handle.buffers.get("3", "ax")
    assert buf is not None
    assert buf.snapshot() == [(0.1, 1.5)]
