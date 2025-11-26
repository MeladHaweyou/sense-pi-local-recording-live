# Task 5: Wire Everything Together & Ensure Clean Startup/Shutdown

You are an expert in **Qt application architecture** and **resource management**.

Your job is to:

- Wire together the new components introduced in Tasks 1–4.
- Ensure **clean startup/shutdown** of the data ingestion thread and GUI timers.
- Keep the architecture coherent and maintainable.

This is primarily an **integration and polish** task.

---

## Context

By now, you should have:

1. **Data Ingestion**  
   - `SensorIngestWorker` (`QObject` in a `QThread`) that:
     - Uses `PiRecorder` to read sensor JSON lines over SSH.
     - Parses them into `MpuSample`.
     - Emits `samples_batch` (list of `MpuSample`).

2. **Central Buffer**  
   - `StreamingDataBuffer` (or similar):
     - Owned by `RecorderTab`.
     - Receives batches via `RecorderTab._on_samples_batch`.
     - Exposes methods like `get_recent_samples(sensor_id, seconds)` and `get_all_sensor_ids()`.

3. **GUI Tabs**  
   - `SignalsTab`:
     - Has a `QTimer` updating at ~10 Hz.
     - Pulls from `RecorderTab.data_buffer()` in `_update_plots_from_buffer`.
   - `FftTab`:
     - Has a `QTimer` updating at ~5–10 Hz.
     - Pulls from `RecorderTab.data_buffer()` in `_update_fft_from_buffer`.

The remaining work is to ensure the **lifecycle** is correct:

- Data ingestion thread starts/stops with recording.
- Timers start/stop appropriately.
- Everything is cleaned up when the app exits or the user stops recording.

---

## Requirements

1. **RecorderTab as central orchestrator**
   - Owns:
     - `PiRecorder` instance.
     - `SensorIngestWorker` instance.
     - `QThread` for ingestion.
     - `StreamingDataBuffer` instance.
   - Emits high-level signals, e.g.:
     - `recording_started`
     - `recording_stopped`
     - `recording_error(str)`

2. **Start sequence**
   - When the user clicks “Start recording” (or equivalent):
     1. Instantiate `PiRecorder` as before.
     2. Create `StreamingDataBuffer` (if not already created in `__init__`).
     3. Create `QThread` and `SensorIngestWorker`.
     4. Move worker to thread, connect signals:
        - `QThread.started -> worker.start`
        - `worker.samples_batch -> RecorderTab._on_samples_batch`
        - `worker.error -> RecorderTab._on_ingest_error`
        - `worker.finished -> RecorderTab._on_ingest_finished`
     5. `worker.finished -> thread.quit`, `thread.finished -> thread.deleteLater`.
     6. Start the thread.
     7. Emit `recording_started` so `SignalsTab` and `FftTab` can start their timers.

3. **Stop sequence**
   - When the user clicks “Stop recording”:
     1. Request the worker to stop (`worker.stop()`).
     2. Optionally call `thread.quit()` and `thread.wait()` if needed.
     3. Stop timers in `SignalsTab` and `FftTab` via `recording_stopped` signal.
     4. Clean up references (`_worker = None`, `_data_thread = None`, `_recorder = None`).

4. **Error handling**
   - If `SensorIngestWorker` emits an error:
     - Log it and optionally show a message to the user.
     - Decide whether to stop recording automatically or allow it to continue.
     - If it results in stopping, also emit `recording_stopped`.

5. **Application shutdown**
   - When the main window is closing:
     - Ensure recording is stopped cleanly.
     - This might involve overriding `closeEvent` in the main window to call `RecorderTab.stop_recording()` and wait for the thread to finish.

---

## Suggested Wiring Sketch in `RecorderTab`

### 1. RecorderTab structure

```python
from PySide6.QtCore import QThread, Signal

from sensepi.remote.pi_recorder import PiRecorder
from sensepi.remote.sensor_ingest_worker import SensorIngestWorker
from sensepi.data.stream_buffer import StreamingDataBuffer, BufferConfig
from sensepi.models import MpuSample  # adjust import

class RecorderTab(QWidget):
    recording_started = Signal()
    recording_stopped = Signal()
    recording_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recorder: PiRecorder | None = None
        self._data_thread: QThread | None = None
        self._ingest_worker: SensorIngestWorker | None = None
        self._data_buffer = StreamingDataBuffer(BufferConfig(
            max_seconds=5.0,
            sample_rate_hz=200.0,
        ))
        # init UI, buttons etc.

    # --- Public API used by other tabs ---

    def data_buffer(self) -> StreamingDataBuffer:
        return self._data_buffer
```

### 2. Start recording

```python
    def start_recording(self) -> None:
        if self._data_thread is not None:
            # Already running
            return

        try:
            self._recorder = PiRecorder(...)
        except Exception as exc:
            self.recording_error.emit(str(exc))
            return

        self._data_thread = QThread(self)
        self._ingest_worker = SensorIngestWorker(
            self._recorder,
            batch_size=50,
            max_latency_ms=100,
        )
        self._ingest_worker.moveToThread(self._data_thread)

        # Thread and worker connections
        self._data_thread.started.connect(self._ingest_worker.start)
        self._ingest_worker.samples_batch.connect(self._on_samples_batch)
        self._ingest_worker.error.connect(self._on_ingest_error)
        self._ingest_worker.finished.connect(self._on_ingest_finished)

        self._ingest_worker.finished.connect(self._data_thread.quit)
        self._data_thread.finished.connect(self._data_thread.deleteLater)

        self._data_thread.start()
        self.recording_started.emit()
```

### 3. Stop recording

```python
    def stop_recording(self) -> None:
        if self._ingest_worker is not None:
            self._ingest_worker.stop()

        if self._data_thread is not None:
            # Optionally, wait for it to finish
            self._data_thread.quit()
            self._data_thread.wait()

        self._ingest_worker = None
        self._data_thread = None

        # Optionally close recorder
        if self._recorder is not None:
            try:
                self._recorder.close()
            except Exception:
                pass
            self._recorder = None

        self.recording_stopped.emit()
```

### 4. Batch handling and error/finished handlers

```python
    def _on_samples_batch(self, samples: list[MpuSample]) -> None:
        # Main thread: push into buffer
        self._data_buffer.add_samples(samples)

    def _on_ingest_error(self, message: str) -> None:
        # Log / show error
        print("Ingest error:", message)
        self.recording_error.emit(message)
        # Decide if this should stop recording
        # self.stop_recording()

    def _on_ingest_finished(self) -> None:
        # Worker signaled completion; ensure state is consistent
        self._ingest_worker = None
        # The thread will be quit/deleted via signals already set up
```

Adapt exception handling and policies (whether to auto-stop recording on error) according to project needs.

---

## Wiring GUI Tabs

Assuming your main window or some controller creates the tabs and passes `RecorderTab` into `SignalsTab` and `FftTab`:

```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.recorder_tab = RecorderTab(self)
        self.signals_tab = SignalsTab(self.recorder_tab, self)
        self.fft_tab = FftTab(self.recorder_tab, self)

        # maybe organize them in a QTabWidget
```

`SignalsTab` and `FftTab` should already be wired (from Tasks 3 & 4) to:

- `recorder_tab.recording_started.connect(tab.start_updates)`
- `recorder_tab.recording_stopped.connect(tab.stop_updates)`

Ensure that:

- **Start/Stop buttons** on `RecorderTab` call `start_recording()` / `stop_recording()`.
- Tabs start/stop their timers based on `recording_started`/`recording_stopped`.

---

## Application Shutdown

If the main window has a `closeEvent`, ensure it stops recording cleanly:

```python
class MainWindow(QMainWindow):
    def closeEvent(self, event: QCloseEvent) -> None:
        # Make sure recording thread is stopped
        self.recorder_tab.stop_recording()
        super().closeEvent(event)
```

This prevents background threads from lingering after the window is closed.

---

## What to Implement

1. Finalize `RecorderTab` as the **orchestrator** for:
   - PiRecorder creation/destruction.
   - SensorIngestWorker + QThread lifecycle.
   - StreamingDataBuffer ownership.
   - Emitting recording lifecycle signals.

2. Ensure `SignalsTab` and `FftTab` start and stop their timers based on `RecorderTab` signals.

3. Add or refine application-level shutdown code so that recording is always stopped cleanly when the app exits.

4. Clean and minimal error handling so failures in ingestion are surfaced without crashing the GUI.

Focus on **integration and lifecycle correctness**. Avoid changing the core logic of ingestion, buffering, or plotting beyond what is necessary to wire them together.
