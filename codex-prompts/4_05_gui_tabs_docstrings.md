# SensePi teaching comments – GUI tabs (Signals, FFT, Recorder)

Files:
- `src/sensepi/gui/tabs/tab_signals.py`
- `src/sensepi/gui/tabs/tab_fft.py`
- `src/sensepi/gui/tabs/tab_recorder.py`

The goal is to clarify how the GUI stays responsive via timers, queues, and shared buffers,
without modifying any behaviour.

## General rules

- Only touch comments and docstrings; no logic changes.
- Keep comments to 1–3 lines and focused on *why* something is done.
- If a similar explanation already exists in a nearby comment/docstring, just refine it.

---

## 1. `SignalsTab.update_stream_rate` – tie GUI rate to Pi `--stream-every`

In `tab_signals.py`, there is an `update_stream_rate` slot that already updates a label and calls
`set_nominal_sample_rate` on the plot widget. If the docstring does not yet mention Pi-side decimation,
adjust it to something like:

```python
    @Slot(str, float)
    def update_stream_rate(self, sensor_type: str, hz: float) -> None:
        """Update the GUI-side stream rate shown in the Signals tab.

        ``hz`` reflects the effective rate at which samples arrive in the GUI
        after any Pi-side stream decimation (for example, mpu6050 --stream-every N).
        """
        ...
```

If a similar explanation is already present, keep the wording but ensure it clearly mentions
that this is the post-decimation rate seen by the GUI.

---

## 2. `SignalsTab._refresh_timer_state` – explain when the redraw timer runs

In `tab_signals.py`, locate `_refresh_timer_state`:

```python
    def _refresh_timer_state(self) -> None:
        """Start or stop the plot timer depending on stream activity."""
        if not hasattr(self, "_timer"):
            return
        should_run = self._stream_active or self._synthetic_active
        if should_run:
            if self._timer.isActive():
                ...
```

Edit: If the docstring is shorter or missing, update it to:

```python
    def _refresh_timer_state(self) -> None:
        """Start/stop the redraw timer based on live or synthetic stream activity."""
        ...
```

And add a brief comment before computing `should_run`:

```python
        # Only tick the GUI timer while we have real or synthetic data;
        # pausing it avoids wasting CPU when no stream is active.
        should_run = self._stream_active or self._synthetic_active
```

---

## 3. `SignalsTab._drain_samples` – describe decoupling via `sample_queue`

Still in `tab_signals.py`, find `_drain_samples`:

```python
    def _drain_samples(self) -> None:
        """Drain queued samples from RecorderTab and append them to the plots."""
        if not self._stream_active and not self._synthetic_active:
            return

        queue_obj = self._recorder_sample_queue() if self._stream_active else None
        if queue_obj is None:
            ...
```

Edit: Add this 2-line comment just before the `drained: list[object] = []` block:

```python
        # Pull as many samples as are currently queued by RecorderTab; this keeps
        # ingest work in short bursts driven by the GUI timer instead of per-sample.
        drained: list[object] = []
```

Leave all queue logic as it is.

---

## 4. `SignalsTab.update_plot` – explain stall detection vs redraw

In `tab_signals.py`, locate `update_plot` (the slot called by `_on_redraw_timer`). It contains logic that
checks `_last_data_monotonic` and toggles a “No recent data” status before calling `self._plot.redraw()`.

Edit: At the top of `update_plot`, just after the docstring, add:

```python
        # First update the stream status (waiting / stalled / streaming),
        # then ask the plotting backend to redraw the latest buffered data.
```

Do not touch the underlying logic.

---

## 5. `FftTab._update_fft_timer_interval` – link window length to refresh cadence

In `tab_fft.py`, locate `_update_fft_timer_interval`:

```python
    def _update_fft_timer_interval(self, *_: object) -> None:
        """Adjust the FFT refresh cadence based on the selected window length."""
        timer = getattr(self, "_timer", None)
        if timer is None:
            return
        ...
```

If the above docstring is not already present, add or update it to exactly that wording.
No further comments needed here – the key message is that longer windows imply slower refresh.

---

## 6. `FftTab._get_buffer_window` – call out reuse of SignalsTab buffers

In `tab_fft.py`, find `_get_buffer_window`:

```python
    def _get_buffer_window(
        self,
        key: SampleKey,
        *,
        window_s: float,
        data_buffer: StreamingDataBuffer | None = None,
    ) -> tuple[Sequence[float], Sequence[float]]:
        sensor_id, channel = key
        window = self._window_from_signals_tab(sensor_id, channel, window_s)
        if window is not None:
            return window

        buffer = data_buffer or self._active_stream_buffer()
        return buffer.get_axis_series(sensor_id, channel, seconds=window_s)
```

Edit: Add this comment at the top of the method body:

```python
        # Prefer reusing the time-windowed data held by SignalsTab; if that
        # is unavailable, fall back to querying the shared StreamingDataBuffer.
```

---

## 7. `RecorderTab.data_buffer` / `RecorderTab.sample_queue` – document sharing

In `tab_recorder.py`, the following small helpers already exist (or should exist):

```python
    def data_buffer(self) -> StreamingDataBuffer:
        """Return the streaming data buffer for other tabs to query."""
        return self._data_buffer

    @property
    def sample_queue(self) -> queue.Queue[object]:
        """Return the queue carrying recent samples for GUI ingestion."""
        return self._sample_queue
```

If these docstrings are missing or shorter, set them to match the above text. The key points:

- `data_buffer()` is the shared buffer used by Signals and FFT tabs.
- `sample_queue` is the short-term queue drained by `SignalsTab._drain_samples`.

---

After applying these edits, you can run the GUI and watch the Signals/FFT tabs while streaming
to verify that only explanatory text changed and behaviour is unchanged.
