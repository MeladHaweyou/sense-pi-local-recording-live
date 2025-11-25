"""Filtering helpers."""

from typing import Tuple

import numpy as np
from scipy import signal


def butter_lowpass(data: np.ndarray, cutoff_hz: float, sample_rate_hz: float, order: int = 4) -> np.ndarray:
    nyquist = 0.5 * sample_rate_hz
    normal_cutoff = cutoff_hz / nyquist
    b, a = signal.butter(order, normal_cutoff, btype="low", analog=False)
    return signal.filtfilt(b, a, data)


def detrend(data: np.ndarray) -> np.ndarray:
    return signal.detrend(data)
