from __future__ import annotations

import csv
from typing import List, Dict, Optional

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDoubleSpinBox, QFileDialog, QGridLayout, QCheckBox, QMessageBox,
    QGroupBox
)

from ...core.state import AppState


class ViewCSVTab(QWidget):
    """
    Offline visualization of a previously recorded CSV (Capture format).

    Behavior per your request:
      • No playback. Just plot the loaded data.
      • Controls:
          - Open CSV…
          - Global X range: Xmin (s), Xmax (s), and Auto-X
          - Per-plot Y range: click a plot to select it, then set Ymin/Ymax or Auto-Y
          - Enable/Disable channels

    Assumes CSV header: timestamp_iso, t_rel_s, <compact labels...>
    """

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

        self._t: Optional[np.ndarray] = None
        self._cols: Dict[str, np.ndarray] = {}
        self._labels: List[str] = []

        self._plots: List[pg.PlotWidget] = []
        self._curves: Dict[str, pg.PlotDataItem] = {}
        self._chb: Dict[str, QCheckBox] = {}

        self._selected_plot_index: Optional[int] = None

        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # Top bar
        top = QHBoxLayout()

        self.btn_open = QPushButton("Open CSV…")
        self.btn_open.clicked.connect(self.on_open)
        top.addWidget(self.btn_open)

        # Global X controls
        top.addWidget(QLabel("X min (s):"))
        self.spin_xmin = QDoubleSpinBox(); self.spin_xmin.setRange(-1e12, 1e12); self.spin_xmin.setDecimals(6)
        self.spin_xmin.valueChanged.connect(self._apply_x_range)
        top.addWidget(self.spin_xmin)

        top.addWidget(QLabel("X max (s):"))
        self.spin_xmax = QDoubleSpinBox(); self.spin_xmax.setRange(-1e12, 1e12); self.spin_xmax.setDecimals(6)
        self.spin_xmax.valueChanged.connect(self._apply_x_range)
        top.addWidget(self.spin_xmax)

        self.btn_auto_x = QPushButton("Auto X")
        self.btn_auto_x.clicked.connect(self._auto_x)
        top.addWidget(self.btn_auto_x)

        # Per-plot Y controls (apply to selected plot)
        top.addSpacing(12)
        top.addWidget(QLabel("Selected plot Y min:"))
        self.spin_ymin = QDoubleSpinBox(); self.spin_ymin.setRange(-1e12, 1e12); self.spin_ymin.setDecimals(6)
        self.spin_ymin.valueChanged.connect(self._apply_selected_y_range)
        top.addWidget(self.spin_ymin)

        top.addWidget(QLabel("Y max:"))
        self.spin_ymax = QDoubleSpinBox(); self.spin_ymax.setRange(-1e12, 1e12); self.spin_ymax.setDecimals(6)
        self.spin_ymax.valueChanged.connect(self._apply_selected_y_range)
        top.addWidget(self.spin_ymax)

        self.btn_auto_y = QPushButton("Auto Y (selected)")
        self.btn_auto_y.clicked.connect(self._auto_selected_y)
        top.addWidget(self.btn_auto_y)

        top.addStretch(1)
        self.lbl_info = QLabel("No file loaded")
        self.lbl_info.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.lbl_info)

        root.addLayout(top)

        # Channel enable toggles
        grp = QGroupBox("Channels")
        h = QHBoxLayout(grp)
        self._toggle_box = h
        root.addWidget(grp)

        # 3x3 grid plots
        grid = QGridLayout()
        grid.setSpacing(6)
        for r in range(3):
            for c in range(3):
                pw = pg.PlotWidget()
                pw.showGrid(x=True, y=True, alpha=0.25)
                pw.setLabel("bottom", "t", units="s")
                pw.setMouseEnabled(x=True, y=True)
                idx = len(self._plots)
                pw.scene().sigMouseClicked.connect(lambda ev, i=idx: self._on_plot_clicked(i))
                self._plots.append(pw)
                grid.addWidget(pw, r, c)
        root.addLayout(grid)

        self.setLayout(root)

    # ---------------- File I/O ----------------
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

            self._rebuild_toggles()

            # Initial X and Y ranges
            if t.size > 0:
                self.spin_xmin.blockSignals(True); self.spin_xmax.blockSignals(True)
                self.spin_xmin.setValue(float(np.nanmin(t)))
                self.spin_xmax.setValue(float(np.nanmax(t)))
                self.spin_xmin.blockSignals(False); self.spin_xmax.blockSignals(False)

            self._redraw_all()
            dur = (t[-1] - t[0]) if t.size > 1 else 0.0
            self.lbl_info.setText(f"{len(t)} rows · {len(labels)} channels · dur={dur:.2f}s")
        except Exception as e:
            QMessageBox.critical(self, "Load error", str(e))

    def _rebuild_toggles(self) -> None:
        # clear toggles
        while self._toggle_box.count():
            item = self._toggle_box.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        self._chb.clear()

        # add toggles
        for i, lab in enumerate(self._labels):
            cb = QCheckBox(lab)
            cb.setChecked(True)
            cb.stateChanged.connect(self._redraw_all)
            self._chb[lab] = cb
            self._toggle_box.addWidget(cb)

        # quick toggles
        btn_all = QPushButton("Enable All")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none = QPushButton("Enable None")
        btn_none.clicked.connect(lambda: self._set_all(False))
        self._toggle_box.addWidget(btn_all)
        self._toggle_box.addWidget(btn_none)
        self._toggle_box.addStretch(1)

    def _set_all(self, enabled: bool) -> None:
        for cb in self._chb.values():
            cb.blockSignals(True)
            cb.setChecked(enabled)
            cb.blockSignals(False)
        self._redraw_all()

    # ---------------- Plotting ----------------
    def _on_plot_clicked(self, idx: int) -> None:
        self._selected_plot_index = idx
        # lightly indicate selection
        for i, pw in enumerate(self._plots):
            pw.setTitle("Selected" if i == idx else "")

    def _apply_x_range(self) -> None:
        xmin = float(self.spin_xmin.value())
        xmax = float(self.spin_xmax.value())
        if xmax <= xmin:
            return
        for pw in self._plots:
            try:
                pw.enableAutoRange('x', False)
                pw.setXRange(xmin, xmax, padding=0)
            except Exception:
                pass

    def _auto_x(self) -> None:
        for pw in self._plots:
            try:
                pw.enableAutoRange('x', True)
            except Exception:
                pass

    def _apply_selected_y_range(self) -> None:
        if self._selected_plot_index is None:
            return
        ymin = float(self.spin_ymin.value())
        ymax = float(self.spin_ymax.value())
        if ymax <= ymin:
            return
        pw = self._plots[self._selected_plot_index]
        try:
            pw.enableAutoRange('y', False)
            pw.setYRange(ymin, ymax, padding=0)
        except Exception:
            pass

    def _auto_selected_y(self) -> None:
        if self._selected_plot_index is None:
            return
        pw = self._plots[self._selected_plot_index]
        try:
            pw.enableAutoRange('y', True)
        except Exception:
            pass

    def _redraw_all(self) -> None:
        if self._t is None:
            return
        t = self._t

        # clear plots and curves
        for pw in self._plots:
            pw.clear()
        self._curves.clear()

        enabled = [lab for lab, cb in self._chb.items() if cb.isChecked()]
        if not enabled:
            return

        # draw enabled channels distributed across plot widgets
        for i, lab in enumerate(enabled):
            pw = self._plots[i % len(self._plots)]
            y = self._cols.get(lab)
            if y is None:
                continue
            curve = pw.plot(t, y, pen=pg.mkPen(width=1.8))
            self._curves[lab] = curve

        # Apply current X range if not in auto
        self._apply_x_range()
