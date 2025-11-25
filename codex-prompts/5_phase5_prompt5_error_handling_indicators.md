# Prompt 5 – Error handling + SSH / Run / Stream indicators in Qt SSH tab

**Task:** Add **visible indicators and better error handling** to the Qt SSH tab so it feels as rich as the Tkinter GUI in `main.py`.

We want:

- A mini status bar (or dedicated row) inside the SSH tab.
- Three text indicators:
  - `SSH: Connected / Disconnected`
  - `Run: Idle / Running (ADXL / MPU)`
  - `Stream: packets/sec, missing data estimate`
- Display of connection errors, remote script failures, `pkill` errors, etc.

---

## Requirements

### 1. Status row UI

At the bottom of `SSHTab`, add a `QHBoxLayout` containing three labels:

```python
self.lbl_ssh = QLabel("SSH: Disconnected")
self.lbl_run = QLabel("Run: Idle")
self.lbl_stream = QLabel("Stream: —")

row = QHBoxLayout()
row.addWidget(self.lbl_ssh)
row.addWidget(self.lbl_run)
row.addWidget(self.lbl_stream)
row.addStretch(1)

main_layout.addLayout(row)
```

Optionally, use colored text:

- Green for OK.
- Red for error.

Helper:

```python
from PySide6.QtWidgets import QLabel

def _set_indicator(self, label: QLabel, text: str, ok: bool | None) -> None:
    label.setText(text)
    if ok is True:
        color = "#2e8b57"   # green
    elif ok is False:
        color = "#b22222"   # red
    else:
        color = "#444444"   # neutral
    label.setStyleSheet(f"QLabel {{ color: {color}; font-weight: bold; }}")
```

---

### 2. SSH connect / disconnect

When the SSH client connects successfully:

```python
self._set_indicator(self.lbl_ssh, "SSH: Connected", ok=True)
```

On disconnect or failure:

```python
self._set_indicator(self.lbl_ssh, "SSH: Disconnected", ok=False)
```

Reuse logic from Tkinter’s `App._connect_worker()` in `main.py` but adapted to Qt signals/slots (e.g. move Paramiko work to a worker thread and update the labels via `QMetaObject.invokeMethod` or `QTimer.singleShot`).

---

### 3. Run state

When starting a remote run (MPU or ADXL):

```python
sensor_label = "ADXL" if self.current_sensor_type() == "adxl" else "MPU6050"
self._set_indicator(self.lbl_run, f"Run: Running {sensor_label}", ok=True)
self._set_indicator(self.lbl_stream, "Stream: warming up…", ok=None)
```

On normal completion:

```python
self._set_indicator(self.lbl_run, "Run: Idle", ok=None)
```

On error (non‑zero exit status, thrown exception):

```python
self._set_indicator(self.lbl_run, "Run: Error (see log)", ok=False)
```

Show remote stderr lines in a log text area if you have one (similar to Tkinter’s scrolled text).

---

### 4. Stream stats

While reading JSON lines from `--stream-stdout`:

- Count samples per second.
- Optionally estimate “missing” based on expected rate (`rate / stream_every`).

Maintain simple counters:

```python
self._stream_samples = 0
self._stream_window_start = time.monotonic()
```

For each valid JSON sample:

```python
self._stream_samples += 1
self._maybe_update_stream_label()
```

Every ~1 second, compute:

```python
rate = self._stream_samples / dt
self.lbl_stream.setText(f"Stream: {rate:.1f} pkt/s")
self._stream_samples = 0
self._stream_window_start = now
```

You can also compare against expected:

```python
expected_hz = requested_rate / stream_every
ok_flag = rate > 0.5 * expected_hz
self._set_indicator(
    self.lbl_stream,
    f"Stream: {rate:.1f} pkt/s (expected ~{expected_hz:.1f})",
    ok=ok_flag,
)
```

---

### 5. `pkill` & stop errors

When stopping a run, you already do something like (in Tkinter):

```python
_, err, status = self.manager.exec_quick(f"pkill -f {pattern}")
self._log(f"Stop command sent (pkill status {status}).")
if err.strip():
    self._log(f"pkill stderr: {err.strip()}")
```

Port this to Qt and, on non‑zero `status`, set:

```python
self._set_indicator(self.lbl_run, "Run: pkill error", ok=False)
```

---

### 6. Helper for colored labels

(Already given above.)

Call `_set_indicator` from your SSH connect/disconnect handlers, run worker, and stop worker.

By the end of this prompt, the SSH tab should visibly communicate:

- SSH connection state.
- Whether a run is active or idle.
- Whether streaming is happening at a reasonable rate.
- When errors occur, both via colored labels and via a log area.
