"""Compatibility shim for the PyQtGraph SignalPlotWidget implementation."""

from __future__ import annotations

from .tabs.tab_signals import SignalPlotWidget

# Historically, the PyQtGraph implementation lived in this module. Keep the
# import path alive so older code can still request PyQtGraphSignalPlotWidget.
PyQtGraphSignalPlotWidget = SignalPlotWidget

