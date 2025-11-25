# ui/mqtt_settings.py
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
)

from ..core.state import AppState


class MQTTSettingsDialog(QDialog):
    """
    Minimal stub dialog for editing MQTT settings.

    Lets the user view/edit host/port/topic/initial_hz on AppState.mqtt
    and applies them on OK.
    """

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MQTT Settings")

        self._state = state

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.edit_host = QLineEdit(state.mqtt.host)
        self.edit_port = QLineEdit(str(state.mqtt.port))
        self.edit_topic = QLineEdit(state.mqtt.topic)
        self.edit_hz = QLineEdit(str(state.mqtt.initial_hz))

        form.addRow("Host", self.edit_host)
        form.addRow("Port", self.edit_port)
        form.addRow("Topic", self.edit_topic)
        form.addRow("Initial Hz", self.edit_hz)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        # Apply changes back into state; keep this forgiving.
        m = self._state.mqtt
        m.host = self.edit_host.text().strip() or m.host
        try:
            m.port = int(self.edit_port.text())
        except Exception:
            pass
        m.topic = self.edit_topic.text().strip() or m.topic
        try:
            m.initial_hz = int(float(self.edit_hz.text()))
        except Exception:
            pass
        super().accept()
