# AI Prompt 07 – Network Jitter Handling & Resilience

You are an AI coding assistant working on the **Sensors recording and plotting** project.
Implement mechanisms in the PC side to make the system robust against **network jitter, temporary stalls, and end-of-stream conditions**.

## Goals

- Ensure the GUI remains responsive even when data arrival is irregular.
- Avoid plot “explosions” or mis-timed data due to bursts.
- Clearly indicate when the stream has paused or stopped.

## Constraints & Design

- Data ingestion: background reader thread that appends to ring buffers.
- GUI: QTimer-driven plotting and FFT.
- Use **sensor timestamps** (`t_s`) for x-axis, not PC receive time.

## Tasks

1. In the stream reader:
   - Detect EOF or connection loss.
   - Set a shared flag or emit a Qt signal to inform the GUI.
2. In `SignalsTab.update_plot()`:
   - If `latest_timestamp_ns` hasn’t changed for longer than some threshold (e.g. 2 seconds):
     - Optionally show a “No data / stream paused” message in the UI.
     - Avoid extrapolating bogus data.
3. Consider a **small display lag** buffer (optional):
   - Instead of plotting up to `latest_ns`, plot up to `latest_ns - slack_ns` (e.g. 50 ms) to absorb short jitter.
4. Ensure that bursts are rendered smoothly:
   - Since plotting is timer-based, simply plotting the current ring buffer state each tick will naturally smooth bursts.
   - No need to draw multiple frames per burst; only latest state matters.

## Important Code Skeleton (Python)

```python
import time
from PySide6.QtCore import Signal, QObject

class StreamStatus(QObject):
    stream_stopped = Signal()

status = StreamStatus()
last_data_time_monotonic = 0.0

def reader_loop(stream):
    global last_data_time_monotonic
    for line in stream:
        # ... parse, append to buffers ...
        last_data_time_monotonic = time.monotonic()
    # EOF reached
    status.stream_stopped.emit()

class SignalsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_data_timestamp_ns = None
        self.display_slack_ns = int(0.05 * 1e9)  # 50 ms
        status.stream_stopped.connect(self.on_stream_stopped)

    def update_plot(self):
        latest_ns = self._compute_latest_ns()
        if latest_ns is None:
            # clear or show "waiting"
            return

        # detect stale data
        now_mono = time.monotonic()
        if now_mono - last_data_time_monotonic > 2.0:
            # show "no recent data"
            # e.g., update a QLabel in the UI
            pass

        # apply optional slack
        effective_latest = latest_ns - self.display_slack_ns
        t_start_ns = effective_latest - int(self.time_window_s * 1e9)

        # ... fetch window from buffers and update lines as usual ...

    def on_stream_stopped(self):
        # update UI to indicate stream is finished
        # optionally stop timers
        self.timer.stop()
```

## Notes for the AI

- Use Qt’s signal/slot mechanism to safely communicate stream status between threads.
- Keep user feedback clear but non-intrusive (e.g., subtle status bar text).
