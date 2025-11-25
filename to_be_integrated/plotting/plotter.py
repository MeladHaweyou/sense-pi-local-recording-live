"""Helper functions for creating and updating pyqtgraph plots.

By funnelling all pyqtgraph usage through a thin layer, the rest of the
application remains decoupled from the plotting library.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg


def create_plot(parent, x_label: str = "Data points", y_label: str = ""):
    """Create a new pyqtgraph plot inside the given parent widget.

    The plot has its grid enabled and mouse interaction disabled.
    Axis labels are set from the provided arguments.
    """
    plot_widget = pg.PlotWidget(parent=parent)
    plot_widget.showGrid(x=True, y=True, alpha=0.3)
    plot_widget.setLabel('left', y_label)
    plot_widget.setLabel('bottom', x_label)
    plot_widget.setMouseEnabled(x=False, y=False)
    # Create a new curve; do not fill until data is provided.
    curve = plot_widget.plot([], [])
    return plot_widget, curve


def update_curve(curve: pg.PlotDataItem, y: np.ndarray | None, y_zoom: float) -> None:
    """Update the given curve with new y-values.

    If the input array ``y`` is empty or None, the curve is cleared. The supplied
    ``y_zoom`` is applied multiplicatively to the data prior to plotting.
    """
    if y is None or len(y) == 0:
        curve.setData([], [])
        return
    data = np.asarray(y, dtype=float)
    if data.ndim != 1:
        data = data.ravel()
    zoom = max(1e-9, float(y_zoom))
    y_scaled = data * zoom
    x = np.arange(len(y_scaled), dtype=float)
    curve.setData(x, y_scaled)
