# ui/fft_view.py
from __future__ import annotations

from typing import Tuple, List
import numpy as np

from PySide6.QtWidgets import QWidget, QVBoxLayout
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.cm as cm

# Reuse your helpers
from sonify.notes_method import one_sided_fft, top_n_freqs, map_frequencies

# Optional note-name labeling (works even if pretty_midi not installed)
try:
    import pretty_midi  # type: ignore
    _HAS_PM = True
except Exception:
    pretty_midi = None  # type: ignore
    _HAS_PM = False

_NOTE_NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]


def _hz_to_note_name(f: float) -> str:
    if not _HAS_PM:
        return f"{float(f):.1f} Hz"
    midi = int(round(pretty_midi.hz_to_note_number(float(f))))  # type: ignore
    return _NOTE_NAMES[midi % 12] + str(midi // 12 - 1)


class FFTNotesView(QWidget):
    """
    Two-panel Matplotlib view:
      • left  = natural FFT with peak markers
      • right = mapped FFT (band is adjustable) + note labels

    Public API:
      - set_mapped_xlim(lo_hz, hi_hz): adjust the mapped axis limits & title
      - update_view(...): recompute FFT/peaks and redraw both panels
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.fig = Figure(figsize=(7.8, 3.2), dpi=100)
        self.ax_nat = self.fig.add_subplot(1, 2, 1)
        self.ax_map = self.fig.add_subplot(1, 2, 2)

        self.canvas = FigureCanvas(self.fig)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.canvas)

        # Current mapped-band x-limits (can be changed from the Notes tab)
        self._map_xlim: Tuple[float, float] = (200.0, 1000.0)

        self._setup_axes()

    # ---------------- axes & limits ----------------
    def _setup_axes(self) -> None:
        self.ax_nat.clear()
        self.ax_map.clear()

        self.ax_nat.set_title("Natural FFT")
        self.ax_nat.set_xlabel("Freq [Hz]")
        self.ax_nat.set_ylabel("Amplitude")
        self.ax_nat.grid(True, alpha=0.3)

        lo, hi = self._map_xlim
        self.ax_map.set_title(f"Mapped FFT ({lo:.0f}–{hi:.0f} Hz)")
        self.ax_map.set_xlabel("Freq [Hz]")
        self.ax_map.set_ylabel("Amplitude")
        self.ax_map.grid(True, alpha=0.3)
        self.ax_map.set_xlim(lo, hi)
        self.ax_map.set_ylim(0.0, 1.0)

        self.canvas.draw_idle()

    def _apply_mapped_xlim(self) -> None:
        lo, hi = self._map_xlim
        if hi <= lo:
            # keep sane ordering
            lo, hi = hi, lo
            self._map_xlim = (lo, hi)
        self.ax_map.set_xlim(lo, hi)
        self.ax_map.set_title(f"Mapped FFT ({lo:.0f}–{hi:.0f} Hz)")
        self.canvas.draw_idle()

    def set_mapped_xlim(self, lo_hz: float, hi_hz: float) -> None:
        """
        Public: update the mapped FFT x-axis limits and retitle the panel.
        """
        try:
            lo = float(lo_hz)
            hi = float(hi_hz)
        except Exception:
            return
        # clamp to positive and avoid degenerate limits
        lo = max(1e-6, lo)
        hi = max(1e-6, hi)
        if lo == hi:
            hi = lo * 1.001
        self._map_xlim = (lo, hi)
        self._apply_mapped_xlim()

    # ---------------- main redraw ----------------
    def update_view(
        self,
        signal: np.ndarray,
        fs: float,
        n_peaks: int,
        mapping_method: str,
        *,
        detrend: str = "mean",
        xlim_nat: Tuple[float, float] = (0.0, 10.0),
    ) -> tuple[list[float], list[float], list[str]]:
        """
        Redraw both panels for the given signal & settings.

        Returns:
            (nat_peaks_hz, mapped_peaks_hz, labels)
        """
        self._setup_axes()

        sig = np.asarray(signal, dtype=float).ravel()
        if sig.size == 0 or float(fs) <= 0:
            self.canvas.draw_idle()
            return [], [], []

        # Natural FFT
        f, A = one_sided_fft(sig, float(fs), detrend=detrend)
        self.ax_nat.plot(f, A, lw=0.7, color="k")
        try:
            self.ax_nat.set_xlim(float(xlim_nat[0]), float(xlim_nat[1]))
        except Exception:
            pass

        # Peaks + mapping for preview markers
        n = int(max(1, n_peaks))
        nat = top_n_freqs(sig, float(fs), n, detrend=detrend)
        mapped = map_frequencies(nat, mapping_method)

        labels = [_hz_to_note_name(x) for x in mapped]
        colors = [cm.get_cmap("tab10")(i % 10) for i in range(len(nat))]

        # Markers on natural
        for f0, c in zip(nat, colors):
            self.ax_nat.axvline(float(f0), color=c, ls=":", lw=1.0)

        # Mapped panel markers + labels
        lo, hi = self._map_xlim
        self.ax_map.set_xlim(lo, hi)
        self.ax_map.set_ylim(0.0, 1.0)
        for f1, lab, c in zip(mapped, labels, colors):
            self.ax_map.axvline(float(f1), color=c, ls="--", lw=1.0)
            self.ax_map.text(
                float(f1), 0.92, lab,
                rotation=90, ha="right", va="top",
                transform=self.ax_map.get_xaxis_transform(),
                color=c, fontsize=9,
            )

        self.canvas.draw_idle()
        return list(map(float, nat)), list(map(float, mapped)), labels
