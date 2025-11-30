# SensePi GUI – Make the live “mode hint” explain how to access offline logs

You are an AI pair-programmer working on the SensePi repository.

**Goal:** When users configure a Raspberry Pi host and enable **Recording** in the Signals tab, the short help text under the Start/Stop buttons should explicitly tell them how to retrieve recorded data via the Offline tab.

We’ll do this by extending `SignalsTab._refresh_mode_hint()` in `src/sensepi/gui/tabs/tab_signals.py`.

---

## Context

The `SignalsTab` already has a short explanatory label under the recording controls, managed by `_refresh_mode_hint()`:

- It uses `_remote_destination_text()` and `RecorderTab.current_remote_data_dir()` to describe where data is written on the Pi.
- It distinguishes between “Streaming only” and “Recording enabled”.

Current structure (simplified):

```python
def _refresh_mode_hint(self) -> None:
    label = getattr(self, "_mode_hint_label", None)
    if label is None:
        return
    dest = self._remote_destination_text()
    session = " ".join(self.session_name().split())
    if self.recording_check.isChecked():
        hint = "Recording enabled. "
        if dest:
            hint += f"Data is written to {dest} on the Pi."
        else:
            hint += "Data is written to the configured Pi logs directory."
    else:
        hint = "Streaming only (samples are not stored on the Pi). "
        if dest:
            hint += f"Enable recording to write into {dest}."
    if session:
        hint += f" Session name: {session}."
    label.setText(hint.strip())
    self._update_recording_indicator()
```

We want this label to also mention the Offline tab as the place to **download** and **replay** logs.

---

## Task

Update `_refresh_mode_hint()` so that:

- When **Recording** is enabled, the hint explains that after stopping the stream, the user should open the Offline tab to sync logs and replay the session.
- When **Recording** is not enabled, the behaviour remains the same except for the optional mention of the Offline tab *only if it is helpful* (do not confuse students by suggesting offline logs when nothing is being recorded).

---

## Implementation sketch

In `src/sensepi/gui/tabs/tab_signals.py`, modify `_refresh_mode_hint()` roughly as follows:

```python
def _refresh_mode_hint(self) -> None:
    label = getattr(self, "_mode_hint_label", None)
    if label is None:
        return
    dest = self._remote_destination_text()
    session = " ".join(self.session_name().split())

    if self.recording_check.isChecked():
        hint = "Recording enabled. "
        if dest:
            hint += f"Data is written to {dest} on the Pi."
        else:
            hint += "Data is written to the configured Pi logs directory."

        # NEW: point users to the Offline tab for retrieval.
        hint += (
            " After you stop the stream, open the Offline tab to sync logs "
            "from the Pi and replay this session."
        )
    else:
        hint = "Streaming only (samples are not stored on the Pi). "
        if dest:
            hint += f"Enable recording to write into {dest}."

    if session:
        hint += f" Session name: {session}."

    label.setText(hint.strip())
    self._update_recording_indicator()
```

Details to maintain:

- Keep the existing logic around `dest` and `session` unchanged, only append the new sentence in the “recording enabled” branch.
- Use a single space at the start of the new sentence so spacing remains natural after whatever comes before it.
- Don’t introduce new dependencies or imports.

---

## Acceptance criteria

- When recording is **off**, the hint text remains effectively the same as before (no confusing offline references when nothing will be stored).
- When recording is **on**, the hint explicitly mentions:
  - Data is written on the Pi (with the correct path when available).
  - The **Offline** tab is where logs are synced and replayed after stopping.
- No behaviour change to the actual recording/streaming pipeline—only the explanatory text is updated.
