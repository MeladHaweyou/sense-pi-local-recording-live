# Task 1: Implement Sensor Data Ingestion Thread with Batched Qt Signals

You are an expert **PySide6/Qt** and **real-time data streaming** developer.

Your job is to refactor the existing sensor data ingestion so that it runs in a **dedicated worker thread** and emits **batched Qt signals** instead of per-sample signals, following the concurrency design described below.

---

## Context

The project already has:

- `PiRecorder` in `src/sensepi/remote/pi_recorder.py`  
  - Uses **Paramiko** to connect to a Raspberry Pi and run a logger.
  - Exposes a way to iterate JSON lines from the remote process.
- A GUI built with **PySide6**, including:
  - `RecorderTab` — manages starting/stopping the recording and interacts with `PiRecorder`.
  - `SignalsTab` — plots time-domain data.
  - `FftTab` — plots FFT of recent data.
- A data class `MpuSample` (possibly in `src/sensepi/...`) that parses/represents a single sensor sample.

The **current pattern** is roughly:

- A worker thread iterates JSON lines from `PiRecorder`.
- Each line is parsed into an `MpuSample`.
- The worker emits **one Qt signal per sample** to update GUI tabs.

We want to change this so that:

1. The data ingestion runs in a **QObject-based worker** moved to a `QThread`.
2. The worker **batches samples** and emits them as a **list of `MpuSample`** objects.
3. The GUI no longer receives per-sample signals; instead, it will use a **shared buffer** and **timers** (handled in separate tasks).

---

## Requirements

Implement a new ingestion component with these properties:

1. **Worker object** (e.g. `SensorIngestWorker`) that:
   - Lives in its own `QThread` (created/owned by `RecorderTab` or similar).
   - Takes a `PiRecorder` instance, a `batch_size`, and optionally a `max_latency_ms`.
   - Iterates over the JSON line stream from `PiRecorder`.
   - Parses each line into an `MpuSample`.
   - Accumulates samples into a local buffer.
   - Emits a **batched signal** whenever:
     - `len(buffer) >= batch_size`, or
     - more than `max_latency_ms` has passed since the last emit.
2. **Qt signals/slots**:
   - A signal like:
     ```python
     samples_batch = Signal(list)  # list[MpuSample]
     ```
   - A slot to start the reading loop (called when the `QThread` starts).
   - A way to request a clean shutdown from the GUI thread.
3. **Thread safety / Qt rules**:
   - No direct GUI calls from the worker.
   - Use Qt signals to communicate with the GUI.
   - Ensure clean shutdown: stop the reading loop, close the SSH stream, quit the thread, and wait for it to finish.

You may create a new module, for example:

- `src/sensepi/remote/sensor_ingest_worker.py`

or another suitable location that fits the current project layout.

---

## Key Integration Sketch

### 1. Worker class skeleton (in a new module)

Use this skeleton as the starting point; keep API names compatible but feel free to adjust specifics as needed to match the project:

```python
# src/sensepi/remote/sensor_ingest_worker.py

from PySide6.QtCore import QObject, Signal, Slot
from collections import deque
import time

from .pi_recorder import PiRecorder
from ..models import MpuSample  # adjust import to real location


class SensorIngestWorker(QObject):
    samples_batch = Signal(list)   # list[MpuSample]
    error = Signal(str)
    finished = Signal()

    def __init__(self, recorder: PiRecorder, batch_size: int = 50,
                 max_latency_ms: int = 100, parent: QObject | None = None):
        super().__init__(parent)
        self._recorder = recorder
        self._batch_size = batch_size
        self._max_latency_ms = max_latency_ms
        self._running = False

    @Slot()
    def start(self) -> None:
        """Entry point for the QThread: read the stream and emit batches."""
        self._running = True
        buffer: list[MpuSample] = []
        last_emit = time.monotonic()

        try:
            for line in self._recorder.iter_lines():
                if not self._running:
                    break

                if not line:
                    continue

                try:
                    sample = MpuSample.from_json(line)
                except Exception as exc:  # be more specific if possible
                    # You might want to log this instead of stopping everything.
                    self.error.emit(f"Failed to parse sample: {exc}")
                    continue

                buffer.append(sample)

                now = time.monotonic()
                latency_ms = (now - last_emit) * 1000.0

                if len(buffer) >= self._batch_size or latency_ms >= self._max_latency_ms:
                    # Emit a *copy* in case the receiver keeps it.
                    self.samples_batch.emit(list(buffer))
                    buffer.clear()
                    last_emit = now

            # Flush any remaining samples on exit
            if buffer:
                self.samples_batch.emit(list(buffer))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self._running = False
            try:
                self._recorder.close()
            except Exception:
                pass
            self.finished.emit()

    @Slot()
    def stop(self) -> None:
        """Request graceful shutdown from GUI thread."""
        self._running = False
```

### 2. Starting the worker in `RecorderTab`

In `RecorderTab` (or the equivalent controller), set up the QThread and worker like this:

```python
# inside RecorderTab.__init__ or a setup method
from PySide6.QtCore import QThread

from sensepi.remote.pi_recorder import PiRecorder
from sensepi.remote.sensor_ingest_worker import SensorIngestWorker

class RecorderTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data_thread: QThread | None = None
        self._ingest_worker: SensorIngestWorker | None = None
        # ... rest of setup ...

    def start_recording(self) -> None:
        # Create PiRecorder as you currently do
        self._recorder = PiRecorder(...)

        self._data_thread = QThread(self)
        self._ingest_worker = SensorIngestWorker(self._recorder, batch_size=50, max_latency_ms=100)
        self._ingest_worker.moveToThread(self._data_thread)

        # When the thread starts, call worker.start()
        self._data_thread.started.connect(self._ingest_worker.start)

        # Connect worker outputs to RecorderTab slots (to be implemented in another task)
        self._ingest_worker.samples_batch.connect(self._on_samples_batch)
        self._ingest_worker.error.connect(self._on_ingest_error)
        self._ingest_worker.finished.connect(self._on_ingest_finished)

        # Ensure worker and thread get cleaned up
        self._ingest_worker.finished.connect(self._data_thread.quit)
        self._data_thread.finished.connect(self._data_thread.deleteLater)
        self._data_thread.start()

    def stop_recording(self) -> None:
        if self._ingest_worker is not None:
            self._ingest_worker.stop()
        # Optionally wait for thread to finish; this may be done in a separate method.

    def _on_samples_batch(self, samples: list[MpuSample]) -> None:
        """Will be implemented in Task 2: push to central buffer, not directly to plots."""
        pass

    def _on_ingest_error(self, message: str) -> None:
        # Log or show error
        print("Ingest error:", message)

    def _on_ingest_finished(self) -> None:
        # Cleanup references, update UI state, etc.
        self._ingest_worker = None
        self._data_thread = None
```

**Important:** Do not wire `samples_batch` directly to plotting slots. Instead, `RecorderTab._on_samples_batch` will push samples into a shared ring buffer (implemented in Task 2) which the GUI plots will read from on a fixed timer.

---

## What to Implement

1. Add a `SensorIngestWorker` (or similarly named) class, as above, in its own module.
2. Integrate it into `RecorderTab`:
   - Create the `QThread` and worker.
   - Connect signals/slots as in the sketch.
   - Start/stop the worker when the user starts/stops recording.
3. Ensure the implementation works with **multiple sensors and channels** without blocking the UI.
4. Do **not** modify GUI plotting code in this task; just adapt the data ingestion mechanism.

Focus on correct **Qt threading**, **batched signal emission**, and **clean shutdown**. Leave the central buffer and plot updates to the following tasks.
