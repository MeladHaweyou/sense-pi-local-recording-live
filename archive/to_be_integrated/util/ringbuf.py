"""A simple fixed‑size ring buffer for numeric data.

The `RingBuffer` class stores a fixed number of the most recent samples in a
numpy array.  When the buffer fills up it silently overwrites the oldest
samples.  This is useful for implementing moving windows without dynamic
memory allocation.
"""

from __future__ import annotations

import numpy as np


class RingBuffer:
    """Fixed‑length circular buffer for floats.

    Parameters
    ----------
    size : int
        Maximum number of elements to retain.
    """

    def __init__(self, size: int) -> None:
        self.size = int(size)
        self.buffer = np.zeros(self.size, dtype=float)
        self.index: int = 0
        self.full: bool = False

    def push(self, values: np.ndarray | list[float]) -> None:
        """Append one or more values to the buffer."""
        arr = np.asarray(values, dtype=float).ravel()
        for val in arr:
            self.buffer[self.index] = float(val)
            self.index = (self.index + 1) % self.size
            if self.index == 0:
                self.full = True

    def get_last(self, n: int) -> np.ndarray:
        """Return the last ``n`` samples in chronological order."""
        if n <= 0:
            return np.empty(0, dtype=float)
        valid_length = self.size if self.full else self.index
        n = int(min(n, valid_length))
        start = (self.index - n) % self.size
        if start + n <= self.size:
            return self.buffer[start:start + n].copy()
        else:
            part1 = self.buffer[start:]
            part2 = self.buffer[: (start + n) % self.size]
            return np.concatenate((part1, part2))

    def clear(self) -> None:
        """Reset the buffer to its initial empty state."""
        self.buffer.fill(0.0)
        self.index = 0
        self.full = False
