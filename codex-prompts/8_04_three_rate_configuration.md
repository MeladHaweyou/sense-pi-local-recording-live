
# Prompt: Implement explicit configuration for recording, streaming, and plot refresh rates

You are editing the SensePi GUI code to make the three key rates explicit and easy to tune:

1. **Recording rate** on the Pi: `mpu6050_multi_logger.py --rate`.
2. **Stream decimation**: `mpu6050_multi_logger.py --stream-every N`.
3. **Plot refresh rate**: QTimer intervals in `SignalsTab` and `FftTab`.

Currently:

- **Recording rate** defaults live in `src/sensepi/config/sensors.yaml` under `mpu6050.sample_rate_hz` and are shown (read-only) in `RecorderTab` (`mpu_recording_rate_label`).
- **Stream decimation** is controlled by `mpu_stream_every_spin` in `RecorderTab` and passed to the Pi via `--stream-every`.
- **Plot refresh** is configured in `SignalsTab` via:
  - `refresh_mode` (fixed vs follow_sampling_rate).
  - `fixed_interval_combo` with presets 250/50/20 ms.
  - A QTimer that calls `self._plot.redraw()`.

## Goal

Expose a **coherent configuration** for these three rates, and wire them end-to-end:

- Users pick:
  - A recording rate (Hz).
  - A *target stream rate* (Hz, capped).
  - A plot refresh preset (“Low CPU”, “Balanced”, “High fidelity”).
- The GUI computes:
  - `stream_every = max(1, round(record_rate / target_stream_rate))`.
  - `plot_refresh_interval_ms` from preset or from stream rate.
- `RecorderTab` passes the computed `--stream-every` to `mpu6050_multi_logger.py`.
- `SignalsTab` uses the chosen plot refresh interval for its QTimer (and updates it when the user changes settings).

## Tasks for you

1. **Add a target stream rate control in RecorderTab**

   In `src/sensepi/gui/tabs/tab_recorder.py`:

   - In the MPU6050 settings area, add a **QDoubleSpinBox** to represent “Target stream rate [Hz] (GUI)”.
   - Reasonable defaults: 25 Hz, range e.g. 1–100 Hz.

   Example snippet to integrate:

   ```python
   self.mpu_target_stream_rate = QDoubleSpinBox(self.mpu_group)
   self.mpu_target_stream_rate.setRange(1.0, 200.0)
   self.mpu_target_stream_rate.setDecimals(1)
   self.mpu_target_stream_rate.setValue(25.0)
   self.mpu_target_stream_rate.setToolTip(
       "Desired rate of samples arriving in the GUI (after decimation). "
       "The logger's --stream-every will be chosen to approximate this."
   )
   mpu_layout.addWidget(QLabel("Target GUI stream [Hz]:", self.mpu_group))
   mpu_layout.addWidget(self.mpu_target_stream_rate)
   ```

2. **Compute `stream_every` based on recording rate + target stream rate**

   In `RecorderTab._build_mpu_extra_args()`:

   - You already have `rate = self._get_default_mpu_sample_rate()`.
   - Use this and the target stream rate to compute `stream_every`:

   ```python
   rate = self._get_default_mpu_sample_rate()
   if rate > 0:
       args += ["--rate", f"{rate:.3f}"]

   target_stream = float(self.mpu_target_stream_rate.value())
   if rate > 0 and target_stream > 0:
       stream_every = max(1, int(round(rate / target_stream)))
   else:
       stream_every = max(1, int(self.mpu_stream_every_spin.value()))
   # If we are also recording, you can enforce a minimum, as the existing code does.
   if self._recording_mode:
       stream_every = max(stream_every, 5)
   args += ["--stream-every", str(stream_every)]
   ```

   - Keep `mpu_stream_every_spin` for advanced users, but it can be hidden or only used when a “Manual stream every” checkbox is enabled.

3. **Persist target stream rate**

   - Add this value to QSettings (similar to how `SignalsTab` stores refresh settings), or at least ensure it’s initialized sensibly on startup.
   - You can add a small helper in `RecorderTab.__init__` to load/save it, but this is optional for now.

4. **Wire plot refresh presets in SignalsTab**

   In `src/sensepi/gui/tabs/tab_signals.py`:

   - `REFRESH_PRESETS` is currently:

     ```python
     REFRESH_PRESETS: list[tuple[str, int]] = [
         ("4 Hz (250 ms) – Low CPU", 250),
         ("20 Hz (50 ms) – Medium", 50),
         ("50 Hz (20 ms) – High (CPU heavy)", 20),
     ]
     ```

   - Keep these, but ensure the **default** choice is consistent with the default target stream rate (e.g. Balanced / 20 Hz).

   - Optionally, add a small label that shows the **effective** refresh rate computed from `RateController` (already tracked in `_stream_rate_label`) and mention “Plot refresh: X ms (preset)”.

5. **Update `SignalsTab._compute_refresh_interval`**

   - Currently, `follow_sampling_rate` mode uses `_sampling_rate_hz` (estimated from RateController):

     ```python
     def _compute_refresh_interval(self) -> int:
         if self.refresh_mode == "follow_sampling_rate":
             rate_hz = self._get_sampling_rate_hz()
             # ...
             interval_ms = int(1000.0 / rate_hz)
             # clamp with MIN_REFRESH_INTERVAL_MS
             return interval_ms
         return int(self.refresh_interval_ms)
     ```

   - Ensure that, by default, `refresh_mode == "fixed"` and `refresh_interval_ms` is set according to the chosen preset.
   - Leave the advanced “follow sampling rate” mode for power users; it should still work with the new streaming configuration.

6. **Update SettingsTab / sensors.yaml docs (optional)**

   - In `src/sensepi/gui/tabs/tab_settings.py`, consider adding a short hint that:
     - `sample_rate_hz` is the recording rate on the Pi.
     - GUI stream and plot rates are configured in the Signals/Recorder tabs.

## Deliverables

- Changes in `RecorderTab`:
  - A new QDoubleSpinBox for “Target GUI stream rate [Hz]”.
  - Updated `_build_mpu_extra_args` to compute `--stream-every` from recording rate + target stream rate.
- Minor changes in `SignalsTab`:
  - Make the refresh presets and default settings consistent with the target GUI stream rate.
  - Ensure refresh settings are still stored in QSettings.

Your patch should integrate with the existing UI layout and signal wiring with minimal disruption.
