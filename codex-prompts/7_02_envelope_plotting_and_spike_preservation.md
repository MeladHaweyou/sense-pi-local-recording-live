
# Prompt: Implement Envelope Plotting and Spike Preservation

You are an AI coding assistant tasked with implementing **envelope plotting** and **spike-preservation logic** for a live sensor plot in a SensePi-like system.

## System Context

- Raw sensor data at 500–1000 Hz.
- Plot refresh rate ~20–60 Hz.
- A `Decimator` module (from previous prompt) is available and returns:
  - `t_dec` (timestamps),
  - `y_mean` (mean per interval),
  - optionally `y_min`, `y_max` (envelope).
- Plotting uses **Matplotlib** for a live GUI plot.

The goal is to:
- Draw a **smooth line** for the mean.
- Draw a **translucent band** for the min–max envelope.
- Optionally highlight spikes where the raw samples exceeded some threshold relative to the mean.

## Your Tasks

1. Implement helper functions in a module like `envelope_plot.py` that:
   - Accept decimated arrays and a Matplotlib `Axes` instance.
   - Maintain and update:
     - A `Line2D` object for the mean.
     - A `PolyCollection` or `PolyCollection`-like object for the `fill_between` envelope.
   - Provide a simple API such as:
     ```python
     def init_envelope_plot(ax, color="C0", alpha=0.2):
         ...

     def update_envelope_plot(line, envelope_coll, t_dec, y_mean, y_min, y_max):
         ...
     ```

2. Implement **spike markers**:
   - Given `y_mean` and per-interval `y_max`, mark intervals where:
     `y_max - y_mean > spike_threshold` (configurable).
   - Use a separate scatter plot or markers to highlight these spikes.

3. Ensure that updates are **fast** enough to run at 20–60 Hz.

## Important Code Snippets

Use these as starting points and refine:

```python
# envelope_plot.py
from __future__ import annotations
from typing import Tuple, Optional
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection

def init_envelope_plot(
    ax: plt.Axes,
    color: str = "C0",
    alpha: float = 0.2,
) -> Tuple[Line2D, PolyCollection]:
    """Initialize a mean line and envelope fill on the given axes."""
    # Dummy initial data
    line, = ax.plot([], [], color=color, lw=1.0)
    # Create an empty PolyCollection via fill_between
    # We'll update its paths later.
    coll = ax.fill_between([], [], [], color=color, alpha=alpha)
    return line, coll

def update_envelope_plot(
    line: Line2D,
    envelope_coll: PolyCollection,
    t_dec: np.ndarray,
    y_mean: np.ndarray,
    y_min: Optional[np.ndarray],
    y_max: Optional[np.ndarray],
) -> None:
    """Update line and envelope for new data."""
    if t_dec.size == 0:
        return

    # Update mean line
    line.set_data(t_dec, y_mean)

    # Update envelope only if provided
    if y_min is not None and y_max is not None:
        # Workaround: easiest is to remove old coll and create a new fill_between.
        ax = line.axes
        # remove previous envelope (if any)
        try:
            envelope_coll.remove()
        except ValueError:
            pass

        new_coll = ax.fill_between(t_dec, y_min, y_max,
                                   color=line.get_color(), alpha=0.2)
        # We need to return or store new_coll somewhere.
        # Caller should manage replacing the reference to envelope_coll.
    ```

4. Extend the above to:
   - Return `new_coll` from `update_envelope_plot` so the caller can keep the latest reference.
   - Avoid excessive object creation if performance becomes an issue. For now, a simple `remove()` + `fill_between()` per update is acceptable. If needed, you can optimize later using `PolyCollection` directly.

5. Implement optional **spike markers**:

```python
def update_spike_markers(
    scatter,
    t_dec: np.ndarray,
    y_mean: np.ndarray,
    y_max: Optional[np.ndarray],
    spike_threshold: float,
):
    if y_max is None:
        # Nothing to do
        scatter.set_offsets(np.empty((0, 2)))
        return

    # Find intervals where max is sufficiently above the mean
    mask = (y_max - y_mean) > spike_threshold
    t_spikes = t_dec[mask]
    y_spikes = y_max[mask]

    if t_spikes.size == 0:
        scatter.set_offsets(np.empty((0, 2)))
    else:
        pts = np.column_stack([t_spikes, y_spikes])
        scatter.set_offsets(pts)
```

The calling code should:
- Create `scatter = ax.scatter([], [], s=10, color="red", marker="x")` once.
- Call `update_spike_markers(scatter, ...)` each frame.

## Integration Notes

- Ensure that the code works with Matplotlib’s animation (`FuncAnimation`) or with a manual redraw loop (e.g., using timers).
- The design should allow for multiple sensor channels (e.g., x/y/z axes). You can either:
  - Instantiate multiple envelope plots per channel, or
  - Provide a thin wrapper to manage a list of `(line, coll, scatter)` triples.

Focus on:
- Clean, re-usable plotting helpers.
- Fast updates (limit object churn when possible).
- Clear docstrings and type hints.
