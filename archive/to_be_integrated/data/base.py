"""Abstract interface for data sources.

All data sources used by the application should inherit from
:class:`DataSource` and implement its methods.  This base class does
not impose any threading model; implementations may use background
threads internally but should not expose them to the GUI layer.  The
:func:`read` method must always return a dictionary with a key for each
of the nine slots (``"slot_0"`` through ``"slot_8"``).  Arrays
associated with disabled slots should be empty.
"""

from __future__ import annotations

import numpy as np
from typing import Dict


class DataSource:
    """Protocol for data sources.

    Subclasses must implement ``start()``, ``stop()`` and ``read()``.  The
    base class does not provide any default behaviour.
    """

    def start(self) -> None:
        """Begin acquiring data.

        This method should establish any connections or initialise any
        resources required by the data source.  It should be idempotent: a
        subsequent call should have no effect if the source is already
        started.
        """
        raise NotImplementedError

    def stop(self) -> None:
        """Cease acquiring data and release resources.

        Implementations should ensure that all resources (e.g. sockets,
        file handles, background threads) are cleanly disposed.  It should
        be safe to call this method on an instance that is not currently
        started.
        """
        raise NotImplementedError

    def read(self, last_seconds: float) -> Dict[str, np.ndarray]:
        """Return the most recent data for each slot.

        The implementation should produce arrays of equal length for all
        slots that are enabled in the GUI.  The number of samples to
        return is determined by the ``last_seconds`` parameter, but
        implementations are free to choose an internal sampling frequency.
        Disabled slots should be represented by empty arrays.  The keys
        must be strings of the form ``slot_0``, ``slot_1``, … ``slot_8``.

        Parameters
        ----------
        last_seconds : float
            Time window length in seconds for which data should be
            returned.

        Returns
        -------
        Dict[str, numpy.ndarray]
            Mapping of slot identifiers to 1‑D numpy arrays.
        """
        raise NotImplementedError
