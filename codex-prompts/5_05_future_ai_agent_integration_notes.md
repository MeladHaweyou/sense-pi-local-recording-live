# Prompt: General Guidelines for Future AI Agent Integration in SensePi

This is a meta-prompt intended to live in the repo as a reference for future AI-assisted changes. It explains key architectural decisions so that subsequent AI agents focus on integration rather than ad-hoc rewrites.

Please create (or update) a short markdown document under `docs/` named `AI_AGENT_NOTES.md` with the following content (fleshed out and adapted as needed).

## 1. Multi-rate architecture (short summary)

Explain in 2–3 paragraphs:

- The three core rates:
  - Pi sampling/recording rate (`--rate`, sensors.yaml `sample_rate_hz`),
  - Pi-to-GUI stream rate (`--stream-every`, `--stream-fields`),
  - GUI refresh rate (`SignalsTab` QTimer / refresh mode).
- The principle that **acquisition, streaming, and plotting** are intentionally decoupled to keep the GUI responsive.

Make explicit that:

- Recording on the Pi should always use the configured full sampling rate.
- The GUI is allowed to see a much lighter stream and a lower refresh rate; this is *by design*.

## 2. Buffers and data flow

Document how live data flows through the system:

1. Pi logger (`mpu6050_multi_logger.py`) samples and optionally streams JSON lines with fields like `timestamp_ns`, `t_s`, `sensor_id`, `ax..gz`.
2. `PiRecorder` (SSH wrapper) runs the logger and exposes an iterable of JSON lines.
3. `RecorderTab` uses a worker thread to read lines, parses them into `MpuSample` via `sensepi.sensors.mpu6050.parse_line`, and emits Qt signals:
   - `sample_received(object)` to `SignalsTab` and `FftTab`.
   - `rate_updated(str, float)` with stream-rate estimates.
4. `SignalsTab` / `FftTab` store recent data in `RingBuffer` instances and periodically redraw their Matplotlib canvases.

Emphasize that:

- AI agents should respect this flow and **avoid introducing tight coupling** or blocking operations in the GUI thread.
- New sensors or visualizations should ideally hook into the same signal/slot + buffer pattern.

## 3. Performance design principles

Include a short bullet list of “dos and don’ts” for AI agents:

- **Do**:
  - Use `RingBuffer` for sliding-window storage instead of unbounded lists.
  - Use decimation/downsampling before plotting large streams.
  - Use `FigureCanvasQTAgg`, `draw_idle()`, and in-place `Line2D.set_data` updates for real-time plots.
  - Keep heavy I/O and CPU work off the GUI thread (use threads, async where appropriate).

- **Don’t**:
  - Don’t call blocking network or file I/O from Qt slots in the main thread.
  - Don’t re-create Matplotlib figures/axes/lines for every frame if it can be avoided.
  - Don’t bypass `RecorderTab` to talk directly to the Pi from other tabs.

## 4. How to propose changes

Describe briefly how future AI agents should structure their changes:

- Prefer **small, well-scoped patches** in existing modules over new frameworks or large rewrites.
- When adding a feature, update:
  - The appropriate `tab_*.py` file,
  - Any config in `sensors.yaml` / `hosts.yaml` if needed,
  - And docs under `docs/`.
- When touching performance-sensitive code, mention in comments why a particular pattern is used (e.g. downsampling to keep CPU low).

## 5. Concrete example

Add at least one example snippet showing an *ideal* future change, e.g. adding a new plot type that subscribes to `sample_received` and uses a `RingBuffer` with decimation. Something like:

```python
from ...core.ringbuffer import RingBuffer
from ...sensors.mpu6050 import MpuSample

class ExampleNewTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buffer = RingBuffer[tuple[float, float]](capacity=5000)
        ...  # set up Matplotlib figure/canvas

    @Slot(object)
    def handle_sample(self, sample: object) -> None:
        if not isinstance(sample, MpuSample):
            return
        t_s = float(sample.t_s) if sample.t_s is not None else sample.timestamp_ns * 1e-9
        self._buffer.append((t_s, float(sample.ax)))

    def redraw(self) -> None:
        # Downsample from buffer, update Line2D, and call draw_idle().
        ...
```

## 6. Acceptance criteria

- `docs/AI_AGENT_NOTES.md` exists and is short (1–2 pages) but clear.
- Future AI agents can read this file and quickly understand:
  - The multi-rate design,
  - The streaming and plotting pipeline,
  - What integration constraints they should respect.

Please generate the full `AI_AGENT_NOTES.md` file content as part of this task and save it in `docs/`. 
