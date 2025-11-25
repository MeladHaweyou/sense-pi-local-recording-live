from __future__ import annotations

import csv
import os
import time
from enum import Enum
from typing import List, Dict

import numpy as np
from PySide6.QtCore import QTimer, Qt, QDateTime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QCheckBox, QDoubleSpinBox, QGroupBox, QRadioButton, QFormLayout
)

from ...core.state import AppState
from ...data.base import DataSource
from ...util.calibration import apply_global_and_scale  # per-slot, like your working code

# --- Constants / helpers -----------------------------------------------------

GYRO_SLOTS = {2, 5, 8}  # i % 3 == 2
_SUFFIX = ("ax", "ay", "gz")


def _compact_label_for_slot(i: int) -> str:
    """
    Map slot index 0..8 -> s{sensor_idx}_{ax|ay|gz}
    sensor_idx = i // 3 in [0,1,2]
    col       = i % 3  -> 0=ax, 1=ay, 2=gz
    """
    sensor_idx = i // 3
    suffix = _SUFFIX[i % 3]
    return f"s{sensor_idx}_{suffix}"


def _all_compact_labels() -> List[str]:
    return [_compact_label_for_slot(i) for i in range(9)]


ALL_LABELS = _all_compact_labels()


class RecMode(Enum):
    DRAIN = 1      # every device sample
    FIXED = 2      # resampled to user Hz
    LEGACY = 3     # old timer-per-estimated-hz


# --- UI ----------------------------------------------------------------------

class CaptureTab(QWidget):
    """
    Recorder (auto-rate, 9 channels total):
      - Reads latest samples from the shared DataSource under keys "slot_0" ... "slot_8".
      - Applies the same per-slot calibration you used before.
      - Saves CSV with headers: timestamp_iso, t_rel_s, s0_ax, s0_ay, s0_gz, s1_ax, ...
      - UI has 9 checkboxes (select any subset to record).
    """

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

        # runtime
        self._recording = False
        self._rows: List[List[float | str]] = []    # [ts_iso, t_rel_s, values...]
        self._t0_monotonic: float | None = None
        self._selected_labels: List[str] = []
        self._rec_mode: RecMode = RecMode.DRAIN
        self._fixed_hz: float = 50.0
        self._last_ts_by_slot: dict[int, float] = {i: -float("inf") for i in range(9)}
        self._last_out_t: float | None = None  # for fixed-rate grid continuity

        # timers
        self._tick: QTimer | None = None
        self._fs_watchdog = QTimer(self)
        self._fs_watchdog.setInterval(2000)
        self._fs_watchdog.timeout.connect(self._maybe_adjust_interval)

        # ui
        self._chk: List[QCheckBox] = []
        self._build_ui()

    # --- Build UI -----------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Top controls
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel("Recorder (live · auto-rate)"))

        self.btn_record = QPushButton("Record")
        self.btn_record.clicked.connect(self.on_record)
        row.addWidget(self.btn_record)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.on_stop)
        row.addWidget(self.btn_stop)

        self.btn_save = QPushButton("Save CSV…")
        self.btn_save.clicked.connect(self.on_save_csv)
        row.addWidget(self.btn_save)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.on_clear)
        row.addWidget(self.btn_clear)

        row.addStretch(1)
        layout.addLayout(row)

        # Channel selection (exactly 9)
        sel = QHBoxLayout()
        sel.setSpacing(8)
        sel.addWidget(QLabel("Channels:"))

        self._chk = []
        for i in range(9):
            cb = QCheckBox(_compact_label_for_slot(i))
            cb.setChecked(True)
            self._chk.append(cb)
            sel.addWidget(cb)

        self.btn_all = QPushButton("All")
        self.btn_all.clicked.connect(self._select_all)
        sel.addWidget(self.btn_all)

        self.btn_none = QPushButton("None")
        self.btn_none.clicked.connect(self._select_none)
        sel.addWidget(self.btn_none)

        sel.addStretch(1)
        layout.addLayout(sel)

        # --- Recording mode group (NEW) ---
        grp = QGroupBox("Recording mode")
        frm = QFormLayout(grp)

        self.rb_drain = QRadioButton("Every sample (drain)")
        self.rb_fixed = QRadioButton("Fixed rate")
        self.rb_legacy = QRadioButton("Timer‑tick (legacy)")
        self.rb_drain.setChecked(True)

        self.spin_fixed = QDoubleSpinBox(); self.spin_fixed.setRange(1.0, 1000.0)
        self.spin_fixed.setDecimals(2); self.spin_fixed.setValue(self._fixed_hz); self.spin_fixed.setSuffix(" Hz")

        # keep simple: enable spin only when fixed-rate is selected
        def _toggle_fixed(_):
            self.spin_fixed.setEnabled(self.rb_fixed.isChecked())
        self.rb_fixed.toggled.connect(_toggle_fixed); _toggle_fixed(None)

        frm.addRow(self.rb_drain)
        frm.addRow(self.rb_fixed, self.spin_fixed)
        frm.addRow(self.rb_legacy)
        layout.addWidget(grp)

        # connect handlers
        self.rb_drain.toggled.connect(lambda v: self._set_mode(RecMode.DRAIN if v else self._rec_mode))
        self.rb_fixed.toggled.connect(lambda v: self._set_mode(RecMode.FIXED if v else self._rec_mode))
        self.rb_legacy.toggled.connect(lambda v: self._set_mode(RecMode.LEGACY if v else self._rec_mode))
        self.spin_fixed.valueChanged.connect(lambda v: setattr(self, "_fixed_hz", float(v)))

        # Status row
        srow = QHBoxLayout()
        srow.setSpacing(8)
        self.lbl_status = QLabel("Idle")
        self.lbl_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        srow.addWidget(self.lbl_status)
        srow.addStretch(1)
        layout.addLayout(srow)

        self.setLayout(layout)

    # --- Selection helpers --------------------------------------------------

    def _current_selection(self) -> List[str]:
        return [_compact_label_for_slot(i) for i, cb in enumerate(self._chk) if cb.isChecked()]

    def _set_selection_enabled(self, enabled: bool) -> None:
        for cb in self._chk:
            cb.setEnabled(enabled)
        self.btn_all.setEnabled(enabled)
        self.btn_none.setEnabled(enabled)

    def _select_all(self) -> None:
        for cb in self._chk:
            cb.setChecked(True)

    def _select_none(self) -> None:
        for cb in self._chk:
            cb.setChecked(False)

    # --- Recording modes ---------------------------------------------------

    def _set_mode(self, m: RecMode) -> None:
        self._rec_mode = m
        # reset per-mode state
        self._last_ts_by_slot = {i: -float("inf") for i in range(9)}
        self._last_out_t = None
        self._update_status()

    def _choose_tick_ms(self) -> int:
        if self._rec_mode is RecMode.LEGACY:
            # derive from device estimate (old behavior)
            try:
                fs = self.state.ensure_source().get_rate().hz_effective
                return max(1, int(round(1000.0 / max(1.0, float(fs)))))
            except Exception:
                return 50
        # For DRAIN or FIXED, UI tick can be modest (drain is not tied to UI tick)
        return 40  # 25 Hz UI tick

    def _maybe_adjust_interval(self) -> None:
        if not self._recording or self._tick is None or self._rec_mode is not RecMode.LEGACY:
            return
        try:
            new_ms = self._choose_tick_ms()
            if new_ms != self._tick.interval():
                self._tick.start(new_ms)
        except Exception:
            pass

    # --- Recording control --------------------------------------------------

    def on_record(self) -> None:
        if self._recording:
            return

        # snapshot selection order
        selected = self._current_selection()
        if not selected:
            QMessageBox.information(self, "No channels selected",
                                    "Please select at least one channel.")
            return
        self._selected_labels = list(selected)
        self._set_selection_enabled(False)

        # Ensure source is running
        try:
            self.state.start_source()
        except Exception as e:
            self._set_selection_enabled(True)
            QMessageBox.critical(self, "Source start failed", str(e))
            return

        # Reset buffers/time
        self._rows.clear()
        self._t0_monotonic = time.monotonic()
        self._last_ts_by_slot = {i: -float("inf") for i in range(9)}
        self._last_out_t = None

        # Start timers based on mode
        if self._tick is None:
            self._tick = QTimer(self)
            self._tick.timeout.connect(self._sample_once)
        self._tick.start(self._choose_tick_ms())
        # watchdog only needed for LEGACY timer drift
        if self._rec_mode is RecMode.LEGACY:
            self._fs_watchdog.start()
        else:
            self._fs_watchdog.stop()

        self._recording = True
        self.btn_record.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._update_status()

    def on_stop(self) -> None:
        self._recording = False
        if self._tick:
            self._tick.stop()
        self._fs_watchdog.stop()
        self.btn_record.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_selection_enabled(True)
        self._update_status()

    def on_clear(self) -> None:
        if self._recording:
            if QMessageBox.question(self, "Clear",
                                    "Recording is active. Stop and clear?") != QMessageBox.Yes:
                return
            self.on_stop()
        self._rows.clear()
        self._t0_monotonic = None
        self._update_status()

    # --- Status -------------------------------------------------------------

    def _update_status(self) -> None:
        n = len(self._rows)
        names_str = ", ".join(self._selected_labels) if self._selected_labels else "-"
        if self._recording and self._t0_monotonic is not None:
            dur = time.monotonic() - self._t0_monotonic
            base = f"● REC  |  {n} samples  |  {dur:0.1f} s  |  {names_str}"
        else:
            base = f"Idle  |  {n} samples  |  {names_str}"

        try:
            dev_hz = float(self.state.ensure_source().get_rate().hz_effective)
        except Exception:
            dev_hz = 0.0

        tick_hz = 0.0
        if self._tick and self._tick.interval() > 0:
            tick_hz = 1000.0 / float(self._tick.interval())

        mode_txt = {
            RecMode.DRAIN: "Every sample",
            RecMode.FIXED: f"Fixed {self._fixed_hz:.1f} Hz",
            RecMode.LEGACY: f"Timer‑tick ~{tick_hz:.1f} Hz",
        }[self._rec_mode]

        self.lbl_status.setText(f"{base}  |  device ~{dev_hz:.1f} Hz  |  mode: {mode_txt}")

    def _set_status(self, txt: str) -> None:
        self.lbl_status.setText(txt)

    # --- Sampling & data path ----------------------------------------------

    def _read_latest_values(self) -> Dict[str, float]:
        """
        Read latest values from the shared DataSource, which implements
        read(window_s) -> {"slot_0": np.ndarray, ..., "slot_8": np.ndarray}.

        Map each slot_i to the compact CSV label and apply per-slot calibration.
        """
        out: Dict[str, float] = {lab: np.nan for lab in ALL_LABELS}

        src: DataSource | None = self.state.ensure_source()
        if src is None:
            return out

        try:
            chunk = src.read(0.5)  # { "slot_0": np.ndarray, ..., "slot_8": np.ndarray }
        except Exception:
            return out

        if not isinstance(chunk, dict):
            return out

        for i in range(9):
            key = f"slot_{i}"
            arr = np.asarray(chunk.get(key, []), dtype=float)
            if arr.size > 0:
                # same per-slot calibration you used previously
                try:
                    arr_cal = apply_global_and_scale(self.state, i, arr)
                    v = float(arr_cal[-1])
                except Exception:
                    v = float(arr[-1])
                out[ALL_LABELS[i]] = v
        return out

    def _sample_once(self) -> None:
        src = self.state.ensure_source()
        try:
            chunk = src.read(1.0)  # recent window incl. slot_ts_i arrays
            if not isinstance(chunk, dict):
                return

            slot_data: dict[int, tuple[np.ndarray, np.ndarray]] = {}
            for i in range(9):
                ts = np.asarray(chunk.get(f"slot_ts_{i}", np.array([])), dtype=float)
                vals = np.asarray(chunk.get(f"slot_{i}", np.array([])), dtype=float)
                if vals.size:
                    try:
                        vals = np.asarray(apply_global_and_scale(self.state, i, vals), dtype=float)
                    except Exception:
                        vals = vals.astype(float, copy=False)
                slot_data[i] = (ts, vals)

            if self._rec_mode is RecMode.DRAIN:
                self._emit_rows_drain(slot_data)
            elif self._rec_mode is RecMode.FIXED:
                self._emit_rows_fixed(slot_data, self._fixed_hz)
            else:  # LEGACY
                self._emit_rows_legacy_snapshot(chunk)
        except Exception as e:
            self._set_status(f"Error: {e}")

    def _sorted_valid(self, ts: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        ts = np.asarray(ts, dtype=float); y = np.asarray(y, dtype=float)
        m = np.isfinite(ts) & np.isfinite(y)
        ts = ts[m]; y = y[m]
        if ts.size:
            idx = np.argsort(ts, kind="mergesort")
            ts = ts[idx]; y = y[idx]
        return ts, y

    def _value_at_or_before(self, ts: np.ndarray, y: np.ndarray, t: float) -> float:
        # step-hold (ZOH) at time t
        if ts.size == 0:
            return float("nan")
        i = np.searchsorted(ts, t, side="right") - 1
        if i < 0:
            return float("nan")
        return float(y[i])

    def _interp_at(self, ts: np.ndarray, y: np.ndarray, t: np.ndarray) -> np.ndarray:
        # linear interpolation without extrapolation
        if ts.size < 2:
            return np.full_like(t, np.nan, dtype=float)
        tmin, tmax = float(ts[0]), float(ts[-1])
        t_clip = np.clip(t, tmin, tmax)
        # mask non-finite y
        m = np.isfinite(y)
        if np.count_nonzero(m) < 2:
            return np.full_like(t, np.nan, dtype=float)
        return np.interp(t_clip, ts[m], y[m])

    def _emit_rows_drain(self, slot_data: dict[int, tuple[np.ndarray, np.ndarray]]) -> None:
        # pace rows by reference channel (slot 0)
        ref = 0
        ts_ref, y_ref = slot_data.get(ref, (np.array([]), np.array([])))
        ts_ref, y_ref = self._sorted_valid(ts_ref, y_ref)
        if ts_ref.size == 0:
            return

        new_mask = ts_ref > self._last_ts_by_slot.get(ref, -float("inf"))
        if not np.any(new_mask):
            return

        ts_new = ts_ref[new_mask]
        self._last_ts_by_slot[ref] = float(ts_ref[-1])

        # Append one row per new ref timestamp; other channels: hold-last value at or before t
        for t_dev in ts_new:
            now_iso = QDateTime.currentDateTime().toString(Qt.ISODateWithMs)
            if self._t0_monotonic is None:
                self._t0_monotonic = time.monotonic()
            # keep t_rel from monotonic but strictly increasing: add a tiny epsilon
            t_rel = time.monotonic() - self._t0_monotonic + 1e-6

            row = [now_iso, f"{t_rel:.6f}"]
            for lab in self._selected_labels:
                i = ALL_LABELS.index(lab)
                ts_i, y_i = slot_data.get(i, (np.array([]), np.array([])))
                ts_i, y_i = self._sorted_valid(ts_i, y_i)
                v = self._value_at_or_before(ts_i, y_i, float(t_dev))
                row.append(v)
                if ts_i.size:
                    self._last_ts_by_slot[i] = max(self._last_ts_by_slot[i], float(ts_i[-1]))
            self._rows.append(row)

        self._update_status()

    def _emit_rows_fixed(self, slot_data: dict[int, tuple[np.ndarray, np.ndarray]], target_hz: float) -> None:
        # grid is derived from reference channel (slot 0); others interp linearly
        ref = 0
        ts_ref, y_ref = slot_data.get(ref, (np.array([]), np.array([])))
        ts_ref, y_ref = self._sorted_valid(ts_ref, y_ref)
        if ts_ref.size < 2 or target_hz <= 0:
            return

        from ...util.resample import resample_to_fixed_rate
        t_out, _y_out_ref, new_last = resample_to_fixed_rate(ts_ref, y_ref, float(target_hz), self._last_out_t)
        if t_out.size == 0:
            return
        self._last_out_t = float(new_last)

        for t_dev in t_out:
            now_iso = QDateTime.currentDateTime().toString(Qt.ISODateWithMs)
            if self._t0_monotonic is None:
                self._t0_monotonic = time.monotonic()
            t_rel = time.monotonic() - self._t0_monotonic + 1e-6

            row = [now_iso, f"{t_rel:.6f}"]
            for lab in self._selected_labels:
                i = ALL_LABELS.index(lab)
                ts_i, y_i = slot_data.get(i, (np.array([]), np.array([])))
                ts_i, y_i = self._sorted_valid(ts_i, y_i)
                v = float(self._interp_at(ts_i, y_i, np.array([t_dev]))[0])
                row.append(v)
                if ts_i.size:
                    self._last_ts_by_slot[i] = max(self._last_ts_by_slot[i], float(ts_i[-1]))
            self._rows.append(row)

        self._update_status()

    def _emit_rows_legacy_snapshot(self, chunk: dict) -> None:
        # this matches your old behavior: snapshot latest values once per tick
        now_iso = QDateTime.currentDateTime().toString(Qt.ISODateWithMs)
        if self._t0_monotonic is None:
            self._t0_monotonic = time.monotonic()
        t_rel = time.monotonic() - self._t0_monotonic
        values = self._read_latest_values()  # reuse your existing helper
        row = [now_iso, f"{t_rel:.6f}"] + [values.get(lab, np.nan) for lab in self._selected_labels]
        self._rows.append(row)
        self._update_status()

    # --- Saving -------------------------------------------------------------

    def on_save_csv(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "Save CSV", "No samples to save yet.")
            return
        if self._recording:
            if QMessageBox.question(self, "Save while recording?",
                                    "Save current buffer to CSV while still recording?") != QMessageBox.Yes:
                return

        default_name = QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
        default_path = os.path.join(os.getcwd(), f"recording_{default_name}.csv")

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save recording as CSV",
            default_path,
            "CSV files (*.csv)"
        )
        if not path:
            return

        try:
            headers = ["timestamp_iso", "t_rel_s"] + self._selected_labels
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(headers)
                w.writerows(self._rows)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return

        QMessageBox.information(self, "Saved", f"Saved {len(self._rows)} samples to:\n{path}")
