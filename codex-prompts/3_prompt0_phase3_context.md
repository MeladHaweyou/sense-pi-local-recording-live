# Prompt 0 – Context (Phase 3 – SSHStreamSource wiring)

You are editing a Python / Qt6 project that lives under:

`to_be_integrated/`

It’s a live sensor viewer/recorder GUI (“Digital Twin Simple”) that currently uses MQTT as its data backend.  
I want to **add an SSH‑based backend** (`SSHStreamSource`) and wire it into the Qt Signals and FFT tabs so that I can get live plots over SSH from a Raspberry Pi running:

- `mpu6050_multi_logger.py`
- `adxl203_ads1115_logger.py`

You **must keep the existing MQTT behaviour intact**, but the default backend for this project can be SSH.

Key files (paths are relative to `to_be_integrated`):

- `core/state.py` – central `AppState`
- `data/base.py` – `DataSource` base class
- `data/mqtt_source.py` – MQTT live source (already exists in my repo even if you don’t see it here)
- `ui/tab_signals.py` – live time‑domain signals
- `ui/tab_fft.py` – live FFT
- `ui/main_window.py` – top‑level tabs
- **NEW:** `ui/tab_ssh.py` – SSH connection / run control tab (you will create this)

There is also a separate Tk/Paramiko GUI at the repo root (`main.py`) that already knows how to:

- connect over SSH
- build the correct `python3 mpu6050_multi_logger.py ...` / `python3 adxl203_ads1115_logger.py ...` commands
- stream JSON lines over stdout (`timestamp_ns`, `sensor_id`, `ax`, `ay`, `gz` or `x_lp`, `y_lp`, …)

You may reuse ideas from `main.py` but **do not copy the Tk GUI** – only re‑use the logic for building commands / run modes where appropriate.

The live Qt GUI expects its backend source (`AppState.source`) to:

- implement the `DataSource` protocol from `data/base.py`:
  - `start()`, `stop()`, `read(last_seconds) -> dict[str, np.ndarray]`
  - keys like `"slot_0"` ... `"slot_8"`
- expose some sampling‑rate info (`estimated_hz` or similar) for status/FFT

You **must not** randomly reformat or rewrite whole files. Make small, surgical changes that preserve style and behaviour, unless explicitly told otherwise.

When you’re ready, I’ll give you specific tasks to implement SSH support.
