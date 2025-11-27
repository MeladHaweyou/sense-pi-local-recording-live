# Prompt: Clarify and Document Multi-Rate Behaviour (Sampling, Streaming, Refresh)

You are working inside the **SensePi** repository. The system already has three distinct “rates”:

1. **Sensor sampling / recording rate on the Pi** (`--rate` in `mpu6050_multi_logger.py`, configured via `sensors.yaml`).
2. **Streaming rate** from the Pi to the GUI (controlled by `--stream-every` and `--stream-fields`).
3. **GUI plot refresh rate** (Qt timer interval in `SignalsTab`, modes: fixed vs follow sampling rate).

The goal of this task is **not** to change behaviour, but to:

- Make the rate relationships explicit and easy to understand in the code.
- Add small bits of logging / UI hints so that users and developers clearly see what each rate means.
- Ensure the “follow sampling rate” mode in `SignalsTab` behaves well and is clearly documented.

Relevant files:

- `raspberrypi_scripts/mpu6050_multi_logger.py`
- `src/sensepi/config/sensors.yaml`
- `src/sensepi/gui/tabs/tab_recorder.py`
- `src/sensepi/gui/tabs/tab_signals.py`

## 1. Add docstrings and inline comments

### `mpu6050_multi_logger.py`

At the top-level `main()` logic, where `--rate`, `--stream-every`, and `--stream-fields` are parsed and used, add a clear comment block summarizing the three rates, for example:

```python
    # ------------------------------------------------------------------
    # Rates overview
    # ------------------------------------------------------------------
    # - args.rate / mpu6050.sample_rate_hz:
    #     Device sampling + recording rate (Hz) on the Pi.
    # - args.stream_every:
    #     Stream decimation factor; only every N-th sample per sensor is
    #     emitted over stdout for remote GUIs.
    # - GUI refresh rate:
    #     Controlled on the desktop side (SignalsTab QTimer); independent
    #     from the device sampling rate.
```

This is purely for developer clarity.

### `tab_recorder.py`

In `RecorderTab._build_mpu_extra_args`, there is already logic that ties recording mode to streaming decimation:

```python
        stream_every = max(1, int(self.mpu_stream_every_spin.value()))
        if self._recording_mode:
            stream_every = max(stream_every, 5)
        args += ["--stream-every", str(stream_every)]
```

Add a docstring to `_build_mpu_extra_args` and/or inline comments explaining the rationale:

- Recording uses full device rate on Pi, but GUI receives decimated stream.
- When recording is enabled, force a minimum `--stream-every` (e.g. 5) to avoid overwhelming the GUI at high sampling rates.

## 2. Improve GUI labels / tooltips in `SignalsTab`

In `src/sensepi/gui/tabs/tab_signals.py`, the top row already shows:

- `recording_check` – “Recording” checkbox.
- `_stream_rate_label` – e.g. “Stream rate: X Hz”.
- Plot refresh settings are under a collapsible section (“Plot refresh rate / GUI refresh”).

### Tasks

1. Update `_stream_rate_label` tooltip to explicitly mention that this is the **effective rate of samples arriving in the GUI**, *after* any Pi-side `--stream-every` decimation.

   For example:

   ```python
   self._stream_rate_label.setToolTip(
       "Estimated rate at which samples arrive in this GUI tab, after Pi-side "
       "stream decimation (--stream-every)."
   )
   ```

2. In the refresh settings section (`_build_refresh_controls`), add a short tooltip or label text explaining the difference between:

   - “Fixed refresh rate” – QTimer interval is a fixed preset (4 Hz, 20 Hz, etc.), independent of stream rate.
   - “Follow sampling rate” – QTimer interval is derived from the estimated stream rate (but clamped to a minimum like 20 ms).

   You can extend the existing helper label:

   ```python
   help_label = QLabel(
       "High refresh rates and 'Follow sampling rate' may be heavy on CPU, "
       "especially with many channels.\n"
       "In 'Fixed refresh rate' mode, the plots update at a configurable "
       "timer interval regardless of the stream rate.\n"
       "In 'Follow sampling rate' mode, the timer interval is derived from "
       "the estimated stream rate reported by the Recorder tab."
   )
   ```

3. In `update_stream_rate`, add a short comment indicating that this slot is fed by `RecorderTab.rate_updated` and represents the **GUI-side stream rate**, not the Pi’s raw sampling rate.

   ```python
   @Slot(str, float)
   def update_stream_rate(self, sensor_type: str, hz: float) -> None:
       """Update the small stream-rate label from RecorderTab.

       The value 'hz' is the estimated rate at which samples arrive in this
       GUI (after any Pi-side stream decimation), not the device's raw
       sampling rate.
       """
       ...
   ```

## 3. Ensure “follow sampling rate” is robust

`SignalsTab` already has logic to compute the refresh interval when `refresh_mode == "follow_sampling_rate"`:

```python
    def _compute_refresh_interval(self) -> int:
        if self.refresh_mode == "follow_sampling_rate":
            rate_hz = self._get_sampling_rate_hz()
            if not rate_hz or rate_hz <= 0:
                return DEFAULT_REFRESH_INTERVAL_MS

            interval_ms = int(1000.0 / rate_hz)
            if interval_ms < MIN_REFRESH_INTERVAL_MS:
                interval_ms = MIN_REFRESH_INTERVAL_MS
            return interval_ms

        return int(self.refresh_interval_ms)
```

Tasks:

1. Confirm that `MIN_REFRESH_INTERVAL_MS` is set to a sensible minimum (currently 20 ms = 50 Hz). If needed, add a comment explaining why this clamp exists (human perceptual limits, CPU constraints).

2. In `update_stream_rate`, after updating `_sampling_rate_hz`, the code already does:

   ```python
   if self.refresh_mode == "follow_sampling_rate":
       self._apply_refresh_settings()
   ```

   Leave this logic as-is, but add a debug log or comment noting that this may frequently update the QTimer interval as stream rate estimates change.

   Optional: use Python’s `logging` module to emit a debug-level message when the computed interval changes significantly (e.g. >10% difference), but ensure logging is not too spammy.

## 4. Acceptance criteria

- No change in functional behaviour of streaming or plotting, just better documentation and clarity.
- Developers reading the code can quickly understand:
  - Which rate lives where (Pi vs stream vs GUI refresh).
  - How `--stream-every` interacts with `SignalsTab`’s stream-rate estimate.
  - What “follow sampling rate” actually does.
- Tooltips in the GUI make it clearer to advanced users how the system behaves.

Please implement comments, docstrings, and small tooltip/label text changes in the indicated files. Avoid changing logic beyond trivial log/tooltip additions. 
