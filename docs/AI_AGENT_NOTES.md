# AI Agent Notes

## 1. Multi-rate architecture (short summary)

SensePi purposely runs three independent rates. The Pi logger samples sensors at the configured `--rate` (or `sensors.yaml` `sample_rate_hz`) and writes every point to disk when recording. The Pi-to-GUI stream uses `--stream-every` and `--stream-fields` so the logger can forward a lighter subset of samples over SSH without altering what gets recorded. The GUI itself refreshes via the `SignalsTab` QTimer (or manual refresh modes) so plots only redraw as fast as the Qt loop can stay responsive.

Acquisition, streaming, and plotting must stay decoupled: the Pi always records at the full sampling rate even if the stream is sparse, the stream can be throttled to keep bandwidth manageable, and the Qt refresh rate only dictates how often canvases repaint. Keeping these layers independent is what lets operators view trends in real time without jeopardizing data capture or UI responsiveness. When adding new behaviors, never couple GUI pacing to recorder pacing—let the buffer/signal plumbing do the work.

## 2. Buffers and data flow

1. `raspberrypi_scripts/mpu6050_multi_logger.py` samples sensors and optionally writes JSON lines (`timestamp_ns`, `t_s`, `sensor_id`, `ax..gz`, etc.) to stdout while logging to disk.
2. `PiRecorder` (SSH wrapper) starts that logger on the Pi and exposes an iterable of streamed JSON lines back to the desktop app.
3. `RecorderTab` reads the iterator on a worker thread, parses each line into `MpuSample` via `sensepi.sensors.mpu6050.parse_line`, and emits Qt signals: `sample_received(object)` for tabs such as `SignalsTab` and `FftTab`, plus `rate_updated(str, float)` so the UI can show live throughput estimates.
4. Visualization tabs maintain `RingBuffer` instances for recent samples and periodically redraw Matplotlib canvases from those buffers.

AI agents must respect this pipeline. All heavy lifting (SSH, parsing, FFTs) belongs in worker threads or background tasks, not the GUI thread. Tabs should subscribe to `sample_received`, push data into buffers, and let timed redraws pull from those buffers. New sensors or plots should reuse this signal/slot + buffer pattern to avoid tight coupling and blocking operations.

## 3. Performance design principles

**Do**
- Use `RingBuffer` for sliding windows instead of unbounded Python lists.
- Downsample/decimate before plotting large streams so CPU and Matplotlib stay light.
- Keep Matplotlib canvases alive; update data via `Line2D.set_data` and trigger `FigureCanvasQTAgg.draw_idle()`.
- Run heavy I/O, parsing, or FFT work outside the GUI thread (worker threads, async tasks).

**Don’t**
- Call blocking SSH/file/network operations from Qt slots in the main thread.
- Re-create Matplotlib figures/axes/lines for each frame if they can be updated in place.
- Bypass `RecorderTab` to talk directly to the Pi from other tabs; share its iterator/signals instead.

## 4. How to propose changes

- Keep patches small and scoped; prefer extending existing tabs/modules over introducing new frameworks.
- When adding a feature, update the relevant `tab_*.py` file, any `sensors.yaml` or `hosts.yaml` entries, and add/adjust docs under `docs/`.
- For performance-sensitive code, leave lightweight comments explaining non-obvious patterns (e.g., downsampling to keep CPU low).

## 5. Concrete example

```python
from ...core.ringbuffer import RingBuffer
from ...sensors.mpu6050 import MpuSample

class ExampleNewTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buffer = RingBuffer[tuple[float, float]](capacity=5000)
        ...  # set up Matplotlib figure/canvas and QTimer

    @Slot(object)
    def handle_sample(self, sample: object) -> None:
        if not isinstance(sample, MpuSample):
            return
        t_s = float(sample.t_s) if sample.t_s is not None else sample.timestamp_ns * 1e-9
        self._buffer.append((t_s, float(sample.ax)))

    def redraw(self) -> None:
        # Downsample from buffer, update Line2D data, and call draw_idle()
        ...
```

Connect `RecorderTab.sample_received` to `handle_sample`, keep the redraw timer independent of the sample rate, and use the buffer contents for FFTs or additional plots as needed.

## 6. Acceptance criteria

- `docs/AI_AGENT_NOTES.md` (this file) summarizes the multi-rate architecture, buffer flow, and performance constraints.
- After reading it, future AI agents should know to respect the decoupled acquisition/streaming/plotting design, reuse the signal/buffer pipeline, and keep integrations small and well reasoned.
