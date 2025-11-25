# Prompt 4 – Wire SSH backend into FFT + notes / sonification

*(Use this if/when you actually want FFT/notes/sonification to run on SSH streaming instead of MQTT.)*

**Task:** Allow the existing live FFT and sonification stack (`FFTTab`, `FFTNotesView`, etc.) to operate when the data backend is SSH streaming instead of MQTT, reusing the same `AppState` / `DataSource` abstraction.

---

## Requirements

### 1. New DataSource: SSHSource

Create `to_be_integrated/data/ssh_source.py` implementing the same protocol as `DataSource` in `data/base.py`:

```python
class SSHSource(DataSource):
    def __init__(self, ssh_config: SSHSettingsLike): ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def read(self, last_seconds: float) -> Dict[str, np.ndarray]: ...
```

It should:

- Start an SSH command (MPU or ADXL logger) with `--stream-stdout` from `mpu6050_multi_logger.py` or `adxl203_ads1115_logger.py`.
- Consume JSON lines on a background thread.
- Fill a set of 9 ring buffers (e.g. using `util.ringbuf.RingBuffer`) with per‑slot time series (`"slot_0"` … `"slot_8"` = S0 ax, S0 ay, S0 gz, S1 ax, …).
- Implement `read(last_seconds)` by slicing recent data and returning exactly the same dict shape as `MQTTSource.read()`.

**Minimal ssh_source skeleton:**

```python
# to_be_integrated/data/ssh_source.py
from __future__ import annotations
import json, threading, time
from typing import Dict
import numpy as np

from .base import DataSource
from util.ringbuf import RingBuffer

class SSHSource(DataSource):
    def __init__(self, ssh_client_factory, logger_cmd_builder):
        self._ssh_client_factory = ssh_client_factory
        self._cmd_builder = logger_cmd_builder
        self._client = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._buffers: Dict[int, RingBuffer] = {i: RingBuffer(10_000) for i in range(9)}

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._client = self._ssh_client_factory()
        cmd = self._cmd_builder()
        chan, stdout, _ = self._client.exec_command(cmd)
        def _loop():
            for line in stdout:
                if self._stop.is_set():
                    break
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                # map obj["sensor_id"], obj["ax"], obj["ay"], obj["gz"] -> slot indices 0..8
                self._handle_sample(obj)
        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._client is not None:
            self._client.close()
            self._client = None

    def read(self, last_seconds: float) -> Dict[str, np.ndarray]:
        # TODO: if you store timestamps alongside data, filter by last_seconds
        out: Dict[str, np.ndarray] = {}
        for i in range(9):
            y = self._buffers[i].get_last(5000)
            out[f"slot_{i}"] = y
        return out

    def _handle_sample(self, obj: dict) -> None:
        # TODO: map (sensor_id, ax, ay, gz) into 3 slots per sensor exactly like MQTTSource does
        pass
```

Implement `_handle_sample` to match your existing MQTT layout (S0 ax, S0 ay, S0 gz, …).

---

### 2. AppState switch

Extend `core/state.py`’s `AppState` with `data_source: str = "mqtt"` (already there), and allow `"ssh"` as another option.

Add a small switch in the GUI (maybe in a “Backend” dropdown) that lets the user pick `"mqtt"` vs `"ssh"`.

In `AppState.ensure_source()`, if `self.data_source == "ssh"`, use `SSHSource` instead of `MQTTSource`.

---

### 3. FFT + sonification tabs

`FFTTab` already calls `self.state.ensure_source()` or reads from `state.source`. Ensure that:

- It does not depend on MQTT‑specific methods.
- It only relies on the `DataSource.read()` protocol and the 9 slot arrays.

`FFTNotesView` itself just needs `(signal, fs)`; keep it backend‑agnostic.

---

### 4. Calibration

Regardless of backend (MQTT or SSH), continue to use:

- `SignalsTab.do_calibrate_global` to compute offsets.
- `apply_global_and_scale` for per‑slot correction.

---

By the end of this prompt, you should be able to switch the backend to `"ssh"` and see:

- Live Signals tab using SSH streamed data.
- Live FFT and notes / sonification acting on SSH data via the same `DataSource` interface.
