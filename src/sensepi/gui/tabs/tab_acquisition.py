from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from sensepi.gui.widgets.acquisition_settings import AcquisitionSettingsWidget


class AcquisitionRatesTab(QWidget):
    """
    Tab that wraps AcquisitionSettingsWidget and adds streaming/plotting rate
    and a 'record only' toggle.

    Phase 2: UI only, state is local to the widget and not sent to backend.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)

        # Existing widget for sampling configuration
        self.acq_widget = AcquisitionSettingsWidget(parent=self)
        layout.addWidget(self.acq_widget)

        # Streaming / plotting rate
        streaming_layout = QHBoxLayout()
        streaming_layout.addWidget(QLabel("Streaming / plotting rate [Hz]:"))
        self.streaming_rate_spin = QDoubleSpinBox()
        self.streaming_rate_spin.setRange(0.1, 1000.0)
        self.streaming_rate_spin.setValue(50.0)
        streaming_layout.addWidget(self.streaming_rate_spin)
        layout.addLayout(streaming_layout)

        # Record-only checkbox
        self.record_only_checkbox = QCheckBox("Record only (no live streaming)")
        self.record_only_checkbox.setChecked(False)
        layout.addWidget(self.record_only_checkbox)

        layout.addStretch()

        # Phase 2: log UI changes
        self.streaming_rate_spin.valueChanged.connect(self._dump_state)
        self.record_only_checkbox.stateChanged.connect(self._dump_state)

    def _dump_state(self) -> None:
        print("[AcquisitionRatesTab] streaming_rate_hz =", self.streaming_rate_spin.value())
        print("[AcquisitionRatesTab] record_only =", self.record_only_checkbox.isChecked())
        # A concise summary from the acquisition widget can be added later when wired.
