from __future__ import annotations

"""
Notes-based sonification helpers and FluidSynth renderer.

- Puts FluidSynth in 'no audio' mode (render-to-buffer only) before importing pretty_midi.
- Robust FFT + peak mapping to 200–1000 Hz.
- PrettyMIDI + FluidSynth render with selectable instrument and velocity.
- Optional snapping of mapped frequencies to a set of allowed pitch classes (scale).
"""

# ── FluidSynth & SDL env BEFORE pretty_midi import ───────────────────────────
import os, sys
os.environ["FS_AUDIO_DRIVER"] = "null"          # no realtime audio device
os.environ.setdefault("FS_MIDI_DRIVER", "null")
os.environ.setdefault("FS_LOG_LEVEL", "error")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

# Help Windows find FluidSynth DLLs (adjust if yours is elsewhere)
if sys.platform.startswith("win"):
    candidates = [
        os.environ.get("FLUIDSYNTH_BIN", ""),
        r"C:\Program Files\fluidsynth\bin",
        r"C:\Program Files (x86)\fluidsynth\bin",
    ]
    for d in candidates:
        if d and os.path.isdir(d):
            try:
                os.add_dll_directory(d)  # Python 3.8+
            except Exception:
                pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            break

# ── imports ─────────────────────────────────────────────────────────────────
from dataclasses import dataclass
from typing import Iterable, List, Literal, Optional, Sequence

import numpy as np

# robust peak picking (SciPy optional)
try:
    from scipy.signal import find_peaks, detrend as _sp_detrend
    _HAS_SCIPY = True
except Exception:  # pragma: no cover
    _HAS_SCIPY = False
    _sp_detrend = None  # type: ignore

try:
    import pretty_midi  # type: ignore
    _HAS_PRETTY = True
    _IMPORT_ERR: Exception | None = None
except Exception as e:  # pragma: no cover
    pretty_midi = None  # type: ignore
    _HAS_PRETTY = False
    _IMPORT_ERR = e


# ── FFT + peak picking ───────────────────────────────────────────────────────
def one_sided_fft(
    signal: np.ndarray,
    fs: float,
    *,
    detrend: str = "mean",  # 'none' | 'mean' | 'linear'
) -> tuple[np.ndarray, np.ndarray]:
    """
    One-sided FFT using a Hann window; returns (freq_hz, amplitude_linear).

    detrend:
      - 'none'   : no bias removal
      - 'mean'   : subtract mean (default; kills DC spike)
      - 'linear' : subtract best-fit line (SciPy if available; else LSQ fallback)
    """
    x = np.asarray(signal, dtype=float).ravel()
    n = int(x.size)
    if n == 0 or fs <= 0:
        return np.empty(0), np.empty(0)

    if detrend == "mean":
        x = x - float(np.mean(x))
    elif detrend == "linear":
        if _HAS_SCIPY and _sp_detrend is not None:
            x = _sp_detrend(x, type="linear")  # type: ignore
        else:
            t = np.arange(n, dtype=float)
            t -= t.mean()
            denom = float(np.dot(t, t)) or 1.0
            a = float(np.dot(t, x - x.mean())) / denom
            b = float(x.mean())
            x = x - (a * t + b)
    # else 'none'

    window = np.hanning(n)
    amp = 2.0 / n * np.abs(np.fft.rfft(x * window))
    freq = np.fft.rfftfreq(n, d=1.0 / float(fs))
    return freq, amp


def _quad_interp(f: np.ndarray, A: np.ndarray, i: int) -> float:
    """
    Quadratic (parabolic) interpolation around bin i to refine the peak frequency.
    Returns refined frequency in Hz.
    """
    if i <= 0 or i >= A.size - 1:
        return float(f[i])
    a, b, c = float(A[i-1]), float(A[i]), float(A[i+1])
    denom = (a - 2*b + c)
    if denom == 0:
        return float(f[i])
    delta = 0.5 * (a - c) / denom  # shift in bins
    return float(f[i] + delta * (f[1] - f[0]))


def pick_peaks_advanced(
    signal: np.ndarray,
    fs: float,
    n: int,
    *,
    detrend: str = "mean",      # <--- NEW
    min_freq: float = 0.5,
    max_freq: float | None = None,
    min_separation_hz: float = 0.5,
    prominence_rel: float = 0.25,
) -> list[float]:
    """
    Robust top-N peaks with bandlimit, minimum spacing and relative prominence.
    """
    f, A = one_sided_fft(signal, fs, detrend=detrend)  # <--- pass through
    if A.size == 0:
        return []

    # band-limit
    lo = max(min_freq, 0.0)
    hi = max_freq if (max_freq is not None and max_freq > lo) else f[-1]
    m = (f >= lo) & (f <= hi)
    f_band, A_band = f[m], A[m]
    if A_band.size < 3:
        return []

    # absolute prominence threshold from robust stats
    a_med = np.median(A_band)
    a_max = float(A_band.max())
    prom_abs = max(0.0, float(a_med + prominence_rel * (a_max - a_med)))

    # minimum spacing in bins
    df = f_band[1] - f_band[0]
    min_dist_bins = max(1, int(round(min_separation_hz / max(df, 1e-12))))

    if _HAS_SCIPY:
        idx, props = find_peaks(A_band, distance=min_dist_bins, prominence=prom_abs)
        scores = props.get("prominences", A_band[idx])
    else:
        # simple fallback: local maxima + distance + amplitude threshold
        idx = np.where((A_band[1:-1] > A_band[:-2]) & (A_band[1:-1] >= A_band[2:]))[0] + 1
        idx = idx[A_band[idx] >= prom_abs]
        # greedy non-maximum suppression by amplitude
        idx = idx[np.argsort(A_band[idx])[::-1]]
        kept = []
        last_bin = -10**9
        for i in idx:
            if (i - last_bin) >= min_dist_bins:
                kept.append(i); last_bin = i
        idx = np.array(kept, dtype=int)
        scores = A_band[idx] if idx.size else np.array([], dtype=float)

    if idx.size == 0:
        return []

    # sort by score, take top N
    order = np.argsort(scores)[::-1][: int(max(1, n))]
    idx = idx[order]

    # refine frequency with quadratic interpolation
    out = []
    for i in idx:
        # map band index back to full-fft index
        full_i = np.nonzero(m)[0][i]
        out.append(_quad_interp(f, A, full_i))
    # sort ascending if you want fundamentals first visually
    return sorted(out)


def top_n_freqs(signal: np.ndarray, fs: float, n: int, *, detrend: str = "mean") -> List[float]:
    """Strongest n peaks by amplitude (DC bin always dropped)."""
    freq, amp = one_sided_fft(signal, fs, detrend=detrend)
    if freq.size <= 1:
        return []
    freq, amp = freq[1:], amp[1:]  # drop DC bin
    if amp.size == 0:
        return []
    idx = np.argsort(amp)[-int(max(1, n)) :][::-1]
    return freq[idx].tolist()


# ── mapping to an audible band ───────────────────────────────────────────────
MappingMethod = Literal[
    "Linear scale",
    "Octave shift",
    "Nearest note",
    "Constant offset",
]

def _nearest_note_hz(f: float) -> float:
    """Snap a frequency to the nearest MIDI pitch and convert back to Hz."""
    if not pretty_midi:
        return float(f)
    midi = int(round(pretty_midi.hz_to_note_number(float(f))))  # type: ignore
    return float(pretty_midi.note_number_to_hz(midi))  # type: ignore


def map_frequencies(
    freqs: List[float],
    method: MappingMethod,
    ref_note_hz: float = 261.63,  # C4
    scale: float | None = None,
) -> List[float]:
    """
    Map frequencies into 200–1000 Hz using the selected method.
    If method is 'Linear scale', the first frequency is scaled to ref_note_hz.
    """
    if not freqs:
        return []
    mapped: List[float] = []

    if method == "Linear scale":
        factor = (ref_note_hz / max(freqs[0], 1e-6)) if (scale is None) else float(scale)
        mapped = [float(f) * factor for f in freqs]
    elif method == "Octave shift":
        for f in freqs:
            f = float(f)
            while f < 20.0:
                f *= 2.0
            mapped.append(f)
    elif method == "Nearest note":
        factor = ref_note_hz / max(freqs[0], 1e-6)
        mapped = [_nearest_note_hz(float(f) * factor) for f in freqs]
    elif method == "Constant offset":
        offset = ref_note_hz - float(freqs[0])
        mapped = [float(f) + offset for f in freqs]
    else:
        mapped = [float(f) for f in freqs]

    # Clamp into 200..1000 Hz via octave shifts
    audible: List[float] = []
    for f in mapped:
        while f < 200.0:
            f *= 2.0
        while f > 1000.0:
            f /= 2.0
        audible.append(float(f))
    return audible


# ── scale constraint (allowed pitch classes) ─────────────────────────────────
_PCS = {
    "C":0, "C#":1, "Db":1, "D":2, "D#":3, "Eb":3, "E":4, "Fb":4, "E#":5,
    "F":5, "F#":6, "Gb":6, "G":7, "G#":8, "Ab":8, "A":9, "A#":10, "Bb":10, "B":11, "Cb":11, "B#":0
}

def snap_hz_to_allowed_pitch_classes(f_hz: float, allowed_pcs: Sequence[int]) -> float:
    """Quantize frequency to the nearest MIDI note whose pitch class is in allowed_pcs."""
    if f_hz <= 0 or not allowed_pcs:
        return float(f_hz)
    m_real = 69.0 + 12.0 * np.log2(float(f_hz) / 440.0)
    k0 = int(np.floor(m_real))
    best_k, best_err = k0, float("inf")
    for delta in range(-24, 25):  # ±2 octaves search is plenty
        k = k0 + delta
        if (k % 12) in allowed_pcs:
            err = abs(k - m_real)
            if err < best_err:
                best_k, best_err = k, err
                if err < 0.5:  # already nearest semitone
                    pass
    return float(440.0 * (2.0 ** ((best_k - 69.0) / 12.0)))

def constrain_to_pitch_classes(freqs_hz: Sequence[float], allowed_pcs: Sequence[int]) -> List[float]:
    """Apply snap_hz_to_allowed_pitch_classes to each frequency."""
    if not allowed_pcs:
        return [float(f) for f in freqs_hz]
    return [snap_hz_to_allowed_pitch_classes(float(f), allowed_pcs) for f in freqs_hz]


# ── FluidSynth renderer (PrettyMIDI) ─────────────────────────────────────────
PlayMode = Literal[
    "Method 1 – Sweep",
    "Method 2A – Sequence",
    "Method 2B – Chord",
    "Method 3 – Scale melody",
    "Method 4 – AM-Chord",
]

@dataclass
class FluidConfig:
    sample_rate: int = 44100
    note_ms: int = 120
    transpose_st: int = 0
    mode: PlayMode = "Method 2A – Sequence"
    soundfont_path: str = ""      # must exist
    instrument: int = 0           # GM program (0–127)
    velocity: int = 110           # 1–127


class FluidNoteEngine:
    """Render mono float32 PCM chunks from a list of pitches via PrettyMIDI → FluidSynth."""

    def __init__(self, cfg: FluidConfig) -> None:
        if not _HAS_PRETTY:  # env-specific failure
            raise RuntimeError(
                f"pretty_midi import failed: {str(_IMPORT_ERR) if _IMPORT_ERR else 'unknown error'}"
            )
        if not cfg.soundfont_path or not os.path.isfile(cfg.soundfont_path):
            raise RuntimeError("SoundFont (.sf2) not found or not set.")
        self.cfg = cfg
        self._seq_idx = 0

    # live updaters
    def set_mode(self, mode: PlayMode) -> None:
        self.cfg.mode = mode

    def set_transpose(self, semitones: int) -> None:
        self.cfg.transpose_st = int(semitones)

    def set_note_ms(self, ms: int) -> None:
        self.cfg.note_ms = max(20, int(ms))

    def set_soundfont(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            raise RuntimeError("SoundFont (.sf2) not found or not set.")
        self.cfg.soundfont_path = path

    def set_instrument(self, program: int) -> None:
        self.cfg.instrument = int(np.clip(program, 0, 127))

    def set_velocity(self, velocity: int) -> None:
        self.cfg.velocity = int(np.clip(velocity, 1, 127))

    def render_chunk(self, pitches_hz: Iterable[float]) -> np.ndarray:
        """Render a mono float32 buffer of length note_ms * sr / 1000 from pitches_hz."""
        pitches = list(pitches_hz) or [440.0]

        # transpose in Hz
        factor = 2 ** (self.cfg.transpose_st / 12.0)
        pitches = [float(p) * factor for p in pitches]

        dur = float(self.cfg.note_ms) / 1000.0
        sr = int(self.cfg.sample_rate)
        vel = int(self.cfg.velocity)

        pm = pretty_midi.PrettyMIDI()  # type: ignore
        inst = pretty_midi.Instrument(program=int(self.cfg.instrument))  # type: ignore

        mode = self.cfg.mode
        if mode == "Method 1 – Sweep":
            steps = max(3, len(pitches))
            for f in np.linspace(pitches[0], pitches[-1], steps):
                inst.notes.append(
                    pretty_midi.Note(velocity=vel,
                                     pitch=int(pretty_midi.hz_to_note_number(float(f))),  # type: ignore
                                     start=0.0, end=max(0.02, dur / steps))
                )
        elif mode in ("Method 2B – Chord", "Method 4 – AM-Chord"):
            for f in pitches:
                inst.notes.append(
                    pretty_midi.Note(velocity=max(1, vel - 10),
                                     pitch=int(pretty_midi.hz_to_note_number(float(f))),  # type: ignore
                                     start=0.0, end=dur)
                )
        else:  # Sequence / Scale melody
            f = float(pitches[self._seq_idx % len(pitches)])
            self._seq_idx += 1
            inst.notes.append(
                pretty_midi.Note(velocity=vel,
                                 pitch=int(pretty_midi.hz_to_note_number(f)),  # type: ignore
                                 start=0.0, end=dur)
            )

        pm.instruments.append(inst)  # type: ignore
        buf = pm.fluidsynth(fs=sr, sf2_path=self.cfg.soundfont_path)  # type: ignore

        # mixdown to mono if needed
        if buf.ndim > 1:
            buf = buf.mean(axis=1)

        n = int(round(dur * sr))
        if buf.shape[0] < n:
            buf = np.pad(buf, (0, n - buf.shape[0]))
        return buf[:n].astype(np.float32)
