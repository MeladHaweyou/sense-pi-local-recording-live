# Prompt 2 – Live calibration UI using apply_global_and_scale and SignalsTab.do_calibrate_global

**Task:** Make sure the Qt SSH / live‑data path uses the same calibration pipeline as the Digital Twin app:

- Global offsets via `SignalsTab.do_calibrate_global`.
- Per‑channel scaling via `util.calibration.apply_global_and_scale`.

---

## Requirements

### 1. Confirm / enforce usage of apply_global_and_scale

In `to_be_integrated/ui/tab_signals.py`, the live plots already call:

```python
from util.calibration import apply_global_and_scale
...
y_cal = apply_global_and_scale(self.state, i, y)
```

In `to_be_integrated/ui/tab_fft.py`, FFT curves also use `apply_global_and_scale`.

If any other live path (e.g. a new SSH‑backed `DataSource` you created earlier) bypasses this function, refactor it so that **all live plots** go through `apply_global_and_scale` when producing y‑values.

---

### 2. Global calibration button

`SignalsTab` already has a `btn_cal` and `do_calibrate_global()` that:

- Read a window from `source.read(window_s)`.
- Compute mean per slot.
- Store offsets in `state.global_cal.offsets`.

Verify that:

- `state.global_cal.enabled` is set to `True`.
- `apply_global_and_scale` subtracts these offsets (it already does based on `state.global_cal.enabled`).

If you have an SSH‑backed `DataSource` (e.g. `SSHSource`) that feeds the same 9 slots, no extra changes are needed; the calibration should “just work”.

---

### 3. UI feedback

After calibration, show a short message somewhere (status bar or small label) like:

> “Global calibration applied (per‑slot mean over last X s)”.

Example: add a `QLabel` in `SignalsTab`’s top bar to echo that message.

---

### 4. Key function to rely on

```python
# to_be_integrated/util/calibration.py
def apply_global_and_scale(state: AppState, idx: int, y: np.ndarray) -> np.ndarray:
    arr = np.asarray(y, dtype=float).ravel()
    if arr.size == 0:
        return arr
    try:
        if state.global_cal.enabled:
            arr = arr - float(state.global_cal.offsets[idx])
    except Exception:
        # keep data as-is if something is wrong with offsets
        pass
    try:
        arr = float(state.channels[idx].cal.scale) * arr
    except Exception:
        pass
    return arr
```

Ensure **all live visualization** (Signals tab, live FFT, any SSH‑driven views) use the above for per‑slot calibration.
