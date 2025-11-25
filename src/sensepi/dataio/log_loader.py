"""Utilities for loading recorded CSV logs."""

from pathlib import Path
from typing import Iterable, List, Sequence

import numpy as np


def load_csv(path: Path) -> np.ndarray:
    """Load a CSV file containing numeric data."""
    return np.loadtxt(path, delimiter=",")


def chunk_array(array: np.ndarray, chunk_size: int) -> Iterable[np.ndarray]:
    """Yield fixed-size chunks from an array."""
    total = array.shape[0]
    for start in range(0, total, chunk_size):
        yield array[start : start + chunk_size]


def merge_logs(paths: Sequence[Path]) -> np.ndarray:
    """Load multiple CSV logs and concatenate them along the first axis."""
    arrays: List[np.ndarray] = [load_csv(path) for path in paths]
    if not arrays:
        return np.empty((0, 0))
    return np.concatenate(arrays, axis=0)
