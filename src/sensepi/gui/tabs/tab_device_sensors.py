from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class DeviceSensorsTab(QWidget):
    """
    Tab for selecting host/device, active sensors, and per-sensor channels.

    Phase 2: UI only, no backend logic or data binding.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        main_layout = QVBoxLayout(self)

        # Host selection (placeholder values until backend discovery is wired).
        host_layout = QHBoxLayout()
        host_layout.addWidget(QLabel("Host:"))
        self.host_combo = QComboBox()
        # TODO: In Phase 4, populate from real backend discovery.
        self.host_combo.addItems(["localhost", "raspberrypi", "custom..."])
        host_layout.addWidget(self.host_combo)
        main_layout.addLayout(host_layout)

        # Sensor count / list (placeholder range matching the current hardware assumptions).
        sensor_layout = QHBoxLayout()
        sensor_layout.addWidget(QLabel("Number of sensors:"))
        self.sensor_count_spin = QSpinBox()
        self.sensor_count_spin.setRange(1, 3)
        self.sensor_count_spin.setValue(1)
        sensor_layout.addWidget(self.sensor_count_spin)
        main_layout.addLayout(sensor_layout)

        # Per-sensor channel selection (simple 3-sensor grid example).
        channels_group = QGroupBox("Channels per sensor")
        channels_layout = QGridLayout(channels_group)

        # For simplicity, same channel checkboxes per sensor: ax, ay, az, gx, gy, gz
        self.channel_checkboxes: dict[tuple[int, str], QCheckBox] = {}
        channel_names = ["ax", "ay", "az", "gx", "gy", "gz"]

        channels_layout.addWidget(QLabel("Sensor"), 0, 0)
        for j, ch in enumerate(channel_names, start=1):
            channels_layout.addWidget(QLabel(ch), 0, j)

        for sensor_id in (1, 2, 3):
            channels_layout.addWidget(QLabel(f"S{sensor_id}"), sensor_id, 0)
            for j, ch in enumerate(channel_names, start=1):
                cb = QCheckBox()
                cb.setChecked(ch in ["ax", "ay", "az"])  # accel enabled by default
                self.channel_checkboxes[(sensor_id, ch)] = cb
                channels_layout.addWidget(cb, sensor_id, j)

        main_layout.addWidget(channels_group)

        main_layout.addStretch()

        # Phase 2 behavior: UI only; print changes to stdout.
        self.host_combo.currentTextChanged.connect(self._on_ui_changed)
        self.sensor_count_spin.valueChanged.connect(self._on_sensor_count_changed)
        for cb in self.channel_checkboxes.values():
            cb.stateChanged.connect(self._on_ui_changed)

    # --- UI helpers (Phase 2: no backend, just logging) ---

    def _on_ui_changed(self) -> None:
        print("[DeviceSensorsTab] host =", self.host_combo.currentText())
        print("[DeviceSensorsTab] sensor_count =", self.sensor_count_spin.value())
        print("[DeviceSensorsTab] active channels =", self._collect_active_channels())

    def _on_sensor_count_changed(self, count: int) -> None:
        """
        Enable/disable sensor rows based on the selected count and clear any
        channels for disabled sensors. Then log the updated UI state.
        """
        max_sensor = int(count)
        channel_names = ["ax", "ay", "az", "gx", "gy", "gz"]

        for sensor_id in (1, 2, 3):
            enabled = sensor_id <= max_sensor
            for ch in channel_names:
                cb = self.channel_checkboxes[(sensor_id, ch)]
                cb.setEnabled(enabled)
                if not enabled:
                    cb.setChecked(False)

        # Reuse the existing logging helper so stdout reflects the new state
        self._on_ui_changed()

    def _collect_active_channels(self) -> dict[int, list[str]]:
        active: dict[int, list[str]] = {}
        max_sensor = self.sensor_count_spin.value()
        for (sensor_id, ch), cb in self.channel_checkboxes.items():
            if sensor_id > max_sensor:
                # Ignore sensors beyond the configured count
                continue
            if cb.isChecked():
                active.setdefault(sensor_id, []).append(ch)
        return active
