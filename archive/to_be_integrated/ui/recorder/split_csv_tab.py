from __future__ import annotations

import csv
import os
import re
from typing import List, Dict, Optional

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog,
    QTableWidget, QTableWidgetItem, QMessageBox, QAbstractItemView, QComboBox
)

from ...core.state import AppState


def _safe_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name or "slice"


class SplitCSVTab(QWidget):
    """
    Split a recorded CSV into multiple CSVs by [start,end] seconds (t_rel_s).

    Additions:
      • Preview: choose which column to visualize to help pick ranges.
      • Splitting always keeps ALL columns; preview choice does not affect output.
    """

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

        self._path: Optional[str] = None
        self._header: List[str] = []
        self._rows: List[List[str]] = []
        self._t: Optional[np.ndarray] = None
        self._labels: List[str] = []
        self._cols: Dict[str, np.ndarray] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.btn_open = QPushButton("Open CSV…")
        self.btn_open.clicked.connect(self.on_open)
        self.lbl_file = QLabel("No file loaded")
        self.lbl_file.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.btn_open)

        top.addStretch(1)
        top.addWidget(self.lbl_file)
        root.addLayout(top)

        # Preview controls
        prev_bar = QHBoxLayout()
        prev_bar.addWidget(QLabel("Preview column:"))
        self.cmb_col = QComboBox()
        self.cmb_col.currentIndexChanged.connect(self._redraw_preview)
        prev_bar.addWidget(self.cmb_col)
        prev_bar.addStretch(1)
        root.addLayout(prev_bar)

        # Preview plot
        self.preview = pg.PlotWidget()
        self.preview.showGrid(x=True, y=True, alpha=0.25)
        self.preview.setLabel("bottom", "t", units="s")
        root.addWidget(self.preview)

        # Table for ranges
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Start (s)", "End (s)", "Output name"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        root.addWidget(self.table)

        rowbar = QHBoxLayout()
        self.btn_add = QPushButton("Add Row")
        self.btn_del = QPushButton("Delete Selected")
        self.btn_add.clicked.connect(self.on_add)
        self.btn_del.clicked.connect(self.on_del)
        rowbar.addWidget(self.btn_add)
        rowbar.addWidget(self.btn_del)
        rowbar.addStretch(1)
        root.addLayout(rowbar)

        self.btn_split = QPushButton("Split & Save to ./outputs")
        self.btn_split.clicked.connect(self.on_split)
        root.addWidget(self.btn_split)

        self.setLayout(root)

    # ------------- File -------------
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
                rows: List[List[str]] = []
                t: List[float] = []
                cols: Dict[str, List[float]] = {lab: [] for lab in labels}
                for row in rdr:
                    if not row:
                        continue
                    rows.append(row)
                    try:
                        t.append(float(row[1]))
                    except Exception:
                        t.append(np.nan)
                    for i, lab in enumerate(labels, start=2):
                        try:
                            v = row[i]
                            cols[lab].append(float(v) if v != '' else np.nan)
                        except Exception:
                            cols[lab].append(np.nan)

            self._path = path
            self._header = header
            self._rows = rows
            self._labels = labels
            self._t = np.asarray(t, dtype=float)
            self._cols = {k: np.asarray(v, dtype=float) for k, v in cols.items()}

            self.lbl_file.setText(os.path.basename(path) + f"  (rows: {len(rows)})")
            self.table.setRowCount(0)

            # Fill preview combobox
            self.cmb_col.blockSignals(True)
            self.cmb_col.clear()
            self.cmb_col.addItems(self._labels)
            self.cmb_col.blockSignals(False)

            self._redraw_preview()
        except Exception as e:
            QMessageBox.critical(self, "Load error", str(e))

    def _redraw_preview(self) -> None:
        self.preview.clear()
        if self._t is None or not self._labels:
            return
        lab = self.cmb_col.currentText() if self.cmb_col.count() else None
        if not lab:
            return
        y = self._cols.get(lab)
        if y is None:
            return
        mask = np.isfinite(self._t) & np.isfinite(y)
        if not np.any(mask):
            return
        self.preview.plot(self._t[mask], y[mask], pen=pg.mkPen(width=1.6))

    # ------------- Table -------------
    def on_add(self) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem("0.0"))
        self.table.setItem(r, 1, QTableWidgetItem("1.0"))
        base = f"slice_{r+1:02d}"
        self.table.setItem(r, 2, QTableWidgetItem(base))

    def on_del(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    # ------------- Split -------------
    def on_split(self) -> None:
        if self._t is None or self._path is None:
            QMessageBox.information(self, "No file", "Load a CSV first.")
            return

        os.makedirs("outputs", exist_ok=True)
        tmax = float(np.nanmax(self._t)) if self._t.size else 0.0

        n_saved = 0
        for r in range(self.table.rowCount()):
            try:
                t0 = float(self.table.item(r, 0).text())
                t1 = float(self.table.item(r, 1).text())
                name = _safe_name(self.table.item(r, 2).text())
            except Exception:
                QMessageBox.warning(self, "Invalid row", f"Row {r+1} has invalid values.")
                continue

            if not (0.0 <= t0 < t1 <= max(tmax, t1)):
                QMessageBox.warning(self, "Invalid range", f"Row {r+1}: check Start/End times.")
                continue

            mask = (self._t >= t0) & (self._t <= t1)
            idx = np.nonzero(mask)[0]
            if idx.size == 0:
                QMessageBox.information(self, "Empty slice", f"Row {r+1}: no samples in range.")
                continue

            out_path = os.path.join("outputs", name if name.lower().endswith('.csv') else name + ".csv")
            try:
                with open(out_path, "w", newline="", encoding="utf-8") as f:
                    wr = csv.writer(f)
                    wr.writerow(self._header)
                    for i in idx.tolist():
                        wr.writerow(self._rows[i])
                n_saved += 1
            except Exception as e:
                QMessageBox.critical(self, "Write error", f"{name}: {e}")

        QMessageBox.information(self, "Done", f"Saved {n_saved} file(s) to ./outputs/")
