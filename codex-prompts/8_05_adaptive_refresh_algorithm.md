
# Prompt: Implement an adaptive refresh / decimation controller based on measured load

You are editing the SensePi GUI to automatically **reduce plotting and streaming load** when the system is under stress, while trying to keep plots smooth.

We already have:

- `RecorderTab` measuring effective GUI stream rate with `RateController`.
- `SignalsTab` with:
  - Plot refresh modes (“fixed” vs “follow sampling rate”).
  - A QTimer driving `self._plot.redraw()` at configurable intervals.
- A `Target GUI stream rate` (from the previous prompt) and a `stream_every` value passed to `mpu6050_multi_logger.py`.

## Goal

Implement a simple **adaptive control loop** that:

1. Monitors:
   - Effective GUI stream rate (from `RateController`, via `update_stream_rate` in `SignalsTab`).
   - Average redraw time for `SignalPlotWidget.redraw()` and optionally `FftTab._update_fft`.
2. When **redraw time becomes too large** or the system cannot keep up, it:
   - Increases `stream_every` (reducing stream rate).
   - Or increases the plot refresh interval.
3. When the system is comfortably under load, it may cautiously **improve fidelity**:
   - Decrease `stream_every` (more samples).
   - Decrease the plot refresh interval (faster updates) within configured caps.

This should run automatically in the background, but we can gate it behind a simple UI toggle like “Adaptive performance mode”.

## Tasks for you

1. **Measure redraw time in SignalsTab**

   In `src/sensepi/gui/tabs/tab_signals.py`:

   - In `_plot.redraw()`, or just around the call site in the QTimer handler, measure wall-clock duration:

     ```python
     import time

     class SignalsTab(QWidget):
         def __init__(...):
             # ...
             self._last_redraw_ms = 0.0
             self._redraw_ema_ms = 0.0  # exponential moving average

         def _on_redraw_timer(self) -> None:
             start = time.perf_counter()
             self._plot.redraw()
             elapsed_ms = (time.perf_counter() - start) * 1000.0
             self._last_redraw_ms = elapsed_ms
             alpha = 0.2
             if self._redraw_ema_ms == 0.0:
                 self._redraw_ema_ms = elapsed_ms
             else:
                 self._redraw_ema_ms = alpha * elapsed_ms + (1.0 - alpha) * self._redraw_ema_ms
     ```

   - Adjust the QTimer to call `_on_redraw_timer` instead of `_plot.redraw` directly.

2. **Expose adaptive mode in the UI**

   - In `SignalsTab` top controls, add a `QCheckBox`:

     ```python
     self.adaptive_mode_check = QCheckBox("Adaptive performance", top_row_group)
     self.adaptive_mode_check.setToolTip(
         "Automatically lower plotting/streaming load if redraws become too slow."
     )
     top_row.addWidget(self.adaptive_mode_check)
     ```

3. **Implement a small controller in SignalsTab**

   - Add a QTimer, e.g. `self._adaptive_timer`, that fires every 1–2 seconds:

     ```python
     self._adaptive_timer = QTimer(self)
     self._adaptive_timer.setInterval(2000)
     self._adaptive_timer.timeout.connect(self._adaptive_step)
     self._adaptive_timer.start()
     ```

   - Implement `_adaptive_step`:

     ```python
     def _adaptive_step(self) -> None:
         if not self.adaptive_mode_check.isChecked():
             return
         # Read metrics
         redraw_ms = self._redraw_ema_ms
         stream_rate = self._sampling_rate_hz or 0.0  # from update_stream_rate

         # Define targets and thresholds
         target_refresh_ms = self._compute_refresh_interval()  # current desired refresh
         max_frame_ms = target_refresh_ms * 0.9  # we want redraw < 90% of interval
         max_stream_hz = float(self._target_stream_rate_from_recorder() or 25.0)

         # If redraw is too slow relative to interval, consider reducing load
         if redraw_ms > max_frame_ms and stream_rate > 0:
             self._lower_fidelity()
         else:
             self._maybe_increase_fidelity()
     ```

   - Implement `_lower_fidelity` and `_maybe_increase_fidelity` with hysteresis to avoid oscillations:

     ```python
     def _lower_fidelity(self) -> None:
         # 1) Increase plot refresh interval up to some cap
         if self.refresh_mode == "fixed":
             new_interval = min(500, int(self.refresh_interval_ms * 1.5))
             if new_interval != self.refresh_interval_ms:
                 self.refresh_interval_ms = new_interval
                 self._select_fixed_interval(new_interval)
                 self._apply_refresh_settings()
                 return

         # 2) Ask RecorderTab to increase stream_every (if possible)
         if self._recorder is not None:
             self._recorder.request_coarser_streaming()
     ```

   - `_maybe_increase_fidelity` can do the opposite, but only if redraw has been comfortably below threshold for several cycles (you can store a counter).

4. **Add a simple hook in RecorderTab**

   In `RecorderTab`:

   - Add a method:

     ```python
     def request_coarser_streaming(self) -> None:
         cfg = self.current_mpu_gui_config()
         # for now, just bump stream_every spinbox
         self.mpu_stream_every_spin.setValue(min(1000, self.mpu_stream_every_spin.value() * 2))
         # The next restart of the stream will use the new value (simplest approach).
     ```

   - Optionally, if you want dynamic adjustment without restart, you can integrate with the Pi logger in a more sophisticated way later; for now, it is OK if adaptation only takes effect on the next stream start.

5. **Integrate target stream rate**

   - If you implemented a “Target GUI stream [Hz]” control, you can also adjust it in `request_coarser_streaming()` or provide a symmetrical `request_finer_streaming()`.

6. **Display a small performance summary**

   - In `SignalsTab`, update a label (e.g. reuse `_status_label` or add a new one) to periodically show:

     - `Stream rate ≈ X Hz`
     - `Redraw EMA ≈ Y ms`
     - `Refresh interval = Z ms`

   This helps debug the adaptive behaviour.

## Constraints

- Keep the implementation **simple and robust**; it does not need to be perfect control theory.
- Avoid heavy computations in timers; the adaptive step runs at low frequency (e.g. every 2 seconds).
- Leave all existing manual controls working; adaptive mode should be opt‑in.

## Deliverables

- Code changes in `SignalsTab` implementing:
  - Redraw timing measurement.
  - Adaptive mode checkbox.
  - Adaptive controller with `_adaptive_step`, `_lower_fidelity`, and `_maybe_increase_fidelity`.
- Code changes in `RecorderTab` implementing:
  - `request_coarser_streaming()` (and optionally a symmetric method).

Provide final patches that plug into the existing class structure with minimal extra wiring.
