# Prompt: Add Matplotlib Performance Tuning for Real-Time Plots

You are working inside the **SensePi** repository, which uses Matplotlib via `FigureCanvasQTAgg` embedded in PySide6 widgets (`SignalsTab`, `FftTab`, `OfflineTab`). The goal of this task is to:

- Apply **global Matplotlib performance settings** suitable for real-time updating plots.
- Update the time-domain and FFT tabs to use **more efficient redraw patterns** where possible.

Focus on *integration*: keep the current UI and layout, but reduce CPU cost of redraws.

Relevant files:

- `src/sensepi/gui/application.py`
- `src/sensepi/gui/tabs/tab_signals.py`
- `src/sensepi/gui/tabs/tab_fft.py`
- `src/sensepi/tools/plotter.py` (for reference on current plotting style)

## 1. Add a shared Matplotlib configuration helper

Create a new helper function that configures Matplotlib for “fast-ish” real-time drawing. Place it in a module that is imported early; `src/sensepi/gui/application.py` is a good candidate.

### Step 1: Add helper

In `src/sensepi/gui/application.py`, add:

```python
import matplotlib as mpl

def configure_matplotlib_for_realtime() -> None:
    """
    Apply global Matplotlib tweaks that improve interactive / real-time performance.

    This should be called once before any figures are created.
    """
    # Prefer a fast style; this is a lightweight style that can be combined
    # with others if needed.
    try:
        mpl.style.use("fast")
    except Exception:
        # If the style is missing, just continue with defaults.
        pass

    rc = mpl.rcParams

    # Enable path simplification (reduces number of points actually drawn)
    rc["path.simplify"] = True
    rc["path.simplify_threshold"] = 0.2  # balance performance vs. fidelity

    # Chunk long paths so rendering can be interrupted/coalesced
    rc["agg.path.chunksize"] = 10000

    # General sensible defaults for real-time views
    rc["axes.grid"] = True
    rc["figure.autolayout"] = True
```

### Step 2: Call the helper once

Still in `application.py`, inside `create_app` before creating any windows/figures, call the helper:

```python
from .application import configure_matplotlib_for_realtime  # adjust import if needed

def create_app(argv: list[str] | None = None) -> Tuple[QApplication, QMainWindow]:
    ...
    # Make sure Matplotlib is tuned for interactive use
    configure_matplotlib_for_realtime()

    app = QApplication.instance() or QApplication(qt_args)
    window = MainWindow()
    return app, window
```

(Adjust imports to avoid circular references; if needed, move the helper into a small new module under `sensepi.gui` like `gui/mpl_config.py` and import from there.)

## 2. Use `draw_idle()` instead of full redraw where appropriate

In both `SignalPlotWidget` and `FftTab`, canvases are currently updated via `self._canvas.draw_idle()` in some places. Ensure that:

- You **always** use `draw_idle()` instead of `draw()` for timer-driven updates.
- There are no leftover full `draw()` calls in normal live-update paths.

Search for any `draw()` calls on the canvas in:

- `tab_signals.py`
- `tab_fft.py`
- `tab_offline.py` (offline plots can keep using `draw()` if only updated on file load, but `draw_idle()` is also fine).

Adjust to:

```python
self._canvas.draw_idle()
```

unless the context specifically requires a synchronous, immediate redraw (which is rare in this GUI).

## 3. Prepare for optional blitting (future-friendly)

You do **not** need to fully implement Matplotlib blitting in this task, but do some small refactors that make it possible later:

1. In `SignalPlotWidget.redraw`, instead of calling `ax.plot(...)` every time, keep a dictionary of `Line2D` objects keyed by `(sensor_id, channel)` and update their data in place.

   - Add an attribute:

     ```python
     from matplotlib.lines import Line2D

     self._lines: Dict[Tuple[int, str], Line2D] = {}
     ```

   - When creating subplots in `redraw`, for each `(sid, ch)`:

     ```python
     key = (sid, ch)
     line = self._lines.get(key)

     if line is None:
         (line_obj,) = ax.plot(times_dec, values_dec, linewidth=self._line_width)
         self._lines[key] = line_obj
     else:
         line.set_data(times_dec, values_dec)
     ```

   - Ensure the x-limits are updated based on the current window:

     ```python
     if times_dec:
         ax.set_xlim(times_dec[0], times_dec[-1])
     ```

   - For y-limits, you can rely on `ax.relim()` / `ax.autoscale_view()` or manually set them based on min/max of `values_dec`.

   - Only clear the figure when necessary (e.g. when no sensor_ids). If possible, avoid `self._figure.clear()` on every redraw; instead, reuse axes and lines. If that refactor becomes too intrusive, keep using `clear()` but still manage lines in a dictionary so that later blitting is easier.

2. Apply a similar pattern in `FftTab` (`_update_mpu6050_fft` and `_update_generic_fft`):

   - Add `self._fft_lines: Dict[Tuple[str, int, str], Line2D] = {}` in `__init__`.
   - Use `set_data()` for existing lines, and only create new `Line2D` if it doesn’t exist yet.

This change keeps the **public behaviour identical** but reduces per-frame allocations of new `Line2D` objects, paving the way for efficient blitting later.

## 4. Acceptance criteria

- Application still starts and plots correctly in `Signals` and `FFT` tabs.
- `configure_matplotlib_for_realtime()` is called exactly once early in the GUI lifecycle.
- Live updates use `draw_idle()` rather than `draw()` in normal operation.
- Profiling / Task Manager shows lower CPU usage at a given stream rate compared to the pre-change version (due to simplification + more efficient line updates).
- No new external dependencies are introduced.

Please implement these changes in-place, keeping style consistent with existing code. 
