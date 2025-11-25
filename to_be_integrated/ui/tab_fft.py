# ui/tab_fft.py
from __future__ import annotations

from typing import List, Tuple
import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QDoubleSpinBox, QCheckBox, QComboBox, QSpinBox
)

from ..core.state import AppState
from ..data.base import DataSource
from ..data.mqtt_source import MQTTSource
from ..sonify.notes_method import one_sided_fft, top_n_freqs  # robust, Hann-windowed one-sided FFT + peak picker
from ..util.calibration import apply_global_and_scale  # <-- UNIFORM correction


class FFTTab(QWidget):
    """
    Single-panel FFT viewer that can overlay the spectra of all 9 slots.
    - Top bar: window(s), max Hz, detrend mode, normalize, Start/Stop, Show all/none
    - One pyqtgraph plot, 9 colored curves, per-channel checkboxes
    - NEW: peak picking (vertical markers + optional labels), configurable N peaks
    """

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._timer: QTimer | None = None
        self._running: bool = False

        self.plot: pg.PlotWidget | None = None
        self.curves: List[pg.PlotDataItem] = []
        self.checks: List[QCheckBox] = []

        # Peak overlay graphics per slot
        self.peak_lines: List[List[pg.InfiniteLine]] = [[] for _ in range(9)]
        self.peak_labels: List[List[pg.TextItem]] = [[] for _ in range(9)]

        self._last_fs: float | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.addWidget(QLabel("Window (s):"))
        self.spin_window = QDoubleSpinBox()
        self.spin_window.setRange(0.2, 60.0)
        self.spin_window.setSingleStep(0.5)
        self.spin_window.setValue(5.0)
        top.addWidget(self.spin_window)

        top.addWidget(QLabel("Backend:"))
        self.combo_backend = QComboBox()
        self.combo_backend.addItems(["MQTT", "SSH"])
        self.combo_backend.setCurrentText(self.state.data_source.upper())
        self.combo_backend.currentTextChanged.connect(self._on_backend_changed)
        top.addWidget(self.combo_backend)

        top.addWidget(QLabel("Max Hz:"))
        self.spin_max_hz = QDoubleSpinBox()
        self.spin_max_hz.setRange(1.0, 1e6)
        self.spin_max_hz.setDecimals(1)
        self.spin_max_hz.setSingleStep(1.0)
        self.spin_max_hz.setValue(10.0)
        top.addWidget(self.spin_max_hz)

        top.addWidget(QLabel("Detrend:"))
        self.cmb_detrend = QComboBox()
        self.cmb_detrend.addItems(["Mean (DC remove)", "Linear", "None"])
        self.cmb_detrend.setCurrentIndex(0)
        self.cmb_detrend.currentIndexChanged.connect(self._refresh_once)
        top.addWidget(self.cmb_detrend)

        self.chk_norm = QCheckBox("Normalize amplitudes")
        self.chk_norm.setChecked(True)
        top.addWidget(self.chk_norm)

        # --- Peak picking controls ---
        self.chk_peaks = QCheckBox("Show peaks")
        self.chk_peaks.setChecked(True)
        top.addWidget(self.chk_peaks)

        top.addWidget(QLabel("Peaks:"))
        self.spin_npeaks = QSpinBox()
        self.spin_npeaks.setRange(1, 12)
        self.spin_npeaks.setValue(3)
        top.addWidget(self.spin_npeaks)

        self.chk_peak_labels = QCheckBox("Label peaks")
        self.chk_peak_labels.setChecked(False)
        top.addWidget(self.chk_peak_labels)
        # -----------------------------

        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self._on_start_stop)
        top.addWidget(self.btn_start)

        self.btn_all = QPushButton("Show all")
        self.btn_all.clicked.connect(lambda: self._set_all_checks(True))
        top.addWidget(self.btn_all)

        self.btn_none = QPushButton("Show none")
        self.btn_none.clicked.connect(lambda: self._set_all_checks(False))
        top.addWidget(self.btn_none)

        top.addStretch(1)
        root.addLayout(top)

        self.plot = pg.PlotWidget(parent=self)
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel('left', "Amplitude")
        self.plot.setLabel('bottom', "Frequency [Hz]")
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.addLegend(offset=(10, 10))
        root.addWidget(self.plot, 1)

        grid = QGridLayout()
        grid.setSpacing(4)
        self.curves = []
        self.checks = []
        for idx in range(9):
            name = self.state.channels[idx].name
            pen = pg.mkPen(color=pg.intColor(idx, hues=9, values=1, maxValue=255), width=1.6)
            curve = self.plot.plot([], [], pen=pen, name=f"Slot {idx} — {name}")
            self.curves.append(curve)

            chk = QCheckBox(f"{idx}: {name}")
            chk.setChecked(True)
            chk.stateChanged.connect(self._refresh_once)
            self.checks.append(chk)

            r, c = divmod(idx, 3)
            grid.addWidget(chk, r, c)
        root.addLayout(grid)

        # Reactivity
        self.spin_window.valueChanged.connect(self._refresh_once)
        self.spin_max_hz.valueChanged.connect(self._refresh_once)
        self.chk_norm.stateChanged.connect(self._refresh_once)
        self.chk_peaks.stateChanged.connect(self._refresh_once)
        self.spin_npeaks.valueChanged.connect(self._refresh_once)
        self.chk_peak_labels.stateChanged.connect(self._refresh_once)

    def _set_all_checks(self, val: bool) -> None:
        for chk in self.checks:
            chk.blockSignals(True)
            chk.setChecked(val)
            chk.blockSignals(False)
        self._refresh_once()

    def _on_backend_changed(self, text: str) -> None:
        backend = (text or "").strip().lower()
        if backend not in ("mqtt", "ssh"):
            return

        was_running = self._running
        if self._timer:
            self._timer.stop()
        self._running = False
        self.btn_start.setText("Start")

        try:
            self.state.stop_source()
        except Exception:
            pass
        self.state.source = None
        self.state.data_source = backend
        self._last_fs = None

        if was_running:
            self._on_start_stop()

    def _on_start_stop(self) -> None:
        if not self._running:
            try:
                self.state.start_source()
            except Exception:
                self.btn_start.setText("Start")
                return
            if self._timer is None:
                self._timer = QTimer(self)
                self._timer.timeout.connect(self._refresh_once)
            self._timer.start(250)
            self._running = True
            self.btn_start.setText("Stop")
            self._refresh_once()
        else:
            if self._timer:
                self._timer.stop()
            self._running = False
            self.btn_start.setText("Start")

    def _current_fs(self) -> float:
        """Determine effective sampling rate in Hz from the current live source.

        Priority:
          1. src.estimated_hz (SSHStreamSource or generic)
          2. MQTTSource.get_rate().hz_effective
          3. fallback 20.0 Hz
        """
        src = self.state.source or self.state.ensure_source()
        hz = 20.0

        if src is not None:
            est = getattr(src, "estimated_hz", None)
            if est:
                hz = float(est)

            if isinstance(src, MQTTSource):
                try:
                    hz = float(src.get_rate().hz_effective)
                except Exception:
                    pass

        return max(1e-6, float(hz))

    def _read_window(self) -> dict[str, np.ndarray]:
        src = self.state.source
        if src is None:
            return {f"slot_{i}": np.array([]) for i in range(9)}
        window_s = float(self.spin_window.value())
        try:
            return src.read(window_s)
        except Exception:
            return {f"slot_{i}": np.array([]) for i in range(9)}

    def _clear_peaks_for_slot(self, i: int) -> None:
        """Remove existing peak lines and labels for slot i."""
        # Remove lines
        for ln in self.peak_lines[i]:
            try:
                self.plot.removeItem(ln)
            except Exception:
                pass
        self.peak_lines[i].clear()
        # Remove labels
        for txt in self.peak_labels[i]:
            try:
                self.plot.removeItem(txt)
            except Exception:
                pass
        self.peak_labels[i].clear()

    def _add_peak_marker(self, i: int, f0: float, label: str | None, color_pen: pg.mkPen) -> None:
        """Add a vertical line (and optional label) at frequency f0 for slot i."""
        line_pen = pg.mkPen(color=color_pen.color(), width=1, style=Qt.DashLine)
        ln = pg.InfiniteLine(pos=float(f0), angle=90, movable=False, pen=line_pen)
        self.plot.addItem(ln)
        self.peak_lines[i].append(ln)

        if label and self.chk_peak_labels.isChecked():
            # Place label at top of current view, slightly inset
            txt = pg.TextItem(text=label, color=color_pen.color(), anchor=(0.3, 1.0))
            self.plot.addItem(txt)
            vb = self.plot.getViewBox()
            try:
                x_min, x_max = vb.viewRange()[0]
                y_min, y_max = vb.viewRange()[1]
            except Exception:
                x_min, x_max = 0.0, float(self.spin_max_hz.value())
                y_min, y_max = 0.0, 1.0
            txt.setPos(float(f0), y_max)
            self.peak_labels[i].append(txt)

    def _refresh_once(self) -> None:
        data = self._read_window()
        fs = self._current_fs()
        max_hz = float(self.spin_max_hz.value())
        self.plot.setXRange(0.0, max_hz, padding=0.0)

        # clear all existing peak annotations before redrawing
        for i in range(9):
            self._clear_peaks_for_slot(i)

        for i in range(9):
            y_raw = np.asarray(data.get(f"slot_{i}", np.array([])), dtype=float).ravel()
            y = apply_global_and_scale(self.state, i, y_raw)  # <-- UNIFORM correction

            if y.size < 2 or not self.checks[i].isChecked():
                self.curves[i].setData([], [])
                continue

            f, A = one_sided_fft(y, fs, detrend=self._detrend_mode())
            m = f <= max_hz
            f_plot = f[m]; A_plot = A[m]

            if self.chk_norm.isChecked():
                peak = float(np.max(A_plot)) if A_plot.size else 0.0
                if peak > 0:
                    A_plot = A_plot / peak

            self.curves[i].setData(f_plot, A_plot)

            # Peak picking overlay
            if self.chk_peaks.isChecked():
                n = int(self.spin_npeaks.value())
                # Use the same robust picker used by fft_view
                try:
                    cand = top_n_freqs(y, float(fs), max(1, n), detrend=self._detrend_mode())
                except Exception:
                    cand = []

                # Filter peaks to the current visible band
                cand = [float(x) for x in cand if 0.0 < float(x) <= max_hz]

                # If multiple candidates map to the same FFT bin, deduplicate by frequency value
                if cand:
                    # Create a pen for this slot (same color as the curve)
                    pen = self.curves[i].opts.get("pen", pg.mkPen("w"))

                    # Add markers (limit to N shown after filtering)
                    for f0 in cand[:n]:
                        # Optional label text (Hz with one decimal)
                        label = f"{f0:.1f} Hz" if self.chk_peak_labels.isChecked() else None
                        self._add_peak_marker(i, f0, label, pen)

    def _detrend_mode(self) -> str:
        t = self.cmb_detrend.currentText().lower()
        if "linear" in t:
            return "linear"
        if "none" in t:
            return "none"
        return "mean"
