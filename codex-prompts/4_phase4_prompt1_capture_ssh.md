# Prompt 1 — Phase 4.1: Make `CaptureTab` work with `SSHStreamSource` (Option A)

You are an AI coding assistant working on a PySide6 Qt project.  
The goal of this task is **Phase 4.1** – to make the existing `CaptureTab` record from a new SSH‑based live stream (`SSHStreamSource`) instead of (or in addition to) the old `MQTTSource`.

---

## High‑level requirements

- `AppState.ensure_source()` now returns an `SSHStreamSource` object.
- `SSHStreamSource` must implement the same `read(last_seconds: float) -> dict[str, np.ndarray]` contract as `MQTTSource`, including:
  - data arrays: `slot_0` … `slot_8`
  - timestamp arrays: `slot_ts_0` … `slot_ts_8` (monotonic timestamps in seconds or ns, but consistent)
- We want **Option A**: keep using `CaptureTab` to record a second local CSV from streamed data, while the Pi also records its own local CSV.
- `CaptureTab` must become **source‑agnostic**: it should work with any object implementing the `DataSource` interface, not just `MQTTSource`.

Earlier phases should already have introduced an `SSHStreamSource` implementation and updated `AppState` accordingly; if not, you must create it and wire it in.

---

## Repo structure (relevant parts)

Root project (Windows path, just for orientation):

- `C:\Projects\sense-pi-local-recording-live - ref\`fileciteturn0file0  

Key Qt/“to_be_integrated” bits:

- Qt app root: `to_be_integrated/`
- Core state:
  - `to_be_integrated/core/state.py`
- Abstract data source:
  - `to_be_integrated/data/base.py` (`class DataSource`)
- MQTT live reader helper (old system):
  - `to_be_integrated/data/live_reader.py`
- Recorder tab & sub‑tabs:
  - `to_be_integrated/ui/tab_recorder.py`
  - `to_be_integrated/ui/recorder/capture_tab.py`  ⟵ **focus**
  - `to_be_integrated/ui/recorder/view_csv_tab.py`
  - `to_be_integrated/ui/recorder/split_csv_tab.py`
  - `to_be_integrated/ui/recorder/fft_tab.py`
- Calibration helper:
  - `to_be_integrated/util/calibration.py`

---

## Step 1 — Make `AppState` return `SSHStreamSource` instead of `MQTTSource`

Open `to_be_integrated/core/state.py`.  
It currently looks roughly like this:

```python
# core/state.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

from .models import ChannelConfig, MQTTSettings, GlobalCalibration
from data.mqtt_source import MQTTSource

_DEFAULT_SLOT_NAMES = [
    "S0 ax (m/s²)", "S0 ay (m/s²)", "S0 gz (deg/s)",
    "S1 ax (m/s²)", "S1 ay (m/s²)", "S1 gz (deg/s)",
    "S2 ax (m/s²)", "S2 ay (m/s²)", "S2 gz (deg/s)",
]

@dataclass
class AppState:
    channels: List[ChannelConfig] = field(
        default_factory=lambda: [ChannelConfig(name=_DEFAULT_SLOT_NAMES[i], enabled=True) for i in range(9)]
    )
    data_source: str = "mqtt"

    mqtt: MQTTSettings = field(default_factory=MQTTSettings)
    global_cal: GlobalCalibration = field(default_factory=GlobalCalibration)

    # Shared live source (used by ALL tabs)
    source: MQTTSource | None = None

    def ensure_source(self) -> MQTTSource:
        if self.source is None:
            self.source = MQTTSource(self.mqtt)
        return self.source

    def start_source(self) -> None:
        src = self.ensure_source()
        src.start()  # idempotent
        try:
            if getattr(self.mqtt, "initial_hz", 0):
                src.switch_frequency(int(self.mqtt.initial_hz))
        except Exception:
            pass

    def stop_source(self) -> None:
        if self.source is not None:
            self.source.stop()  # safe if already stopped
```

Refactor this to be generic and to use `SSHStreamSource` instead of `MQTTSource`.

### 1.1 Add generic `DataSource` + SSH imports

At the top:

```python
from data.base import DataSource
from data.ssh_stream_source import SSHStreamSource  # you must create this in earlier phases if missing
```

### 1.2 Generalize the `source` field and methods

Turn `AppState` into something like:

```python
@dataclass
class AppState:
    channels: List[ChannelConfig] = field(
        default_factory=lambda: [ChannelConfig(name=_DEFAULT_SLOT_NAMES[i], enabled=True) for i in range(9)]
    )

    # Primary live backend selector
    data_source: str = "ssh"

    # Settings
    mqtt: MQTTSettings = field(default_factory=MQTTSettings)
    global_cal: GlobalCalibration = field(default_factory=GlobalCalibration)
    ssh: SSHSettings = field(default_factory=SSHSettings)  # define SSHSettings in .models or similar

    # Shared live source (used by ALL tabs)
    source: DataSource | None = None

    def ensure_source(self) -> DataSource:
        """
        Return the shared live data source instance, constructing it on demand.
        For Phase 4, default to SSHStreamSource.
        """
        if self.source is not None:
            return self.source

        if self.data_source == "mqtt":
            self.source = MQTTSource(self.mqtt)
        else:
            # Default to SSH
            self.source = SSHStreamSource(self.ssh)
        return self.source

    def start_source(self) -> None:
        src = self.ensure_source()
        src.start()  # idempotent

    def stop_source(self) -> None:
        if self.source is not None:
            self.source.stop()
```

Notes for the agent:

- If your project no longer needs MQTT at all, you can drop the MQTT branch and just construct `SSHStreamSource`.
- `SSHSettings` should already exist from earlier phases (host, port, user, auth, paths). If it doesn’t, add a small dataclass with those fields and store it on `AppState`.

---

## Step 2 — Ensure `SSHStreamSource.read()` matches the expected API

If `SSHStreamSource` is not implemented yet, create `to_be_integrated/data/ssh_stream_source.py` with at least a skeleton that conforms to `DataSource`:

```python
# data/ssh_stream_source.py
from __future__ import annotations

from typing import Dict
import numpy as np

from .base import DataSource
from util.ringbuf import RingBuffer
from ssh_client.ssh_manager import SSHManager  # or similar, from your earlier phase

class SSHStreamSource(DataSource):
    """
    Live stream data over SSH from the Pi.

    Exposes the same API as MQTTSource.read():
      read(last_seconds) -> {
        "slot_0": np.ndarray,
        ...
        "slot_8": np.ndarray,
        "slot_ts_0": np.ndarray,
        ...
        "slot_ts_8": np.ndarray,
      }

    slot_ts_* should be monotonic timestamps in seconds (or ns) since some epoch.
    """

    def __init__(self, settings: SSHSettings) -> None:
        self._settings = settings
        self._manager = SSHManager(settings)  # adapt ctor as needed
        self._running = False

        # Example: one ring buffer of timestamps + values per slot
        self._ts_bufs = [RingBuffer(size=20000) for _ in range(9)]
        self._val_bufs = [RingBuffer(size=20000) for _ in range(9)]

        self._reader_thread = None
        self._stop_flag = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_flag = False

        # Start SSH process that runs the Pi logger script with --stream-stdout.
        # The logger prints JSON lines with timestamp_ns + fields that map to slots.
        self._start_remote_process_and_reader()

    def stop(self) -> None:
        self._stop_flag = True
        self._running = False
        # terminate remote process + close channel
        self._stop_remote_process_and_reader()

    def read(self, last_seconds: float) -> Dict[str, np.ndarray]:
        """
        Return recent data window for each slot.

        last_seconds is a soft window; if you use absolute monotonic seconds in ts,
        you can slice based on (ts >= ts_max - last_seconds).
        """
        out: Dict[str, np.ndarray] = {}

        # Example logic using RingBuffer.get_last():
        # 1. collect timestamps of each slot as np.ndarray
        # 2. filter last_seconds window if needed
        for i in range(9):
            ts = self._get_ts_array(i)  # implement based on RingBuffer
            vals = self._get_vals_array(i)

            if ts.size and last_seconds > 0:
                t_max = ts[-1]
                mask = ts >= (t_max - last_seconds)
                ts = ts[mask]
                vals = vals[mask]

            out[f"slot_{i}"] = vals
            out[f"slot_ts_{i}"] = ts

        return out

    # internal helpers: _start_remote_process_and_reader, _stop_remote_process_and_reader,
    # _get_ts_array, _get_vals_array, and a background thread function that parses
    # JSONL lines from the remote logger and pushes them into the appropriate slots.
```

You do **not** need to implement the full SSH stream details in this prompt; just make sure the interface and key names are correct so `CaptureTab` and `SignalsTab` can use it.

---

## Step 3 — Make `CaptureTab` source‑agnostic (remove `MQTTSource` hard‑coding)

Open `to_be_integrated/ui/recorder/capture_tab.py`.

Right now, it imports `MQTTSource`:

```python
from core.state import AppState
from data.mqtt_source import MQTTSource
from util.calibration import apply_global_and_scale  # per-slot, like your working code
```

### 3.1 Remove the direct `MQTTSource` dependency

Change imports to:

```python
from core.state import AppState
from util.calibration import apply_global_and_scale
from data.base import DataSource  # optional, for type hints only
```

If you don’t want type hints, you can omit `DataSource`, but you must remove `MQTTSource` here.

### 3.2 Rewrite `_read_latest_values` to be generic

Locate `_read_latest_values`:

```python
def _read_latest_values(self) -> Dict[str, float]:
    """
    Read latest values from MQTTSource.read(window_s), which returns a dict with keys
    'slot_0'...'slot_8' -> ndarray. Map each slot_i to the compact CSV label.
    Apply per-slot calibration (same signature as before).
    """
    out: Dict[str, float] = {lab: np.nan for lab in ALL_LABELS}

    src = self.state.ensure_source()
    if not isinstance(src, MQTTSource):
        return out

    try:
        chunk = src.read(0.5)  # { "slot_0": np.ndarray, ..., "slot_8": np.ndarray }
    except Exception:
        return out

    if not isinstance(chunk, dict):
        return out

    for i in range(9):
        key = f"slot_{i}"
        arr = np.asarray(chunk.get(key, []), dtype=float)
        if arr.size > 0:
            # same per-slot calibration you used previously
            try:
                arr_cal = apply_global_and_scale(self.state, i, arr)
                v = float(arr_cal[-1])
            except Exception:
                v = float(arr[-1])
            out[ALL_LABELS[i]] = v
    return out
```

Change it to **not care** about the concrete source type:

```python
def _read_latest_values(self) -> Dict[str, float]:
    """
    Read latest values from the shared DataSource, which must implement:

        read(window_s) -> {"slot_0": np.ndarray, ..., "slot_8": np.ndarray}

    Map each slot_i to the compact CSV label (s{sensor_idx}_{ax|ay|gz}).
    Apply per-slot calibration (apply_global_and_scale).
    """
    out: Dict[str, float] = {lab: np.nan for lab in ALL_LABELS}

    src = self.state.ensure_source()
    if src is None:
        return out

    try:
        chunk = src.read(0.5)  # {"slot_0": np.ndarray, ..., "slot_8": np.ndarray}
    except Exception:
        return out

    if not isinstance(chunk, dict):
        return out

    for i in range(9):
        key = f"slot_{i}"
        arr = np.asarray(chunk.get(key, []), dtype=float)
        if arr.size > 0:
            try:
                arr_cal = apply_global_and_scale(self.state, i, arr)
                v = float(arr_cal[-1])
            except Exception:
                v = float(arr[-1])
            out[ALL_LABELS[i]] = v

    return out
```

This way, the method will work for both:

- old `MQTTSource` which implements `.read()`,
- new `SSHStreamSource` which also implements `.read()` with the same keys.

### 3.3 Ensure `_sample_once` still works with SSH

`_sample_once` already calls `src.read(1.0)` and expects both:

- `slot_i` arrays,
- `slot_ts_i` arrays.

You only need to ensure that the new SSH backend returns both keys.

The method currently:

```python
def _sample_once(self) -> None:
    src = self.state.ensure_source()
    try:
        chunk = src.read(1.0)  # recent window incl. slot_ts_i arrays
        if not isinstance(chunk, dict):
            return

        slot_data: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for i in range(9):
            ts = np.asarray(chunk.get(f"slot_ts_{i}", np.array([])), dtype=float)
            vals = np.asarray(chunk.get(f"slot_{i}", np.array([])), dtype=float)
            if vals.size:
                try:
                    vals = np.asarray(apply_global_and_scale(self.state, i, vals), dtype=float)
                except Exception:
                    vals = vals.astype(float, copy=False)
            slot_data[i] = (ts, vals)

        if self._rec_mode is RecMode.DRAIN:
            self._emit_rows_drain(slot_data)
        elif self._rec_mode is RecMode.FIXED:
            self._emit_rows_fixed(slot_data, self._fixed_hz)
        else:  # LEGACY
            self._emit_rows_legacy_snapshot(chunk)
    except Exception as e:
        self._set_status(f"Error: {e}")
```

Leave this intact, just make sure `SSHStreamSource.read()` does return the timestamp arrays. No further changes are needed here for Phase 4.1.

---

## Step 4 — Sanity checks

After these modifications, verify:

1. `core/state.py` no longer type‑locks `source` to `MQTTSource` and can construct `SSHStreamSource`.
2. `CaptureTab` (`ui/recorder/capture_tab.py`) imports no `MQTTSource` and uses only `state.ensure_source()` and `.read()`.
3. The new backend (`SSHStreamSource`) returns a dict like:

   ```python
   {
       "slot_0": np.ndarray,
       ...
       "slot_8": np.ndarray,
       "slot_ts_0": np.ndarray,
       ...
       "slot_ts_8": np.ndarray,
   }
   ```

4. Running the Qt app (`python -m to_be_integrated.app`) then:
   - Starting the SSH stream (from earlier phases).
   - Opening the **Record → Capture** sub‑tab.
   - Hitting “Record” → you see sample count increase.
   - Clicking “Save CSV…” writes a CSV file with header: `timestamp_iso, t_rel_s, s0_ax, …`.

When this works end‑to‑end, Phase 4.1 (Option A: record a second local CSV from SSH live data) is done.
