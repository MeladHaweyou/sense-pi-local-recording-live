# Prompt 3 – “Calibrate ADXL” button in Qt SSH tab (remote call to logger)

**Task:** Add a **“Calibrate ADXL”** button on the SSH tab that:

- Runs a short calibration on the Raspberry Pi by calling `adxl203_ads1115_logger.py` with `--calibrate`.
- Parses the zero‑g offsets printed by the logger.
- Stores them in Qt (`QSettings` or in‑memory).
- Uses them when constructing future ADXL commands (optional).

---

## Behaviour of the logger

In `adxl203_ads1115_logger.py`, during normal startup it does:

```python
if args.calibrate and args.calibrate > 0:
    print(f"[INFO] Calibrating zero-g over {args.calibrate} samples... keep the sensor still")
    zero_g_offsets = calibrate_zero_g(chans, args.calibrate, sleep_s=1.0/100.0)
    print(f"[INFO] Zero-g offsets (V): {zero_g_offsets}")
```

We can leverage that: run the script for a short time with `--calibrate N` and `--no-record`, then parse the printed line.

---

## Requirements

### 1. UI

- Add a `QPushButton("Calibrate ADXL")` to the SSH tab in the ADXL section.
- Disable it when the current sensor type is MPU.

Example:

```python
self.btn_calibrate_adxl = QPushButton("Calibrate ADXL")
self.btn_calibrate_adxl.clicked.connect(self.on_calibrate_adxl_clicked)
adxl_layout.addWidget(self.btn_calibrate_adxl)
```

In the sensor type change handler:

```python
def _update_sensor_type_ui(self) -> None:
    is_adxl = (self.sensor_type_combo.currentText().lower() == "adxl")
    self.btn_calibrate_adxl.setEnabled(is_adxl)
```

---

### 2. SSH command

Use the same connection mechanism as your Qt SSH tab (Paramiko wrapped in a helper similar to `SSHClientManager` from `main.py`).

Build a command like:

```bash
python3 /home/verwalter/sensor/adxl203_ads1115_logger.py     --rate 100 --channels both     --duration 5     --calibrate 300     --no-record     --out /home/verwalter/sensor/logs     --addr 0x48     --map "x:P0,y:P1"
```

…but using **the current ADXL fields from the SSH tab** (rate, channels, out, addr, map, calibrate, lp_cut).

Run it via a blocking `exec_command` or helper like `exec_quick`.

---

### 3. Parsing offsets

In the stdout of the calibration run, look for a line containing `"Zero-g offsets (V)"`.

Extract the dict literal and parse with `ast.literal_eval`:

```python
import ast

offsets = None
for line in stdout.splitlines():
    if "Zero-g offsets (V)" in line:
        _, _, tail = line.partition(":")
        offsets = ast.literal_eval(tail.strip())
        break
```

Store `offsets` in `QSettings("SensePi", "QtSSH")` under a key like `"adxl_zero_g_offsets"`.

---

### 4. Using the offsets

- **Option A (simpler, acceptable):** just **display them** in the SSH tab (read‑only fields like “Zero‑g X”, “Zero‑g Y”) so the user can see them, and still rely on the logger’s built‑in `--calibrate` for each run.
- **Option B (more advanced):** when building the ADXL command later:
  - If stored offsets exist, pass `--calibrate 0` to skip recalibration and apply the stored offsets in Qt (by subtracting them on the client side if you’re using streaming).

For Phase 5, Option A is enough.

---

### 5. UX

Show progress in the SSH tab status area:

- Before running: `“Calibrating ADXL… keep the sensor still”`.
- On success: `“ADXL calibrated. Zero‑g offsets (V): {...}”`.
- On failure (SSH error, parse error): show a clear error message but don’t crash.

---

### 6. Minimal Qt slot scaffold

```python
# inside SSHTab
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QSettings
import ast

def on_calibrate_adxl_clicked(self) -> None:
    if self.current_sensor_type() != "adxl":
        return
    if not self.ssh_manager.is_connected():
        QMessageBox.warning(self, "SSH", "Connect to the Pi first.")
        return

    cmd = self.build_adxl_calibration_command()  # reuse normal ADXL fields, but short duration & --no-record
    self._set_status("Calibrating ADXL… keep the sensor still")
    try:
        stdout, stderr, status = self.ssh_manager.exec_quick(cmd)
    except Exception as exc:
        QMessageBox.critical(self, "Calibration failed", str(exc))
        self._set_status("Calibration failed")
        return

    offsets = None
    for line in stdout.splitlines():
        if "Zero-g offsets (V)" in line:
            _, _, tail = line.partition(":")
            try:
                offsets = ast.literal_eval(tail.strip())
            except Exception:
                pass
            break

    if not isinstance(offsets, dict):
        QMessageBox.warning(self, "Calibration", "Could not parse zero-g offsets from logger output.")
        self._set_status("Calibration: parse error")
        return

    settings = QSettings("SensePi", "QtSSH")
    settings.setValue("adxl_zero_g_offsets", str(offsets))

    self._set_status(f"ADXL calibrated: {offsets}")
```

Implement helper methods:

- `current_sensor_type()`
- `build_adxl_calibration_command()`
- `_set_status(text: str)`

using your existing SSH tab structure.
