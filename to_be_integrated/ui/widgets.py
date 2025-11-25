"""Reusable user interface components.

This module defines small widgets used in the signals tab. Keeping these
controls in their own module makes it easier to modify their layout or
behaviour without touching the rest of the code.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QCheckBox,
    QDoubleSpinBox,
    QLabel,
    QHBoxLayout,
)

from ..core.state import AppState


class ChannelControls(QWidget):
    """UI panel for adjusting a single plot slot.

    Each cell in the signals tab consists of a plot stacked above a
    :class:`ChannelControls` instance. This widget exposes a checkbox
    to enable/disable the channel and a spin box for a multiplicative
    scale. Per-channel offsets and Y+ / Y− buttons have been removed in
    favour of a global fixed-Y control in the toolbar.
    """

    def __init__(self, idx: int, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.idx = idx
        self.state = state
        ch = self.state.channels[idx]

        # Horizontal layout for controls
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Slot title
        self.lbl_title = QLabel(ch.name)
        layout.addWidget(self.lbl_title)

        # Enable checkbox
        self.check_enable = QCheckBox("Enable")
        self.check_enable.setChecked(ch.enabled)
        self.check_enable.stateChanged.connect(self.on_enable_changed)
        layout.addWidget(self.check_enable)

        # Calibration scale (per-channel)
        self.lbl_scale = QLabel("Scale")
        layout.addWidget(self.lbl_scale)
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(0.0, 1000.0)
        self.spin_scale.setSingleStep(0.1)
        self.spin_scale.setValue(ch.cal.scale)
        self.spin_scale.valueChanged.connect(self.on_scale_changed)
        layout.addWidget(self.spin_scale)

        # Stretch at end
        layout.addStretch(1)

    def on_enable_changed(self, state: int) -> None:
        self.state.channels[self.idx].enabled = bool(state)

    def on_scale_changed(self, value: float) -> None:
        self.state.channels[self.idx].cal.scale = float(value)

    def refresh(self) -> None:
        """Synchronise widgets from the current state."""
        ch = self.state.channels[self.idx]
        self.check_enable.blockSignals(True)
        self.spin_scale.blockSignals(True)
        try:
            self.check_enable.setChecked(ch.enabled)
            self.spin_scale.setValue(ch.cal.scale)
        finally:
            self.check_enable.blockSignals(False)
            self.spin_scale.blockSignals(False)
