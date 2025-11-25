# Prompt 1 – Extend AppState to support SSH as a data source

**Goal:** Add `SSHSettings` + `data_source` plumbing so `AppState` can construct either an MQTT backend or an SSH backend (`SSHStreamSource`) as a shared live source.

---

## 1. Add `SSHSettings` dataclass in `core/models.py`

Open `to_be_integrated/core/models.py`.

It already defines (at least) `ChannelConfig`, `MQTTSettings`, and `GlobalCalibration`.

1. Import `dataclass` / `field` if not already imported.
2. Add a new dataclass `SSHSettings` *next to* `MQTTSettings`, with fields analogous to the existing Tk SSH GUI (`main.py`) and the spec:

```python
from dataclasses import dataclass, field

@dataclass
class SSHSettings:
    # Basic connection
    host: str = "192.168.0.6"
    port: int = 22
    username: str = "verwalter"     # adjust default as needed
    password: str = ""              # leave empty by default
    key_path: str = ""              # optional private key file

    # Remote scripts + output
    mpu_script: str = "/home/verwalter/sensor/mpu6050_multi_logger.py"
    adxl_script: str = "/home/verwalter/sensor/adxl203_ads1115_logger.py"
    remote_out_dir: str = "/home/verwalter/sensor/logs"

    # Run configuration
    # which sensor logger to run by default: "mpu" or "adxl"
    run_sensor: str = "mpu"

    # recording/streaming mode:
    #   "record"       -> record only (no --stream-stdout)
    #   "record+live"  -> record + stream
    #   "live"         -> stream only (--no-record + --stream-stdout)
    run_mode: str = "record+live"

    # common CLI parameters for both scripts
    rate_hz: float = 100.0
    stream_every: int = 5           # Nth sample to stream over stdout
```

If `MQTTSettings` contains other useful fields you want to mirror (e.g. initial Hz), feel free to add them here, but keep the above minimal set.

---

## 2. Update `core/state.py` to know about SSH + generic sources

Open `to_be_integrated/core/state.py`.

It currently looks roughly like this:

```python
from dataclasses import dataclass, field
from typing import List

from .models import ChannelConfig, MQTTSettings, GlobalCalibration
from data.mqtt_source import MQTTSource

_DEFAULT_SLOT_NAMES = [...]
```

At the bottom it defines `AppState` that hard‑codes MQTT.

### 2.1 Imports

Change imports to:

```python
from dataclasses import dataclass, field
from typing import List

from .models import ChannelConfig, MQTTSettings, SSHSettings, GlobalCalibration
from data.base import DataSource
from data.mqtt_source import MQTTSource
from data.ssh_stream_source import SSHStreamSource  # adjust path/name to match actual file
```

> **Note:** If `SSHStreamSource` does **not yet exist**, create a placeholder in `to_be_integrated/data/ssh_stream_source.py` that:
>
> - subclasses `DataSource`
> - has attributes `estimated_hz: float | None = None`
> - accepts `SSHSettings` in `__init__`
> - implements no‑op `connect()`, `disconnect()`, `start_mpu_stream(...)`, `start_adxl_stream(...)`, `stop_run()` for now
> - `start()` should call `connect()`; `stop()` should call `stop_run()` + `disconnect()`
>
> You will flesh this out in another phase; for now you just need types and basic shape.

### 2.2 AppState fields and methods

Replace the existing `AppState` definition with this version (preserving `_DEFAULT_SLOT_NAMES` and imports above):

```python
@dataclass
class AppState:
    channels: List[ChannelConfig] = field(
        default_factory=lambda: [ChannelConfig(name=_DEFAULT_SLOT_NAMES[i], enabled=True) for i in range(9)]
    )

    # Which backend to use for live data: "mqtt" or "ssh"
    # For this project we default to SSH, but keep MQTT intact.
    data_source: str = "ssh"

    mqtt: MQTTSettings = field(default_factory=MQTTSettings)
    ssh: SSHSettings = field(default_factory=SSHSettings)
    global_cal: GlobalCalibration = field(default_factory=GlobalCalibration)

    # Shared live source instance (MQTTSource or SSHStreamSource)
    source: DataSource | None = None

    def ensure_source(self) -> DataSource:
        """Return the shared live source instance, constructing it on first use."""
        if self.source is not None:
            return self.source

        if self.data_source == "ssh":
            self.source = SSHStreamSource(self.ssh)
        else:
            # Default / fallback: MQTT
            self.source = MQTTSource(self.mqtt)
        return self.source

    def start_source(self) -> None:
        """Ensure the current source exists and is started."""
        src = self.ensure_source()
        src.start()  # idempotent for both MQTT and SSH

        # Preserve existing MQTT frequency behaviour
        if isinstance(src, MQTTSource):
            try:
                if getattr(self.mqtt, "initial_hz", 0):
                    src.switch_frequency(int(self.mqtt.initial_hz))
            except Exception:
                # non-fatal if broker/device is offline
                pass

    def stop_source(self) -> None:
        """Stop the current source (MQTT or SSH) if present."""
        if self.source is not None:
            try:
                self.source.stop()
            except Exception:
                pass
```

**Constraints:**

- Do **not** change the meaning of `MQTTSettings` or `MQTTSource`.
- Keep all other logic in `state.py` intact.
- Make sure all imports used here actually exist (create `ssh_stream_source.py` if necessary).
