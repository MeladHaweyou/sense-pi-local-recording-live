# Prompt – Phase 1.1: Minimal Qt app that actually runs

You are an AI coding agent working on this repo:

```text
C:\Projects\sense-pi-local-recording-live - ref
  main.py                  # Tkinter + paramiko GUI (keep for now)
  adxl203_ads1115_logger.py
  mpu6050_multi_logger.py
  to_be_integrated/
    app.py
    core/
      state.py
      # (missing) models.py   <-- you will create
    data/
      base.py
      live_reader.py
      # (missing) mqtt_source.py  <-- you will create
    plotting/
      plotter.py
    ui/
      main_window.py
      tab_signals.py
      tab_recorder.py
      tab_fft.py
      widgets.py
      # (missing) mqtt_settings.py <-- you will create
      recorder/
        capture_tab.py
        fft_tab.py
        split_csv_tab.py
        view_csv_tab.py
    util/
      calibration.py
      ringbuf.py
```

**Goal for this prompt**  
Make `python -m to_be_integrated.app` open a Qt window that:

- Shows **Signals**, **Record**, and **FFT** tabs (plus 1–2 simple placeholder tabs).
- Has **no ImportError / ModuleNotFoundError** at runtime.
- Does **not** need to actually talk to MQTT or a Pi yet. Dummy/stub data is fine.

Important constraints:

- Treat `to_be_integrated` as a **package**. All imports inside it must be package‑correct.
- Any modules not present (e.g. `core.models`, `data.mqtt_source`, `ui.mqtt_settings`, `sonify.*`, `tab_modeling`, etc.) must be either:
  - stubbed with tiny placeholder implementations, or
  - no longer imported from `MainWindow` / other eagerly imported code.
- Don’t pull in Tkinter. This is a pure Qt shell.

---

## 1. Fix `to_be_integrated.app` to use a relative import

**File:** `to_be_integrated/app.py`

Replace the import of `MainWindow` with a relative import so `python -m to_be_integrated.app` works:

```python
from __future__ import annotations
import os, sys, atexit

# Keep these if you like, they don't hurt:
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

try:
    import sdl3
    sdl3.SDL_Init(sdl3.SDL_INIT_AUDIO)

    def _quit_sdl():
        try:
            sdl3.SDL_Quit()
        except Exception:
            pass

    atexit.register(_quit_sdl)
except Exception:
    # SDL is optional; Qt app should still run without it
    pass

from PySide6.QtWidgets import QApplication
from .ui.main_window import MainWindow   # <-- RELATIVE import

def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

---

## 2. Simplify `MainWindow` to only use existing tabs

**File:** `to_be_integrated/ui/main_window.py`

Current code imports tabs that do not exist in this snapshot (`tab_sonify_*`, `tab_mqtt`, `tab_modeling`, etc.).  
Replace it with a minimal version that wires up only:

- `SignalsTab` (live signals)
- `RecorderTab` (Capture / View CSV / Split / FFT)
- `FFTTab` (live FFT)
- 1–2 simple placeholder tabs

Use package‑correct imports (relative to `to_be_integrated`).

```python
# ui/main_window.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTabWidget, QLabel

from ..core.state import AppState
from .tab_signals import SignalsTab
from .tab_recorder import RecorderTab
from .tab_fft import FFTTab
from .styles import apply_styles


class MainWindow(QMainWindow):
    """Top-level window with core tabs only (Signals, Record, FFT + placeholders)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sense Pi – Qt Shell")
        self.resize(1000, 700)

        self.state = AppState()

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Signals (time-domain)
        self.signals_tab = SignalsTab(self.state, parent=self)
        self.tabs.addTab(self.signals_tab, "Signals")

        # Recorder (Capture / View / Split / FFT)
        self.recorder_tab = RecorderTab(self.state, parent=self)
        self.tabs.addTab(self.recorder_tab, "Record")

        # FFT (frequency-domain, 9 channels)
        self.fft_tab = FFTTab(self.state, parent=self)
        self.tabs.addTab(self.fft_tab, "FFT")

        # Simple placeholders for future features
        for title in ["Analysis results", "Digital twin"]:
            page = QWidget()
            vbox = QVBoxLayout(page)
            label = QLabel("Placeholder – not implemented yet")
            label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            vbox.addStretch(1)
            vbox.addWidget(label)
            vbox.addStretch(1)
            self.tabs.addTab(page, title)

        apply_styles(self)
```

---

## 3. Fix intra‑package imports inside `to_be_integrated`

Use **relative imports** for anything under `to_be_integrated`:

### 3.1 `core/state.py`

**File:** `to_be_integrated/core/state.py`

Change:

```python
from .models import ChannelConfig, MQTTSettings, GlobalCalibration
from data.mqtt_source import MQTTSource
```

to:

```python
from .models import ChannelConfig, MQTTSettings, GlobalCalibration
from ..data.mqtt_source import MQTTSource
```

### 3.2 `ui/tab_signals.py`

**File:** `to_be_integrated/ui/tab_signals.py`

Change top imports from:

```python
from core.state import AppState
from data.mqtt_source import MQTTSource
from plotting.plotter import create_plot, update_curve
from ui.mqtt_settings import MQTTSettingsDialog
import pyqtgraph as pg
from util.calibration import apply_global_and_scale
```

to:

```python
from ..core.state import AppState
from ..data.mqtt_source import MQTTSource
from ..plotting.plotter import create_plot, update_curve
from .mqtt_settings import MQTTSettingsDialog
import pyqtgraph as pg
from ..util.calibration import apply_global_and_scale
```

### 3.3 `ui/tab_recorder.py`

**File:** `to_be_integrated/ui/tab_recorder.py`

Change:

```python
from .recorder.capture_tab import CaptureTab
from .recorder.view_csv_tab import ViewCSVTab
from .recorder.split_csv_tab import SplitCSVTab
from .recorder.fft_tab import FFTTab

from core.state import AppState
```

to:

```python
from .recorder.capture_tab import CaptureTab
from .recorder.view_csv_tab import ViewCSVTab
from .recorder.split_csv_tab import SplitCSVTab
from .recorder.fft_tab import FFTTab

from ..core.state import AppState
```

### 3.4 Recorder sub‑tabs

**File:** `to_be_integrated/ui/recorder/capture_tab.py`

Change:

```python
from core.state import AppState
from data.mqtt_source import MQTTSource
from util.calibration import apply_global_and_scale
```

to:

```python
from ...core.state import AppState
from ...data.mqtt_source import MQTTSource
from ...util.calibration import apply_global_and_scale
```

**File:** `to_be_integrated/ui/recorder/fft_tab.py`

Change:

```python
from core.state import AppState
```

to:

```python
from ...core.state import AppState
```

**File:** `to_be_integrated/ui/recorder/view_csv_tab.py` and `split_csv_tab.py`

Change:

```python
from core.state import AppState
```

to:

```python
from ...core.state import AppState
```

### 3.5 `util/calibration.py`

**File:** `to_be_integrated/util/calibration.py`

Change:

```python
from core.state import AppState
```

to:

```python
from ..core.state import AppState
```

### 3.6 `ui/widgets.py`

**File:** `to_be_integrated/ui/widgets.py`

Change:

```python
from core.state import AppState
```

to:

```python
from ..core.state import AppState
```

Apply similar relative‑import fixes anywhere else using bare `core.*`, `data.*`, `util.*`, `plotting.*`, or `ui.*`.

---

## 4. Add minimal `core/models.py` so `AppState` works

**File (NEW):** `to_be_integrated/core/models.py`

Create a small models module covering all attributes currently used by the UI:

```python
# core/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class ChannelCalibration:
    """Per-channel calibration (currently just a scale factor)."""
    scale: float = 1.0


@dataclass
class ChannelConfig:
    """Configuration for one of the 9 slots."""
    name: str
    enabled: bool = True
    cal: ChannelCalibration = field(default_factory=ChannelCalibration)


@dataclass
class MQTTSettings:
    """
    Minimal MQTT-related settings needed by the UI and AppState.
    Extend later when you wire in the real MQTT client.
    """
    host: str = "localhost"
    port: int = 1883
    topic: str = "sensors/raw"
    initial_hz: int = 50        # used by AppState.start_source()
    recorder: str = "mpu6050"   # displayed in SignalsTab


@dataclass
class GlobalCalibration:
    """Global baseline offsets for 9 slots + enabled flag."""
    enabled: bool = False
    offsets: List[float] = field(default_factory=lambda: [0.0] * 9)
```

---

## 5. Add a stub `MQTTSource` that returns dummy data

**File (NEW):** `to_be_integrated/data/mqtt_source.py`

This is a no‑MQTT implementation that:

- has `start()`, `stop()`, `read(last_seconds)`,
- exposes `.estimated_hz`, `.get_rate().hz_effective`, and `.get_rate_apply_result()`,
- returns `{"slot_0": ..., ..., "slot_8": ..., "slot_ts_0": ..., ..., "slot_ts_8": ...}`.

```python
# data/mqtt_source.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
import time
import numpy as np

from ..core.models import MQTTSettings


class _RateInfo:
    def __init__(self, hz: float) -> None:
        self.hz_effective = float(hz)


@dataclass
class MQTTSource:
    """
    Stub MQTT source used for the Qt shell.

    It does NOT actually connect to a broker; it just synthesizes
    dummy data so that the GUI can run without errors.
    """
    settings: MQTTSettings
    estimated_hz: float = 50.0
    _running: bool = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def switch_frequency(self, hz: int) -> None:
        """Update the estimated sampling frequency (used by UI labels)."""
        self.estimated_hz = float(hz)

    def get_rate(self) -> _RateInfo:
        """Return an object with .hz_effective attribute."""
        return _RateInfo(self.estimated_hz)

    def get_rate_apply_result(self):
        """
        Mimic the real API: return (status, last_requested_hz, timestamp).
        For now, always report 'ok'.
        """
        return ("ok", self.estimated_hz, time.time())

    def read(self, last_seconds: float) -> Dict[str, np.ndarray]:
        """
        Return a dict with slot_0..slot_8 and slot_ts_0..slot_ts_8 arrays.

        Currently returns tiny sine waves (or zeros) so plots have something
        to draw without needing a real broker.
        """
        duration = max(0.1, float(last_seconds))
        n = max(1, int(self.estimated_hz * duration))
        t = np.linspace(0.0, duration, n, endpoint=False, dtype=float)

        out: Dict[str, np.ndarray] = {}
        for i in range(9):
            phase = i * 0.3
            # small sine wave; tweak amplitude later if you like
            y = 0.1 * np.sin(2 * np.pi * 1.0 * t + phase)
            out[f"slot_{i}"] = y
            out[f"slot_ts_{i}"] = t
        return out
```

---

## 6. Add a stub `MQTTSettingsDialog`

**File (NEW):** `to_be_integrated/ui/mqtt_settings.py`

Create a minimal dialog for the “MQTT Settings…” button in `SignalsTab`:

```python
# ui/mqtt_settings.py
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
)

from ..core.state import AppState


class MQTTSettingsDialog(QDialog):
    """
    Minimal stub dialog for editing MQTT settings.

    Lets the user view/edit host/port/topic/initial_hz on AppState.mqtt
    and applies them on OK.
    """

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MQTT Settings")

        self._state = state

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.edit_host = QLineEdit(state.mqtt.host)
        self.edit_port = QLineEdit(str(state.mqtt.port))
        self.edit_topic = QLineEdit(state.mqtt.topic)
        self.edit_hz = QLineEdit(str(state.mqtt.initial_hz))

        form.addRow("Host", self.edit_host)
        form.addRow("Port", self.edit_port)
        form.addRow("Topic", self.edit_topic)
        form.addRow("Initial Hz", self.edit_hz)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        # Apply changes back into state; keep this forgiving.
        m = self._state.mqtt
        m.host = self.edit_host.text().strip() or m.host
        try:
            m.port = int(self.edit_port.text())
        except Exception:
            pass
        m.topic = self.edit_topic.text().strip() or m.topic
        try:
            m.initial_hz = int(float(self.edit_hz.text()))
        except Exception:
            pass
        super().accept()
```

---

## 7. Acceptance criteria for Phase 1.1

After all the above changes:

1. From the repo root, run:

   ```bash
   python -m to_be_integrated.app
   ```

2. Confirm:

   - A Qt window opens titled **“Sense Pi – Qt Shell”**.
   - Tabs visible: **Signals**, **Record**, **FFT**, and the two placeholders.
   - Switching between tabs does **not** crash or raise import errors.
   - Clicking “MQTT Settings…” opens the stub dialog and closes cleanly.

Do **not** worry yet about real data or MQTT – the goal here is a clean, crash‑free Qt shell that uses stubbed data sources.
