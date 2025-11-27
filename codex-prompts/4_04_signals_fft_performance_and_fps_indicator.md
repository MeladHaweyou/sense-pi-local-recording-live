# Prompt: Add GUI FPS/refresh indicator and prep for shared live buffers

You are an AI coding assistant working on the **sensepi** project.
Your main task is to make it easier for users to see whether they are **CPU‑bound**
by exposing the GUI plot refresh rate (approx FPS) in the Signals tab.
Additionally, you should prepare the code for a future refactor towards **shared live buffers**
between the Signals and FFT tabs without fully rewriting everything.

Focus on **integration** and small, incremental improvements.

---

## Context: SignalsTab and FFTTab

Relevant modules:

- `sensepi/gui/tabs/tab_signals.py`
- `sensepi/gui/tabs/tab_fft.py`

### SignalsTab (simplified)

SignalsTab already has:

- Per‑channel visibility checkboxes.
- View presets (3 axes vs 6).
- Adjustable plot refresh rate (QTimer).
- A `_stream_rate_label` showing stream rate in Hz.

Example excerpts (names are illustrative, adapt to exact code):

```python
class SignalsTab(QWidget):
    def __init__(self, app_config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        ...
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_refresh_timer)
        self._refresh_interval_ms = 50

        self._stream_rate_label = QLabel("Stream: -- Hz")
        self._buffer_window_label = QLabel("Window: 10 s")
        ...

    def _apply_refresh_settings(self):
        interval_ms = self._refresh_interval_ms
        self._refresh_timer.setInterval(interval_ms)
    ```

### FFTTab (simplified)

The FFT tab uses its **own** ring buffers and its own QTimer:

```python
class FftTab(QWidget):
    def __init__(self, app_config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_refresh_timer)
        self._buffers: dict[tuple[str, str, str], RingBuffer] = {}
        ...
```

Both tabs currently maintain their own in‑memory buffers keyed by `(sensor_key, sensor_id, channel)`
and are updated from the streaming data.

---

## Part 1: Add a GUI plot refresh / FPS indicator in SignalsTab

1. **Add a new label to show the plot refresh rate**

   - In `SignalsTab.__init__`, add something like:

     ```python
     self._plot_refresh_label = QLabel("Plot refresh: -- Hz")
     ```

   - Place this label near the existing `_stream_rate_label` and/or buffer window label
     in the layout so users can see stream rate vs GUI refresh rate side by side.

2. **Track actual refresh frequency**

   Implement simple measurement of how often `_on_refresh_timer` is called:

   - Maintain in `SignalsTab`:

     ```python
     self._last_refresh_timestamp: float | None = None
     self._smoothed_refresh_hz: float | None = None
     ```

   - In `_on_refresh_timer`, compute the delta between the current time and
     `self._last_refresh_timestamp`, then update a simple EMA (exponential moving average)
     for refresh Hz.

     Example sketch (use `time.monotonic()`):

     ```python
     now = time.monotonic()
     if self._last_refresh_timestamp is not None:
         dt = now - self._last_refresh_timestamp
         if dt > 0:
             inst_hz = 1.0 / dt
             alpha = 0.2  # smoothing factor
             if self._smoothed_refresh_hz is None:
                 self._smoothed_refresh_hz = inst_hz
             else:
                 self._smoothed_refresh_hz = (
                     alpha * inst_hz + (1.0 - alpha) * self._smoothed_refresh_hz
                 )
     self._last_refresh_timestamp = now
     ```

   - After updating the value, call a helper to update the label text:

     ```python
     def _update_plot_refresh_label(self) -> None:
         if self._smoothed_refresh_hz is None:
             text = "Plot refresh: -- Hz"
         else:
             text = f"Plot refresh: {self._smoothed_refresh_hz:4.1f} Hz"
         self._plot_refresh_label.setText(text)
     ```

   - Call `_update_plot_refresh_label()` at the end of `_on_refresh_timer`.

3. **Hook label updates to changes in the configured interval**

   - In `_apply_refresh_settings`, also update the label with the **target** refresh rate,
     even before any samples are received:

     ```python
     def _apply_refresh_settings(self):
         interval_ms = self._refresh_interval_ms
         self._refresh_timer.setInterval(interval_ms)
         if interval_ms > 0:
             target_hz = 1000.0 / interval_ms
             self._plot_refresh_label.setText(
                 f"Plot refresh (target): {target_hz:4.1f} Hz"
             )
         else:
             self._plot_refresh_label.setText("Plot refresh: paused")
     ```

   - Once actual samples arrive and `_on_refresh_timer` runs, the smoothed value
     can replace the target text (as above).

---

## Part 2 (lightweight): Prepare for shared live buffers

You do **not** need to fully refactor to a shared `LiveDataStore` yet, but we
want to make that refactor easier later.

Implement the following low‑risk preparation steps:

1. **Isolate buffer access behind small helper methods in both tabs**

   In **SignalsTab**:

   - Identify where the ring buffers are created and updated (e.g. on `on_sample_received`).
   - Wrap buffer access in methods such as:

     ```python
     def _get_buffer(self, key: tuple[str, str, str]) -> RingBuffer:
         return self._buffers[key]

     def _ensure_buffer(self, key: tuple[str, str, str], capacity: int) -> RingBuffer:
         ...
     ```

   Do **not** change behaviour; only centralise buffer access.

2. In **FftTab**:

   - Do the same: introduce `_get_buffer` / `_ensure_buffer` helpers.
   - Clearly separate:
     - Code that **writes** samples to buffers from streaming callbacks.
     - Code that **reads** buffers inside the FFT timer callback.

3. **Add a TODO and type alias for shared buffer keys**

   - Create a type alias near where keys are defined, e.g. in a common module or at the top
     of the tabs:

     ```python
     SampleKey = tuple[str, str, str]  # (sensor_key, sensor_id, channel)
     ```

   - Use `SampleKey` instead of repeating the tuple type in both tabs.
   - Add a comment/TODO near this alias noting that the next step is to move these buffers
     into a shared `LiveDataStore` object.

This way, a future refactor can move the **implementation** of `_get_buffer` / `_ensure_buffer`
into a shared module without touching all call sites again.

---

## Behaviour expectations

After your changes:

- The Signals tab should display a **Plot refresh** readout that:
  - Shows a target Hz based on the configured timer interval.
  - Converges to the actual measured refresh rate as the timer runs.
- Users can immediately see whether the GUI is refreshing slower than they expect.
- No regression to existing plotting behaviour in either Signals or FFT tabs.
- Code paths that manipulate ring buffers are slightly more centralised, making later
  refactors safer.

---

## Constraints & style

- No new third‑party dependencies: use `time.monotonic` from the stdlib.
- Do not move large chunks of code between files; keep changes incremental.
- Maintain existing type hints and follow PEP 8 and the existing naming style.
