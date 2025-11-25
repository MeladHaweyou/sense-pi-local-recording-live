"""Simple smoke test for the MQTTSource stub (returns empty arrays)."""

from __future__ import annotations

import os
import sys

# Ensure the package is importable when running this script directly.
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from ..data.mqtt_source import MQTTSource
from ..core.models import MQTTSettings


def main() -> None:
    src = MQTTSource(MQTTSettings())
    src.start()
    res = src.read(1.0)
    assert isinstance(res, dict), "Expected a dict from read()"
    assert len(res) == 18, "Expected nine slots with timestamps"
    for key, arr in res.items():
        assert len(arr) > 0, f"Expected non-empty array for {key}"
    print("OK")


if __name__ == "__main__":
    main()
