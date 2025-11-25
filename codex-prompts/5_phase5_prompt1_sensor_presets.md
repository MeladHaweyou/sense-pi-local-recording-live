# Prompt 1 – Sensor presets in Qt SSH tab (QSettings + combo box)

**Task:** Implement sensor presets in the Qt SSH GUI (SSH tab), similar to the Tkinter `self.presets` dict in `main.py`, but with persistence using `QSettings`.

Assume there is (or you can create) an SSH tab class, e.g. `SSHTab` in `to_be_integrated/ui/tab_ssh.py`, integrated into `MainWindow`’s `QTabWidget`.

---

## Requirements

### 1. Preset storage

- Use `QSettings("SensePi", "QtSSH")` to persist a JSON blob under key `"ssh_presets"`.
- Each preset is a dict keyed by a human‑readable name, e.g. `"3×MPU, 200 Hz, 60 s, default channels"`.
- Fields to store (at minimum):

**Common:**

- `sensor_type`: `"mpu"` or `"adxl"`.

**For MPU:**

- `rate_hz`
- `duration_s`
- `sensors`
- `channels`
- `out`
- `format`
- `prefix`
- `dlpf`
- `temp`

**For ADXL:**

- `rate_hz`
- `duration_s`
- `channels`
- `out`
- `addr`
- `map`
- `calibrate`
- `lp_cut`

On startup, load presets from `QSettings`; if none exist, seed a couple of defaults roughly mirroring `main.py`’s presets.

**Reference (Tkinter presets in `main.py`):**

```python
# main.py – inside App._build_vars()
self.presets = {
    "Quick ADXL test (10 s @ 100 Hz)": {
        "sensor_type": "adxl",
        "rate": "100",
        "duration": "10",
        "channels": "both",
        "out": "/home/pi/logs/adxl",
        "addr": "0x48",
        "map": "x:P0,y:P1",
        "calibrate": "300",
        "lp_cut": "15",
    },
    "3×MPU6050 full sensors (60 s @ 200 Hz)": {
        "sensor_type": "mpu",
        "rate": "200",
        "duration": "60",
        "sensors": "1,2,3",
        "channels": "both",
        "out": "/home/pi/logs/mpu",
        "format": "csv",
        "prefix": "mpu",
        "dlpf": "3",
        "temp": True,
    },
}
```

---

### 2. UI elements on SSH tab

Add, near the top of the SSH tab:

- A `QComboBox` for presets (first item: `"<No preset>"`).
- A “Apply preset” `QPushButton`.
- A “Save current as preset…” `QPushButton`.
- Optional: “Delete preset” button.

---

### 3. Apply a preset

When the user chooses a preset and clicks **“Apply preset”**:

- Switch the sensor type selector (MPU vs ADXL) accordingly.
- Populate the various Qt fields (spin boxes / line edits / combos) that map to the logger CLI arguments.
- Use the same logic as Tkinter’s `apply_selected_preset()` in `main.py`, but adapted to Qt widgets.

Example mapping (pseudo):

```python
if preset["sensor_type"] == "adxl":
    self.sensor_type_combo.setCurrentIndex(ADXL_INDEX)
    self.adxl_rate_spin.setValue(float(preset["rate_hz"]))
    self.adxl_duration_spin.setValue(float(preset["duration_s"]))
    self.adxl_channels_combo.setCurrentText(preset["channels"])
    self.adxl_out_edit.setText(preset["out"])
    self.adxl_addr_edit.setText(preset["addr"])
    self.adxl_map_edit.setText(preset["map"])
    self.adxl_calibrate_spin.setValue(int(preset["calibrate"]))
    self.adxl_lp_cut_spin.setValue(float(preset["lp_cut"]))
else:
    # sensor_type == "mpu"
    self.sensor_type_combo.setCurrentIndex(MPU_INDEX)
    self.mpu_rate_spin.setValue(float(preset["rate_hz"]))
    self.mpu_duration_spin.setValue(float(preset["duration_s"]))
    self.mpu_sensors_edit.setText(preset["sensors"])
    self.mpu_channels_combo.setCurrentText(preset["channels"])
    self.mpu_out_edit.setText(preset["out"])
    self.mpu_format_combo.setCurrentText(preset["format"])
    self.mpu_prefix_edit.setText(preset["prefix"])
    self.mpu_dlpf_spin.setValue(int(preset["dlpf"]))
    self.mpu_temp_checkbox.setChecked(bool(preset.get("temp", False)))
```

---

### 4. Save a new preset

On **“Save current as preset…”**:

1. Ask for a name using `QInputDialog.getText(self, "Preset name", "Enter a preset name:")`.
2. If the user cancels or gives empty text, do nothing.
3. Create a dict by reading the current SSH tab fields.
4. Store into the in‑memory presets dict via `PresetStore.upsert(name, payload)` and persist to `QSettings`.
5. Refresh the combo box and select the new preset.

---

### 5. Do not break existing behaviour

- Starting / stopping runs through SSH should continue to work as before.
- The command builder on the SSH tab should still build from the UI fields; presets are just a convenient way to fill those fields.

---

## Scaffolding to adapt

**Minimal Qt‑side preset manager you can adapt (in `to_be_integrated/ui/tab_ssh.py`):**

```python
from PySide6.QtCore import QSettings
import json

class PresetStore:
    KEY = "ssh_presets"

    def __init__(self) -> None:
        self._settings = QSettings("SensePi", "QtSSH")
        self._presets: dict[str, dict] = {}
        self.load()

    @property
    def presets(self) -> dict[str, dict]:
        return self._presets

    def load(self) -> None:
        raw = self._settings.value(self.KEY, "{}", str)
        try:
            self._presets = json.loads(raw)
        except Exception:
            self._presets = {}

    def save(self) -> None:
        self._settings.setValue(self.KEY, json.dumps(self._presets, indent=2))

    def upsert(self, name: str, payload: dict) -> None:
        self._presets[name] = payload
        self.save()

    def delete(self, name: str) -> None:
        if name in self._presets:
            del self._presets[name]
            self.save()
```

**Hook this into the SSH tab:**

```python
class SSHTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preset_store = PresetStore()
        self._build_ui()
        self._refresh_preset_combo()

    def _build_ui(self) -> None:
        # existing layout...
        self.preset_combo = QComboBox(self)
        self.btn_apply_preset = QPushButton("Apply preset", self)
        self.btn_save_preset = QPushButton("Save current as preset…", self)

        self.btn_apply_preset.clicked.connect(self._on_apply_preset_clicked)
        self.btn_save_preset.clicked.connect(self._on_save_preset_clicked)

        row = QHBoxLayout()
        row.addWidget(self.preset_combo)
        row.addWidget(self.btn_apply_preset)
        row.addWidget(self.btn_save_preset)
        main_layout.addLayout(row)  # main_layout is your main layout

    def _refresh_preset_combo(self) -> None:
        self.preset_combo.clear()
        self.preset_combo.addItem("<No preset>")
        for name in sorted(self._preset_store.presets.keys()):
            self.preset_combo.addItem(name)

    # TODO:
    # - implement _current_form_as_preset_dict()
    # - implement _apply_preset_dict(preset: dict)
```

Implement `_current_form_as_preset_dict()` and `_apply_preset_dict()` by reading/writing the SSH tab’s fields (similar to `apply_selected_preset()` in Tkinter).
