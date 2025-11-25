from __future__ import annotations

import csv
from typing import List, Dict, Tuple, Optional

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QComboBox, QMessageBox, QDoubleSpinBox, QCheckBox
)

from ...core.state import AppState

# Prefer your robust FFT from repo; fallback if not present.
try:
    from sonify.notes_method import one_sided_fft  # type: ignore
except Exception:
    one_sided_fft = None


def _fallback_one_sided_fft(y: np.ndarray, fs: float, detrend: str = "mean") -> Tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=float).ravel()
    n = y.size
    if n < 2 or fs <= 0:
        return np.array([]), np.array([])
    if detrend == "mean":
        y = y - np.mean(y)
    elif detrend == "linear":
        t = np.arange(n, dtype=float)
        A = np.vstack([t, np.ones_like(t)]).T
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        y = y - (coef[0] * t + coef[1])
    w = np.hanning(n)
    Y = np.fft.rfft(w * y)
    f = np.fft.rfftfreq(n, d=1.0 / fs)
    mag = np.abs(Y) / n
    return f, mag


class FFTTab(QWidget):
    """
    Offline FFT viewer for a recorded CSV:
      • Open CSV (expects: timestamp_iso, t_rel_s, channels...)
      • Choose channel
      • Select time window (drag region or numeric start/end)
      • Optional custom fs override (else estimated from t_rel_s)
      • Show time signal (top) and amplitude spectrum (bottom)
      • Detrend (Mean/Linear/None), Max frequency

    Uses one_sided_fft from your repo if available.
    """

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

        self._t: Optional[np.ndarray] = None
        self._cols: Dict[str, np.ndarray] = {}
        self._labels: List[str] = []
        self._fs_auto: float = 0.0

        self._build_ui()

    # ------------- UI -------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.btn_open = QPushButton("Open CSV…")
        self.btn_open.clicked.connect(self.on_open)
        top.addWidget(self.btn_open)

        top.addWidget(QLabel("Channel:"))
        self.cmb_ch = QComboBox()
        self.cmb_ch.currentIndexChanged.connect(self._replot_all)
        top.addWidget(self.cmb_ch)

        top.addWidget(QLabel("Detrend:"))
        self.cmb_detrend = QComboBox()
        self.cmb_detrend.addItems(["Mean (DC remove)", "Linear", "None"])
        self.cmb_detrend.currentIndexChanged.connect(self._replot_all)
        top.addWidget(self.cmb_detrend)

        top.addWidget(QLabel("Max f (Hz):"))
        self.spin_fmax = QDoubleSpinBox()
        self.spin_fmax.setRange(0.0, 1e7)
        self.spin_fmax.setValue(0.0)  # 0 => full band
        self.spin_fmax.setDecimals(2)
        self.spin_fmax.valueChanged.connect(self._replot_fft_only)
        top.addWidget(self.spin_fmax)

        self.chk_custom_fs = QCheckBox("Use custom fs")
        self.chk_custom_fs.stateChanged.connect(self._replot_fft_only)
        top.addWidget(self.chk_custom_fs)

        self.spin_fs = QDoubleSpinBox()
        self.spin_fs.setRange(0.1, 1e7)
        self.spin_fs.setDecimals(6)
        self.spin_fs.setValue(100.0)
        self.spin_fs.setSuffix(" Hz")
        self.spin_fs.setEnabled(False)
        self.spin_fs.valueChanged.connect(self._replot_fft_only)
        top.addWidget(self.spin_fs)

        def _toggle_fs(_):
            self.spin_fs.setEnabled(self.chk_custom_fs.isChecked())
        self.chk_custom_fs.stateChanged.connect(_toggle_fs)

        top.addStretch(1)
        self.lbl_info = QLabel("No file loaded")
        self.lbl_info.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.lbl_info)

        root.addLayout(top)

        # Time-domain plot (top)
        self.time_plot = pg.PlotWidget()
        self.time_plot.setLabel("bottom", "t", units="s")
        self.time_plot.setLabel("left", "x(t)")
        self.time_plot.showGrid(x=True, y=True, alpha=0.25)
        root.addWidget(self.time_plot, 1)

        # Draggable selection region over time plot
        self.region = pg.LinearRegionItem(values=[0.0, 1.0], brush=(100, 100, 255, 40))
        self.region.setZValue(10)
        self.region.sigRegionChanged.connect(self._sync_region_to_spins_then_fft)
        self.time_plot.addItem(self.region)

        # Numeric window controls
        win = QHBoxLayout()
        win.addWidget(QLabel("Window start (s):"))
        self.spin_t0 = QDoubleSpinBox(); self.spin_t0.setRange(-1e12, 1e12); self.spin_t0.setDecimals(6)
        self.spin_t0.valueChanged.connect(self._sync_spins_to_region_then_fft)
        win.addWidget(self.spin_t0)
        win.addWidget(QLabel("end (s):"))
        self.spin_t1 = QDoubleSpinBox(); self.spin_t1.setRange(-1e12, 1e12); self.spin_t1.setDecimals(6)
        self.spin_t1.valueChanged.connect(self._sync_spins_to_region_then_fft)
        win.addStretch(1)
        root.addLayout(win)

        # Frequency-domain plot (bottom)
        self.fft_plot = pg.PlotWidget()
        self.fft_plot.setLabel("bottom", "f", units="Hz")
        self.fft_plot.setLabel("left", "|X(f)|")
        self.fft_plot.showGrid(x=True, y=True, alpha=0.25)
        root.addWidget(self.fft_plot, 1)

        self.setLayout(root)

    # ------------- File I/O -------------
    def on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "r", newline="", encoding="utf-8") as f:
                rdr = csv.reader(f)
                header = next(rdr)
                if len(header) < 3 or header[0] != "timestamp_iso" or header[1] != "t_rel_s":
                    raise ValueError("Unexpected CSV header. Expect 'timestamp_iso,t_rel_s,...'")
                labels = header[2:]
                t_arr: List[float] = []
                cols: Dict[str, List[float]] = {lab: [] for lab in labels}
                for row in rdr:
                    if not row:
                        continue
                    try:
                        t_arr.append(float(row[1]))
                        for i, lab in enumerate(labels, start=2):
                            v = row[i]
                            cols[lab].append(float(v) if v != '' else np.nan)
                    except Exception:
                        continue

            t = np.asarray(t_arr, dtype=float)
            self._t = t
            self._cols = {k: np.asarray(v, dtype=float) for k, v in cols.items()}
            self._labels = labels

            # sampling rate estimate from t_rel_s
            if t.size > 1 and (t[-1] - t[0]) > 0:
                self._fs_auto = (t.size - 1) / float(t[-1] - t[0])
            else:
                self._fs_auto = 0.0

            # Populate channel list
            self.cmb_ch.blockSignals(True)
            self.cmb_ch.clear()
            self.cmb_ch.addItems(self._labels)
            self.cmb_ch.blockSignals(False)

            # Set region to first few seconds
            if t.size:
                t0 = float(np.nanmin(t)); t1 = float(np.nanmax(t))
                span = t1 - t0
                if span <= 0:
                    a, b = t0, t0 + 1.0
                else:
                    width = min(5.0, span)
                    a, b = t0, t0 + width
                self.region.blockSignals(True); self.region.setRegion((a, b)); self.region.blockSignals(False)
                self.spin_t0.blockSignals(True); self.spin_t1.blockSignals(True)
                self.spin_t0.setValue(a); self.spin_t1.setValue(b)
                self.spin_t0.blockSignals(False); self.spin_t1.blockSignals(False)

            self.lbl_info.setText(f"N={t.size} · fs_auto≈{self._fs_auto:.6f} Hz")
            self._replot_all()
        except Exception as e:
            QMessageBox.critical(self, "Load error", str(e))

    # ------------- Helpers -------------
    def _detrend_mode(self) -> str:
        txt = self.cmb_detrend.currentText().lower()
        if "linear" in txt:
            return "linear"
        if "none" in txt:
            return "none"
        return "mean"

    def _effective_fs(self) -> float:
        if self.chk_custom_fs.isChecked():
            return float(self.spin_fs.value())
        return float(self._fs_auto) if self._fs_auto > 0 else max(1e-6, float(self.spin_fs.value()))

    def _current_channel_series(self) -> Tuple[np.ndarray, np.ndarray]:
        if self._t is None or not self._labels:
            return np.array([]), np.array([])
        ch = self.cmb_ch.currentText() if self.cmb_ch.count() else None
        if not ch:
            return np.array([]), np.array([])
        y = self._cols.get(ch)
        if y is None:
            return np.array([]), np.array([])
        mask = np.isfinite(self._t) & np.isfinite(y)
        return self._t[mask], y[mask]

    def _window_mask(self, t: np.ndarray) -> np.ndarray:
        t0 = float(self.spin_t0.value())
        t1 = float(self.spin_t1.value())
        if t1 < t0:
            t0, t1 = t1, t0
        return (t >= t0) & (t <= t1)

    # ------------- Syncs -------------
    def _sync_region_to_spins_then_fft(self) -> None:
        a, b = self.region.getRegion()
        self.spin_t0.blockSignals(True); self.spin_t1.blockSignals(True)
        self.spin_t0.setValue(float(a)); self.spin_t1.setValue(float(b))
        self.spin_t0.blockSignals(False); self.spin_t1.blockSignals(False)
        self._replot_fft_only()

    def _sync_spins_to_region_then_fft(self) -> None:
        a = float(self.spin_t0.value()); b = float(self.spin_t1.value())
        self.region.blockSignals(True); self.region.setRegion((min(a, b), max(a, b))); self.region.blockSignals(False)
        self._replot_fft_only()

    # ------------- Plotting -------------
    def _replot_all(self) -> None:
        # time plot
        self.time_plot.clear()
        t, y = self._current_channel_series()
        if t.size and y.size:
            self.time_plot.plot(t, y)
            # keep and re-add region
            self.time_plot.addItem(self.region)
        # fft
        self._replot_fft_only()

    def _replot_fft_only(self) -> None:
        self.fft_plot.clear()
        t, y = self._current_channel_series()
        if t.size < 2 or y.size < 2:
            return

        m = self._window_mask(t)
        if not np.any(m):
            self.fft_plot.setTitle("No samples in selected window")
            return
        t_win = t[m]
        y_win = y[m]
        if y_win.size < 2:
            self.fft_plot.setTitle("Window too small")
            return

        fs = max(self._effective_fs(), 1e-9)
        detrend = self._detrend_mode()

        # prefer robust FFT if available
        if one_sided_fft is not None:
            try:
                f, mag = one_sided_fft(y_win, fs, detrend=detrend)  # type: ignore[arg-type]
            except Exception:
                f, mag = _fallback_one_sided_fft(y_win, fs, detrend=detrend)
        else:
            f, mag = _fallback_one_sided_fft(y_win, fs, detrend=detrend)

        fmax = float(self.spin_fmax.value())
        if fmax > 0.0:
            sel = f <= fmax
            f, mag = f[sel], mag[sel]

        self.fft_plot.plot(f, mag)
        self.fft_plot.setTitle(f"fs = {fs:.6f} Hz · detrend = {detrend} · window = [{t_win[0]:.3f}, {t_win[-1]:.3f}] s")
