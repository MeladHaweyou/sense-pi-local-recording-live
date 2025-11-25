"""FFT helpers."""

import numpy as np


def compute_fft(signal: np.ndarray, sample_rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Compute frequency bins and magnitudes for a 1-D signal."""
    fft_result = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(signal.size, d=1.0 / sample_rate_hz)
    magnitude = np.abs(fft_result)
    return freqs, magnitude
