# SensePi GUI – Show an “Offline logs” hint when recording stops

You are an AI pair-programmer working on the SensePi repository.

**Goal:** When a recording run finishes, the main window should:

- Briefly explain (via the status bar) where the logs were saved on the Pi.
- Point the user to the Offline tab as the place to download and inspect logs.
- Optionally bring the Offline tab to the front, so the path “record → offline logs” is obvious.

All wiring should live in `src/sensepi/gui/main_window.py` and reuse the existing signals from `RecorderTab`.

---

## Context

The `MainWindow` currently wires RecorderTab signals to the live tabs like this:

```python
self.recorder_tab.recording_started.connect(
    self.signals_tab.on_stream_started
)
self.recorder_tab.recording_started.connect(
    self.fft_tab.on_stream_started
)

self.recorder_tab.recording_stopped.connect(
    self.signals_tab.on_stream_stopped
)
self.recorder_tab.recording_stopped.connect(
    self.fft_tab.on_stream_stopped
)
```

There is no additional UX hint tying “recording stopped” to “go to Offline tab and download logs”.

The `MainWindow` already owns:

- `self._tabs` – the `QTabWidget` with Signals/FFT/Settings/Offline/Logs.
- `self.offline_tab` – an instance of `OfflineTab(app_paths, self.recorder_tab)`.
- `self.recorder_tab` – which exposes `current_remote_data_dir()` for the recording destination path on the Pi.

---

## Task

1. Connect `RecorderTab.recording_stopped` to a new private slot on `MainWindow`.
2. In that slot:
   - Build a status-bar message explaining where the logs are on the Pi (if known).
   - Mention that the Offline tab is the place to sync and replay logs.
   - Optionally switch to the Offline tab automatically.

Keep the change local to `src/sensepi/gui/main_window.py`.

---

## Step‑by‑step implementation

### 1. Wire the new slot in `__init__`

In `MainWindow.__init__` (same file), extend the existing connections:

```python
self.recorder_tab.recording_stopped.connect(
    self.signals_tab.on_stream_stopped
)
self.recorder_tab.recording_stopped.connect(
    self.fft_tab.on_stream_stopped
)
self.recorder_tab.recording_stopped.connect(
    self._on_recording_stopped
)
```

No `@Slot` decorator is strictly necessary here, since `MainWindow` methods can be used directly as slots.

### 2. Implement `_on_recording_stopped`

Add this method to the `MainWindow` class (near the other private helpers, e.g. `_on_start_stream_requested`):

```python
def _on_recording_stopped(self) -> None:
    """
    Called whenever the RecorderTab signals that a recording/stream run
    has finished.

    Shows a short hint in the status bar and nudges users toward the
    Offline tab, where they can download and inspect the recorded logs.
    """
    # Ensure the main window has a status bar; QMainWindow lazily creates it.
    status = self.statusBar()

    # Try to describe the remote data directory, if available.
    try:
        remote_dir = self.recorder_tab.current_remote_data_dir()
    except AttributeError:
        remote_dir = None

    if remote_dir is not None:
        dest_text = remote_dir.as_posix()
        msg = (
            f"Recording stopped. Logs were written to {dest_text} on the Pi. "
            "Open the Offline tab to sync logs and replay this session."
        )
    else:
        msg = (
            "Recording stopped. Open the Offline tab to sync logs from the Pi "
            "and replay previous sessions."
        )

    # Show the message for a few seconds.
    status.showMessage(msg, 8000)

    # Optional: bring the Offline tab into focus so the path is obvious.
    try:
        idx = self._tabs.indexOf(self.offline_tab)
    except Exception:
        idx = -1
    if idx >= 0:
        self._tabs.setCurrentIndex(idx)
```

Notes:

- `current_remote_data_dir()` is already used elsewhere (e.g. in `SignalsTab._remote_destination_text`) and returns a `Path`-like object for the remote logs directory.
- We don’t introduce new imports; we reuse `self.statusBar()` from `QMainWindow`.

If you want to make the automatic tab switch configurable later, you can factor the last block into a helper (e.g. `_focus_offline_tab_if_available`) and guard it behind a config flag. For now, it’s acceptable to always switch to the Offline tab on stop to make the workflow obvious to learners.

---

## Acceptance criteria

- When a recording/stream run ends (either normally or because the ingest worker stops), the user sees a status-bar message that:
  - Mentions the remote Pi logs directory if available.
  - Mentions the Offline tab as the place to sync and replay logs.
- Immediately after stop, the Offline tab becomes the active tab in the main window.
- No changes to how stream start/stop behaves in Signals/FFT beyond this hint and tab focus.
