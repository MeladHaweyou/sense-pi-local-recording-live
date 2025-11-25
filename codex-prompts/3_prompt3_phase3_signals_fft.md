# Prompt 3 – Make SignalsTab and FFTTab use SSHStreamSource via AppState

**Goal:** Make `SignalsTab` and `FFTTab` work with **any** data source (MQTT or SSH) that:

- implements `DataSource.read(window_s) -> dict[str, np.ndarray]` with `"slot_i"` arrays
- exposes either:
  - `estimated_hz` (SSHStreamSource style), **or**
  - `get_rate().hz_effective` (MQTTSource style)

Keep existing MQTT‑specific UI parts (MQTT settings dialog, recorder label) intact.

---

## 1. Update `ui/tab_signals.py` to be backend‑agnostic

Open: `to_be_integrated/ui/tab_signals.py`.

It currently imports and assumes `MQTTSource` in a few places, and the top label says “Sensors data (MQTT)”.

### 1.1 Imports

Keep the existing MQTT import but also import `DataSource` to reflect generic use:

```python
from core.state import AppState
from data.base import DataSource
from data.mqtt_source import MQTTSource
```

(If `DataSource` is not used in type hints, this import is optional.)

### 1.2 Neutral top label

In `_build_ui()`, change the label from:

```python
        top_row.addWidget(QLabel("Sensors data (MQTT):"))
```

to:

```python
        top_row.addWidget(QLabel("Sensors data (live):"))
```

### 1.3 Sampling rate estimation `_expected_points`

Replace `_expected_points()` with a backend‑agnostic implementation:

```python
    def _expected_points(self) -> int:
        window_s = float(self.spin_window.value())
        src = self.state.source or self.state.ensure_source()

        hz = 20.0
        if src is not None:
            # Prefer generic estimated_hz attribute (SSHStreamSource, etc.)
            est = getattr(src, "estimated_hz", None)
            if est:
                hz = float(est)

            # Fallback to MQTT-specific rate info if available
            if isinstance(src, MQTTSource):
                try:
                    hz = float(src.get_rate().hz_effective)
                except Exception:
                    pass

        n = int(round(max(0.001, window_s) * max(1.0, hz)))
        return max(1, n)
```

`_apply_expected_xrange()` can stay as it is; it uses `_expected_points()`.

### 1.4 Use generic source in `update_data()`

At the top of `update_data()`, change the logic to:

```python
    def update_data(self) -> None:
        src = self.state.source
        dev_hz = 0.0

        if src is not None:
            est = getattr(src, "estimated_hz", None)
            if est:
                dev_hz = float(est)

        # Preserve MQTT-specific status details if available
        if isinstance(src, MQTTSource):
            try:
                rate = src.get_rate()
                dev_hz = float(rate.hz_effective)
            except Exception:
                pass

            try:
                status, hz_req, t = src.get_rate_apply_result()
                if status == "ok":
                    self.lbl_fs.setText(
                        f"Device: ~{dev_hz:.1f} Hz · Last set {hz_req:.0f} Hz ✓"
                    )
                elif status == "timeout":
                    self.lbl_fs.setText(
                        f"Device: ~{dev_hz:.1f} Hz · Set {hz_req:.0f} Hz timed out"
                    )
            except Exception:
                # ignore; label will be set generically below if needed
                pass

        # Generic label for non-MQTT sources (e.g. SSH)
        if not isinstance(src, MQTTSource):
            self.lbl_fs.setText(f"Device: ~{dev_hz:.1f} Hz")

        self._apply_expected_xrange()
        window_s = float(self.spin_window.value())
        if src is None:
            return

        try:
            data = src.read(window_s)
        except Exception:
            # If source fails hard, stop the timer and reset
            self.on_start_stop()
            data = {f"slot_{i}": np.array([]) for i in range(9)}
```

Leave the rest of `update_data()` unchanged (loop over slots, `apply_global_and_scale`, `update_curve`, background colors). It already only depends on `src.read()` returning `"slot_i"` arrays.

> Important: The only knowledge of MQTT left here should be:
> - calling `MQTTSettingsDialog`
> - reading `self.state.mqtt.recorder`
> - using `MQTTSource` only for the extra device rate status (optional)

`on_start_stop()` can remain as-is: it just calls `self.state.start_source()` / `stop_source()`, which now handle both MQTT and SSH depending on `AppState.data_source`.

---

## 2. Update `ui/tab_fft.py` to compute fs from any source

Open: `to_be_integrated/ui/tab_fft.py`.

It currently imports `MQTTSource` and implements `_current_fs()` as:

```python
    def _current_fs(self) -> float:
        src = self.state.ensure_source()
        if isinstance(src, MQTTSource):
            fs = float(src.estimated_hz or 20.0)
        else:
            fs = 20.0
        return max(1e-6, fs)
```

### 2.1 Imports

At top, import `DataSource` alongside `MQTTSource`:

```python
from core.state import AppState
from data.base import DataSource
from data.mqtt_source import MQTTSource
```

### 2.2 Backend‑agnostic `_current_fs()`

Replace `_current_fs()` with:

```python
    def _current_fs(self) -> float:
        """Determine effective sampling rate in Hz from the current live source.

        Priority:
          1. src.estimated_hz (SSHStreamSource or generic)
          2. MQTTSource.get_rate().hz_effective
          3. fallback 20.0 Hz
        """
        src = self.state.source or self.state.ensure_source()
        hz = 20.0

        if src is not None:
            est = getattr(src, "estimated_hz", None)
            if est:
                hz = float(est)

            if isinstance(src, MQTTSource):
                try:
                    hz = float(src.get_rate().hz_effective)
                except Exception:
                    pass

        return max(1e-6, float(hz))
```

### 2.3 Keep `_read_window()` generic

`_read_window()` is already generic and should remain unchanged:

```python
    def _read_window(self) -> dict[str, np.ndarray]:
        src = self.state.source
        if src is None:
            return {f"slot_{i}": np.array([]) for i in range(9)}
        window_s = float(self.spin_window.value())
        try:
            return src.read(window_s)
        except Exception:
            return {f"slot_{i}": np.array([]) for i in range(9)}
```

### 2.4 Leave FFT logic untouched

All other logic (FFT computation, peak picking, normalization, curves, etc.) should not assume MQTT at all and can remain unchanged.

---

## 3. Behaviour after these changes (what to expect)

Once you apply Prompts 1–3:

1. Start the Qt app via `python -m to_be_integrated.app`.
2. Go to the **SSH** tab:
   - configure host/user/password/key and script paths
   - set sensor: **MPU6050** or **ADXL203**
   - choose run mode: **Record + live** to get both CSV logging and live stream
   - click **Connect**, then **Start run**.
3. Switch to **Signals** tab:
   - click **Start**
   - observe live plots driven by `SSHStreamSource.read(window_s)`.
4. Switch to **FFT** tab:
   - click **Start**
   - observe live FFT, using the same `SSHStreamSource` backend.
5. If you switch `AppState.data_source = "mqtt"` and provide a valid MQTT setup, both tabs should again work with MQTT.

This completes **Phase 3 – Wire SSHStreamSource into Qt Signals + FFT tabs** in a way that is backend‑agnostic, keeps MQTT alive, and cleanly integrates SSH as a first‑class data source.
