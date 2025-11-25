from __future__ import annotations

from typing import List
import os
import numpy as np

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QDoubleSpinBox, QMessageBox, QComboBox, QDialog, QDialogButtonBox,
)

from ..core.state import AppState
from ..data.base import DataSource
from ..data.mqtt_source import MQTTSource
from ..plotting.plotter import create_plot, update_curve
from .mqtt_settings import MQTTSettingsDialog
import pyqtgraph as pg
from ..util.calibration import apply_global_and_scale  # <-- UNIFORM correction

PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c",
    "#d62728", "#9467bd", "#8c564b",
    "#e377c2", "#7f7f7f", "#17becf",
]


class SignalsTab(QWidget):
    """Tab displaying signals from a data source in a 3×3 grid."""

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._timer: QTimer | None = None
        self.running = False

        self.plots: List[object] = []
        self.curves: List[object] = []
        self.controls: List["ChannelControls"] = []

        self._last_expected_n: int | None = None

        self._build_ui()

    @staticmethod
    def _slot_is_gyro(slot_index: int) -> bool:
        return slot_index in (2, 5, 8)

    @staticmethod
    def _slot_unit(slot_index: int) -> str:
        return "deg/s" if SignalsTab._slot_is_gyro(slot_index) else "m/s²"

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        top_row.addWidget(QLabel("Sensors data (live):"))

        top_row.addWidget(QLabel("Backend:"))
        self.combo_backend = QComboBox()
        self.combo_backend.addItems(["MQTT", "SSH"])
        self.combo_backend.setCurrentText(self.state.data_source.upper())
        self.combo_backend.currentTextChanged.connect(self._on_backend_changed)
        top_row.addWidget(self.combo_backend)

        top_row.addWidget(QLabel("Window (s):"))
        self.spin_window = QDoubleSpinBox()
        self.spin_window.setRange(0.1, 60.0)
        self.spin_window.setSingleStep(0.5)
        self.spin_window.setValue(5.0)
        top_row.addWidget(self.spin_window)

        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self.on_start_stop)
        top_row.addWidget(self.btn_start)

        self.btn_enable_all = QPushButton("Enable All")
        self.btn_enable_all.clicked.connect(self.on_enable_all)
        top_row.addWidget(self.btn_enable_all)

        self.btn_disable_all = QPushButton("Disable All")
        self.btn_disable_all.clicked.connect(self.on_disable_all)
        top_row.addWidget(self.btn_disable_all)

        self.btn_reset_y_all = QPushButton("Reset Y All")
        self.btn_reset_y_all.clicked.connect(self.on_reset_y_all)
        top_row.addWidget(self.btn_reset_y_all)

        self.btn_mqtt_settings = QPushButton("MQTT Settings…")
        self.btn_mqtt_settings.clicked.connect(self.open_mqtt_settings)
        self.btn_mqtt_settings.setEnabled(self.state.data_source == "mqtt")
        top_row.addWidget(self.btn_mqtt_settings)

        # Removed: manual frequency controls (cmb_hz, btn_set_hz)
        # Add a read-only label to display the source-estimated sampling rate.
        self.lbl_fs = QLabel("fs: — Hz")
        top_row.addWidget(self.lbl_fs)

        self.btn_cal = QPushButton("Calibrate (zero-mean)")
        self.btn_cal.clicked.connect(self.do_calibrate_global)
        top_row.addWidget(self.btn_cal)

        self.lbl_cal_status = QLabel("Calibration: not applied")
        top_row.addWidget(self.lbl_cal_status)

        self.lbl_rec = QLabel(f"Recorder: {self.state.mqtt.recorder}")
        top_row.addWidget(self.lbl_rec)

        top_row.addWidget(QLabel("Fix Y ±:"))
        self.spin_y_limit = QDoubleSpinBox()
        self.spin_y_limit.setRange(0.01, 10000.0)
        self.spin_y_limit.setDecimals(3)
        self.spin_y_limit.setSingleStep(0.05)
        self.spin_y_limit.setValue(5.00)
        top_row.addWidget(self.spin_y_limit)

        self.btn_apply_y = QPushButton("Apply")
        self.btn_apply_y.clicked.connect(self.apply_y_limit)
        top_row.addWidget(self.btn_apply_y)

        self.btn_auto_y = QPushButton("Auto")
        self.btn_auto_y.clicked.connect(self.auto_y_limit)
        top_row.addWidget(self.btn_auto_y)

        self.btn_show_layout = QPushButton("Show sensors layout")
        self.btn_show_layout.clicked.connect(self.show_sensors_layout)
        top_row.addWidget(self.btn_show_layout)

        top_row.addStretch(1)
        layout.addLayout(top_row)

        grid = QGridLayout()
        grid.setSpacing(6)
        for row in range(3):
            for col in range(3):
                idx = row * 3 + col
                cell_widget = QWidget()
                cell_layout = QVBoxLayout(cell_widget)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setSpacing(2)

                y_label = self._slot_unit(idx)
                plot_widget, curve = create_plot(cell_widget, x_label="Data points", y_label=y_label)
                plot_widget.setFixedHeight(120)
                cell_layout.addWidget(plot_widget)
                self.plots.append(plot_widget)
                self.curves.append(curve)
                curve.setPen(pg.mkPen(PALETTE[idx % len(PALETTE)], width=2.0))

                from .widgets import ChannelControls  # local import to avoid cycles
                ctrl = ChannelControls(idx, self.state, cell_widget)
                self.controls.append(ctrl)
                cell_layout.addWidget(ctrl)

                grid.addWidget(cell_widget, row, col)
        layout.addLayout(grid)

        self.spin_window.valueChanged.connect(lambda _=None: self._apply_expected_xrange())

    def _expected_points(self) -> int:
        window_s = float(self.spin_window.value())
        src = self.state.source or self.state.ensure_source()

        hz = 20.0
        if src is not None:
            # Prefer generic estimated_hz attribute (SSHStreamSource, etc.)
            est = getattr(src, "estimated_hz", None)
            if est:
                hz = float(est)

            # Fallback to MQTT-specific rate info if available
            if isinstance(src, MQTTSource):
                try:
                    hz = float(src.get_rate().hz_effective)
                except Exception:
                    pass

        n = int(round(max(0.001, window_s) * max(1.0, hz)))
        return max(1, n)

    def _apply_expected_xrange(self) -> None:
        n = self._expected_points()
        if self._last_expected_n == n:
            return
        for plot in self.plots:
            try:
                plot.enableAutoRange('x', False)
                plot.setXRange(0, max(1, n - 1), padding=0)
            except Exception:
                pass
        self._last_expected_n = n

    def _on_backend_changed(self, text: str) -> None:
        backend = (text or "").strip().lower()
        if backend not in ("mqtt", "ssh"):
            return

        was_running = self.running
        if self._timer:
            self._timer.stop()
        self.running = False
        self.btn_start.setText("Start")

        try:
            self.state.stop_source()
        except Exception:
            pass
        self.state.source = None
        self.state.data_source = backend
        self.btn_mqtt_settings.setEnabled(backend == "mqtt")
        self._last_expected_n = None
        self._apply_expected_xrange()

        if was_running:
            self.on_start_stop()

    def on_start_stop(self) -> None:
        if not self.running:
            try:
                self.state.start_source()
            except Exception as e:
                QMessageBox.critical(self, "MQTT start failed", str(e))
                return
            if self._timer is None:
                self._timer = QTimer(self)
                self._timer.timeout.connect(self.update_data)
            self._timer.start(50)
            self.running = True
            self.btn_start.setText("Stop")
            self._apply_expected_xrange()
        else:
            self.running = False
            if self._timer:
                self._timer.stop()
            self.state.stop_source()
            self.btn_start.setText("Start")

    def on_enable_all(self) -> None:
        for ch_cfg in self.state.channels:
            ch_cfg.enabled = True
        for ctrl in self.controls:
            ctrl.refresh()

    def on_disable_all(self) -> None:
        for ch_cfg in self.state.channels:
            ch_cfg.enabled = False
        for ctrl in self.controls:
            ctrl.refresh()

    def on_reset_y_all(self) -> None:
        for ch_cfg in self.state.channels:
            ch_cfg.y_zoom = 1.0

    def update_data(self) -> None:
        # Update read-only display of estimated sampling rate from source status.
        src = self.state.source
        dev_hz = 0.0

        if src is not None:
            est = getattr(src, "estimated_hz", None)
            if est:
                dev_hz = float(est)

        # Preserve MQTT-specific status details if available
        if isinstance(src, MQTTSource):
            try:
                rate = src.get_rate()
                dev_hz = float(rate.hz_effective)
            except Exception:
                pass

            try:
                status, hz_req, t = src.get_rate_apply_result()
                if status == "ok":
                    self.lbl_fs.setText(
                        f"Device: ~{dev_hz:.1f} Hz · Last set {hz_req:.0f} Hz ✓"
                    )
                elif status == "timeout":
                    self.lbl_fs.setText(
                        f"Device: ~{dev_hz:.1f} Hz · Set {hz_req:.0f} Hz timed out"
                    )
            except Exception:
                # ignore; label will be set generically below if needed
                pass

        # Generic label for non-MQTT sources (e.g. SSH)
        if not isinstance(src, MQTTSource):
            self.lbl_fs.setText(f"Device: ~{dev_hz:.1f} Hz")

        self._apply_expected_xrange()
        window_s = float(self.spin_window.value())
        if src is None:
            return
        try:
            data = src.read(window_s)
        except Exception:
            self.on_start_stop()
            data = {f"slot_{i}": np.array([]) for i in range(9)}

        for i in range(9):
            ch_cfg = self.state.channels[i]
            y = data.get(f"slot_{i}", np.array([]))

            if ch_cfg.enabled and np.size(y) > 0:
                y_cal = apply_global_and_scale(self.state, i, y)  # <-- UNIFORM correction
            else:
                y_cal = np.array([])

            update_curve(self.curves[i], y_cal, ch_cfg.y_zoom)
            plot = self.plots[i]
            plot.setBackground(QColor(255, 255, 255) if ch_cfg.enabled else QColor(245, 245, 245))

    def open_mqtt_settings(self) -> None:
        dlg = MQTTSettingsDialog(self.state, self)
        if dlg.exec() == QDialog.Accepted:
            self.lbl_rec.setText(f"Recorder: {self.state.mqtt.recorder}")
            if self.running:
                self.on_start_stop()
            self.state.stop_source()
            self.state.source = None
            self._last_expected_n = None
            self._apply_expected_xrange()

    def do_calibrate_global(self) -> None:
        src = self.state.source
        if src is None:
            self.lbl_cal_status.setText("Calibration skipped: no source")
            return
        window_s = float(self.spin_window.value())
        try:
            data = src.read(window_s)
        except Exception as exc:
            self.lbl_cal_status.setText(f"Calibration failed: {exc}")
            return
        offsets: list[float] = []
        for i in range(9):
            y = data.get(f"slot_{i}", np.array([]))
            offsets.append(float(np.mean(y)) if np.size(y) > 0 else 0.0)
        self.state.global_cal.offsets = offsets
        self.state.global_cal.enabled = True
        self.lbl_cal_status.setText(
            f"Global calibration applied (per-slot mean over last {window_s:.1f} s)"
        )

    def apply_y_limit(self) -> None:
        val = float(self.spin_y_limit.value())
        if val <= 0:
            return
        for plot in self.plots:
            try:
                plot.enableAutoRange('y', False)
                plot.setYRange(-val, val, padding=0)
            except Exception:
                pass

    def auto_y_limit(self) -> None:
        for plot in self.plots:
            try:
                plot.enableAutoRange('y', True)
            except Exception:
                pass

    def show_sensors_layout(self) -> None:
        candidate_paths = [
            os.path.join(os.getcwd(), "images", "sensors.jpg"),
            os.path.join(os.path.dirname(__file__), "..", "images", "sensors.jpg"),
        ]
        img_path = next((p for p in candidate_paths if os.path.exists(p)), None)
        if not img_path:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Image not found", "Could not find images/sensors.jpg")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Sensors numbering layout")
        v = QVBoxLayout(dlg)
        lbl = QLabel()
        pix = QPixmap(img_path)
        if pix.isNull():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Image error", "Failed to load sensors.jpg")
            return
        lbl.setPixmap(pix)
        v.addWidget(lbl)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        v.addWidget(btns)
        dlg.resize(pix.width(), pix.height())
        dlg.exec()
