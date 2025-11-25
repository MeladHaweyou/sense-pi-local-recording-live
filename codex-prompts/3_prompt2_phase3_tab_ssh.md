# Prompt 2 – Add SSH settings / control tab and integrate into MainWindow

**Goal:** Create a dedicated **SSH** tab that:

- edits `AppState.ssh` (connection + run config)
- controls `SSHStreamSource`:
  - `connect()` / `disconnect()`
  - `start_mpu_stream(...)` / `start_adxl_stream(...)`
  - `stop_run()`
- switches `AppState.data_source` to `"ssh"` when appropriate
- **does not do any plotting** (Signals/FFT tabs remain responsible for display)

You are working inside `to_be_integrated/ui`.

---

## 1. Create `ui/tab_ssh.py`

Create a new file:

`to_be_integrated/ui/tab_ssh.py`

with a Qt widget class like this:

```python
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QDoubleSpinBox, QPushButton,
    QComboBox, QLabel, QMessageBox, QFileDialog,
)

from core.state import AppState
from data.ssh_stream_source import SSHStreamSource  # adjust module name if needed


class SSHTab(QWidget):
    """
    Simple SSH configuration + run-control panel.

    - Edits AppState.ssh (connection + run config).
    - Uses AppState.ensure_source() / AppState.start_source() so the shared
      SSHStreamSource instance is used by Signals/FFT tabs.
    - No plotting here; this is purely control/UI.
    """

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

        self._build_ui()
        self._load_from_state()
```

### 1.1 Build the UI

Implement `_build_ui()` with:

- Connection group:
  - Host (QLineEdit)
  - Port (QSpinBox)
  - Username (QLineEdit)
  - Password (QLineEdit, password echo)
  - Key file (QLineEdit + “Browse…” button)
- Scripts/output:
  - MPU script path
  - ADXL script path
  - Remote `--out` directory
- Run configuration:
  - Sensor combo: “MPU6050 (multi)” / “ADXL203 (ADS1115)”
  - Run mode combo: “Record only”, “Record + live”, “Live only”
  - Rate (Hz) (QDoubleSpinBox)
  - Stream every N (QSpinBox)
- Buttons:
  - Connect / Disconnect / Start run / Stop run
- Status label

Use this template and fill in the missing bits only (don’t change structure):

```python
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # --- Connection form ---
        conn_form = QFormLayout()

        self.edit_host = QLineEdit()
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)

        self.edit_user = QLineEdit()
        self.edit_password = QLineEdit()
        self.edit_password.setEchoMode(QLineEdit.Password)

        key_row = QHBoxLayout()
        self.edit_key = QLineEdit()
        btn_browse_key = QPushButton("Browse…")
        btn_browse_key.clicked.connect(self._choose_key_file)
        key_row.addWidget(self.edit_key)
        key_row.addWidget(btn_browse_key)

        conn_form.addRow("Host", self.edit_host)
        conn_form.addRow("Port", self.spin_port)
        conn_form.addRow("Username", self.edit_user)
        conn_form.addRow("Password", self.edit_password)
        # Use a container widget to hold the key_row layout
        key_container = QWidget()
        key_container.setLayout(key_row)
        conn_form.addRow("Key file", key_container)

        root.addLayout(conn_form)

        # --- Scripts / output ---
        paths_form = QFormLayout()
        self.edit_mpu_script = QLineEdit()
        self.edit_adxl_script = QLineEdit()
        self.edit_out_dir = QLineEdit()

        paths_form.addRow("MPU script", self.edit_mpu_script)
        paths_form.addRow("ADXL script", self.edit_adxl_script)
        paths_form.addRow("Remote out dir", self.edit_out_dir)
        root.addLayout(paths_form)

        # --- Run config ---
        run_form = QFormLayout()

        self.combo_sensor = QComboBox()
        self.combo_sensor.addItems(["MPU6050 (multi)", "ADXL203 (ADS1115)"])

        self.combo_run_mode = QComboBox()
        self.combo_run_mode.addItems(["Record only", "Record + live", "Live only"])

        self.spin_rate = QDoubleSpinBox()
        self.spin_rate.setRange(0.1, 5000.0)
        self.spin_rate.setDecimals(2)
        self.spin_rate.setValue(100.0)

        self.spin_stream_every = QSpinBox()
        self.spin_stream_every.setRange(1, 1000000)
        self.spin_stream_every.setValue(5)

        run_form.addRow("Sensor", self.combo_sensor)
        run_form.addRow("Run mode", self.combo_run_mode)
        run_form.addRow("Rate (Hz)", self.spin_rate)
        run_form.addRow("Stream every N", self.spin_stream_every)
        root.addLayout(run_form)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_start_run = QPushButton("Start run")
        self.btn_stop_run = QPushButton("Stop run")

        self.btn_connect.clicked.connect(self.on_connect)
        self.btn_disconnect.clicked.connect(self.on_disconnect)
        self.btn_start_run.clicked.connect(self.on_start_run)
        self.btn_stop_run.clicked.connect(self.on_stop_run)

        btn_row.addWidget(self.btn_connect)
        btn_row.addWidget(self.btn_disconnect)
        btn_row.addWidget(self.btn_start_run)
        btn_row.addWidget(self.btn_stop_run)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        # Status label
        self.lbl_status = QLabel("Disconnected")
        root.addWidget(self.lbl_status)

        self.setLayout(root)
```

### 1.2 Sync settings with AppState

Add helper methods to load/save `AppState.ssh`:

```python
    def _load_from_state(self) -> None:
        s = self.state.ssh
        self.edit_host.setText(s.host)
        self.spin_port.setValue(int(s.port))
        self.edit_user.setText(s.username)
        self.edit_password.setText(s.password)
        self.edit_key.setText(s.key_path)
        self.edit_mpu_script.setText(s.mpu_script)
        self.edit_adxl_script.setText(s.adxl_script)
        self.edit_out_dir.setText(s.remote_out_dir)
        self.spin_rate.setValue(float(s.rate_hz))
        self.spin_stream_every.setValue(int(s.stream_every))
        self.combo_sensor.setCurrentIndex(0 if s.run_sensor == "mpu" else 1)
        mode_index = {"record": 0, "record+live": 1, "live": 2}.get(s.run_mode, 1)
        self.combo_run_mode.setCurrentIndex(mode_index)

    def _save_to_state(self) -> None:
        s = self.state.ssh
        s.host = self.edit_host.text().strip()
        s.port = int(self.spin_port.value())
        s.username = self.edit_user.text().strip()
        s.password = self.edit_password.text()
        s.key_path = self.edit_key.text().strip()
        s.mpu_script = self.edit_mpu_script.text().strip()
        s.adxl_script = self.edit_adxl_script.text().strip()
        s.remote_out_dir = self.edit_out_dir.text().strip()
        s.rate_hz = float(self.spin_rate.value())
        s.stream_every = int(self.spin_stream_every.value())
        s.run_sensor = "mpu" if self.combo_sensor.currentIndex() == 0 else "adxl"
        idx_mode = self.combo_run_mode.currentIndex()
        s.run_mode = ["record", "record+live", "live"][idx_mode]
        self.state.data_source = "ssh"
```

Keyfile chooser:

```python
    def _choose_key_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select private key", "", "Key files (*)")
        if path:
            self.edit_key.setText(path)
```

### 1.3 Wire buttons to SSHStreamSource

We want a single shared SSHStreamSource instance (`AppState.source`) that is also used by Signals/FFT tabs.

Add a helper to ensure we have the right source constructed:

```python
    def _ensure_ssh_source(self) -> SSHStreamSource:
        # Persist UI values to state and force backend to ssh
        self._save_to_state()

        # Stop any existing source (MQTT or previous SSH)
        try:
            self.state.stop_source()
        except Exception:
            pass

        self.state.data_source = "ssh"
        self.state.source = None

        src = self.state.ensure_source()
        if not isinstance(src, SSHStreamSource):
            raise RuntimeError("Expected SSHStreamSource when data_source == 'ssh'")
        return src
```

Now implement the button slots (adapt the method names to your actual `SSHStreamSource` API; the semantics are key):

```python
    def on_connect(self) -> None:
        try:
            src = self._ensure_ssh_source()
            src.connect()  # should use self.state.ssh inside
            self.lbl_status.setText(
                f"Connected to {self.state.ssh.username}@{self.state.ssh.host}:{self.state.ssh.port}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "SSH connect failed", str(exc))
            self.lbl_status.setText("Connect failed")

    def on_disconnect(self) -> None:
        try:
            src = self.state.source
            if isinstance(src, SSHStreamSource):
                src.disconnect()
            self.lbl_status.setText("Disconnected")
        except Exception as exc:
            QMessageBox.warning(self, "SSH disconnect", str(exc))

    def on_start_run(self) -> None:
        try:
            src = self._ensure_ssh_source()
            s = self.state.ssh

            # Ensure internal threads are running if needed
            self.state.start_source()

            mode = s.run_mode
            record = (mode in ("record", "record+live"))
            live = (mode in ("record+live", "live"))

            if s.run_sensor == "mpu":
                src.start_mpu_stream(
                    rate_hz=s.rate_hz,
                    record=record,
                    live=live,
                    stream_every=s.stream_every,
                )
            else:
                src.start_adxl_stream(
                    rate_hz=s.rate_hz,
                    record=record,
                    live=live,
                    stream_every=s.stream_every,
                )
            self.lbl_status.setText("Run active")
        except Exception as exc:
            QMessageBox.critical(self, "Start run failed", str(exc))
            self.lbl_status.setText("Run error")

    def on_stop_run(self) -> None:
        try:
            src = self.state.source
            if isinstance(src, SSHStreamSource):
                if hasattr(src, "stop_run"):
                    src.stop_run()
                else:
                    src.stop()
            self.lbl_status.setText("Run stopped")
        except Exception as exc:
            QMessageBox.warning(self, "Stop run", str(exc))
```

> If `SSHStreamSource` offers a different API, **adapt the method names and arguments**, but keep:
>
> - `connect()` / `disconnect()`
> - one method for starting MPU streams, one for ADXL streams
> - `stop_run()` as the primary way to stop remote logging.

---

## 2. Add SSH tab to `ui/main_window.py`

Open `to_be_integrated/ui/main_window.py`.

### 2.1 Import SSHTab

At the top, next to other tab imports, add:

```python
from .tab_ssh import SSHTab
```

### 2.2 Instantiate and add the tab

In `MainWindow.__init__`, after `self.state = AppState()` and before Signals, add:

```python
        # SSH control tab (connection + run config)
        self.ssh_tab = SSHTab(self.state)
        self.tabs.addTab(self.ssh_tab, "SSH")
```

Leave the rest of the tabs (Signals, Record, FFT, etc.) unchanged.

Resulting order (example):

1. SSH
2. Signals
3. Record
4. FFT
5. Sonify …
6. Modeling
7. Placeholders…

This keeps the SSH configuration clearly visible.

---

After this prompt, the app should:

- show a new “SSH” tab
- let you configure SSH and start a run
- create/configure `SSHStreamSource` as `AppState.source` so other tabs can read from it.
