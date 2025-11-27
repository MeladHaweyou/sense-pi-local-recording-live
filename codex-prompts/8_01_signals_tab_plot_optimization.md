
# Prompt: Refactor `SignalPlotWidget` for high-performance live plotting

You are an expert in **PySide6 + Matplotlib real-time plotting** and you are editing an existing project.

## Project context

- Repository root example: `sense-pi-local-recording-live-main/`
- GUI entry point: `main.py` → `sensepi.gui.application`
- Live plotting tab: `src/sensepi/gui/tabs/tab_signals.py`
- The main live plot widget is `SignalPlotWidget`, embedded in `SignalsTab`.

Currently, `SignalPlotWidget.redraw()` **re-creates all axes and lines on every timer tick**, which is slow and causes stutter at higher refresh rates.

### Current simplified implementation (excerpt)

File: `src/sensepi/gui/tabs/tab_signals.py`

```python
class SignalPlotWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None, max_seconds: float = 10.0):
        super().__init__(parent)

        self._max_seconds = float(max_seconds)
        self._max_rate_hz = 500.0
        # key = (sensor_id, channel)  -> RingBuffer[(t, value)]
        self._buffers: Dict[Tuple[int, str], RingBuffer[Tuple[float, float]]] = {}
        self._buffer_capacity = max(1, int(self._max_seconds * self._max_rate_hz))

        # Channels currently visible & their preferred order (columns)
        self._visible_channels: Set[str] = set()
        self._channel_order: list[str] = []

        # Appearance
        self._line_width: float = 0.8  # thinner than Matplotlib default

        # Optional base-correction (per sensor/channel)
        self._base_correction_enabled: bool = False
        self._baseline_offsets: Dict[Tuple[int, str], float] = {}

        self._figure = Figure(figsize=(6, 6), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)

        layout = QVBoxLayout(self)
        layout.addWidget(self._canvas)

    def redraw(self) -> None:
        """Refresh the Matplotlib plot (intended to be driven by a QTimer)."""
        # Determine which channels are visible (columns)
        visible_channels = [
            ch for ch in self._channel_order if ch in self._visible_channels
        ]
        if not visible_channels:
            self._figure.clear()
            self._canvas.draw_idle()
            return

        # Active buffers that actually have data
        active_buffers = [
            buf
            for (sid, ch), buf in self._buffers.items()
            if ch in visible_channels and len(buf) > 0
        ]
        if not active_buffers:
            self._figure.clear()
            self._canvas.draw_idle()
            return

        latest = max(buf[-1][0] for buf in active_buffers)
        cutoff = max(0.0, latest - self._max_seconds)

        sensor_ids = sorted(
            {
                sid
                for (sid, ch) in self._buffers.keys()
                if ch in visible_channels
            }
        )
        if not sensor_ids:
            self._figure.clear()
            self._canvas.draw_idle()
            return

        nrows = len(sensor_ids)
        ncols = len(visible_channels)

        self._figure.clear()

        for row_idx, sid in enumerate(sensor_ids):
            for col_idx, ch in enumerate(visible_channels):
                subplot_index = row_idx * ncols + col_idx + 1
                ax = self._figure.add_subplot(nrows, ncols, subplot_index)

                buf = self._buffers.get((sid, ch))
                if buf is None or len(buf) == 0:
                    ax.set_visible(False)
                    continue

                points = [(t, v) for (t, v) in buf if t >= cutoff]
                if not points:
                    ax.set_visible(False)
                    continue

                times = [t - cutoff for (t, v) in points]
                raw_values = [v for (_t, v) in points]

                offset = 0.0
                if self._base_correction_enabled:
                    offset = self._baseline_offsets.get((sid, ch), 0.0)
                values = [v - offset for v in raw_values]

                ax.plot(times, values, linewidth=self._line_width)
                # ... labels, grid, tight_layout() etc. ...
```

## Goal

Refactor `SignalPlotWidget` to use a **pre-created grid of axes and Line2D objects** that are **reused** on each redraw, instead of clearing and re-plotting from scratch.

Key requirements:

1. **Initialization phase**:
   - Create a mapping:
     - `self._axes[(sensor_id, channel)] -> matplotlib.axes.Axes`
     - `self._lines[(sensor_id, channel)] -> matplotlib.lines.Line2D`
   - Axes grid shape (rows/cols) is based on:
     - Distinct `sensor_id`s present in `_buffers`
     - Active `visible_channels` (from `_channel_order` + `_visible_channels`)
   - Create default axes/lines lazily (on first redraw) and reuse thereafter.

2. **Per-frame update (in `redraw`)**:
   - Do **not** call `figure.clear()` or recreate subplots for the common case.
   - For each `(sensor_id, channel)` that has data:
     - Extract `points` from `RingBuffer`.
     - Update the corresponding `Line2D` via `.set_data(times, values)`.
     - Optionally adjust axes limits with `ax.relim()` / `ax.autoscale_view()`.
   - Only when the grid layout (rows/cols) truly changes (e.g., number of sensors or visible channels changes), rebuild axes once, not every frame.

3. **Performance**:
   - Continue using `self._canvas.draw_idle()` instead of `draw()` directly.
   - Avoid `tight_layout()` on every frame; run it only when axes are (re)created.
   - Try to keep allocations small in `redraw` (reusing lists/arrays where practical).

4. **Behaviour**:
   - Preserve the visual behaviour: one row per sensor, one column per visible channel.
   - Preserve axis labels, titles, and grid behaviour as much as possible.
   - Keep base correction (`_base_correction_enabled` and `_baseline_offsets`) working.

## Tasks for you

1. Implement a **line/axes caching mechanism** in `SignalPlotWidget`:
   - Introduce `self._axes_map: Dict[Tuple[int, str], Axes]` and `self._lines_map: Dict[Tuple[int, str], Line2D]`.
   - Provide a helper like `_ensure_axes_and_line(sensor_ids, visible_channels)` that:
     - Checks if the grid layout matches the current set.
     - If not, rebuilds the figure and axes once and updates the maps.
2. Update `redraw()` to:
   - Use `_axes_map` and `_lines_map`.
   - Only call `ax.plot(...)` at axes creation time; use `line.set_data(...)` later.
   - Only resize/redraw axes when strictly necessary.
3. Make sure it integrates cleanly with the rest of `SignalsTab`:
   - `SignalsTab._on_channel_toggles_changed()` calls `self._plot.set_visible_channels(visible)`.
   - Changing visible channels should cause a grid rebuild on the next redraw.
4. Keep the public API of `SignalPlotWidget` the same:
   - `add_sample(sample: MpuSample)` should remain unchanged.
   - `enable_base_correction()`, `calibrate_from_buffer()`, etc., should continue to work.

## Deliverables

- A patch to `src/sensepi/gui/tabs/tab_signals.py` that:
  - Introduces caching of axes/lines.
  - Updates `redraw()` as described.
- Any small helper methods or private attributes you need.
- Comments in code explaining when axes are rebuilt vs reused.

Please produce final code that can be dropped directly into `tab_signals.py` with minimal adaptation.
