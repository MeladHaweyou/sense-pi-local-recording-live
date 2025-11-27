"""Feature extraction helpers."""

import numpy as np


def rms(signal: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(signal))))


def peak_to_peak(signal: np.ndarray) -> float:
    return float(np.max(signal) - np.min(signal))
