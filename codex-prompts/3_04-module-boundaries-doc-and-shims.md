# Prompt: Clarify module boundaries and add package docstrings/shims

You are working in the SensePi repository. Your task is to **make package responsibilities obvious for students** by:

1. Adding/expanding package-level docstrings.
2. Optionally adding small import shims so that “core” vs “data” buffers are easier to reason about, without breaking existing imports.

Focus on the top-level packages under `src/sensepi`:

- `analysis`
- `config`
- `core`
- `data`
- `dataio`
- `gui`
- `remote`
- `sensors`
- `tools`

---

## Step 1 – Add or improve package-level docstrings

For each package, edit its `__init__.py` to include a **clear, one-paragraph docstring** describing its role.

Use wording similar to the following (adapt to actual contents):

```python
# src/sensepi/analysis/__init__.py
"""Signal analysis utilities (FFT, filtering, feature extraction).

This package contains small, pure-Python helpers that operate on arrays of
sensor data. They have no Qt or I/O dependencies so they can be re-used in
both live and offline analyses.
"""
```

```python
# src/sensepi/config/__init__.py
"""Configuration objects and helpers for SensePi.

This package loads and saves YAML configuration files such as:
- `hosts.yaml` – known Raspberry Pi devices
- `sensors.yaml` – default sensor settings
It exposes typed configuration objects used by the rest of the application.
"""
```

```python
# src/sensepi/core/__init__.py
"""Core streaming pipeline: sessions, buffers, and data flow.

This package coordinates live data streaming on the PC side:
- Recorder sessions
- In-memory buffers for recent samples
- High-level pipeline wiring between remote input, GUI, and disk.
"""
```

```python
# src/sensepi/data/__init__.py
"""Generic streaming data buffers and queues for sensor samples.

These classes provide in-memory storage (ring buffers, queues) that other
parts of the system use to pass sensor data between threads and components.
"""
```

```python
# src/sensepi/dataio/__init__.py
"""Data input/output helpers (CSV/JSON logs).

This package is responsible for saving sensor data to disk and loading
recorded logs back into memory for offline analysis or plotting.
"""
```

```python
# src/sensepi/gui/__init__.py
"""Desktop GUI implementation built with PySide6/Qt.

The GUI layer presents configuration, live plots, FFT views, and offline
recordings to the user. It delegates low-level streaming to `remote` and
`core` packages.
"""
```

```python
# src/sensepi/remote/__init__.py
"""Remote communication with the Raspberry Pi.

Classes here (e.g. `PiRecorder`, `SensorIngestWorker`) connect over SSH,
start sensor logging scripts on the Pi, and stream data back to the PC.
"""
```

```python
# src/sensepi/sensors/__init__.py
"""Sensor-specific data models and parsers.

Each supported sensor has its own module (e.g. `mpu6050`) defining:
- Data structures for a single sample
- Parsers that convert raw/JSON data into those structures.
"""
```

```python
# src/sensepi/tools/__init__.py
"""Miscellaneous development tools and helpers.

This package contains optional utilities such as:
- Standalone plot runners
- Performance/benchmark scripts
- Data decimation helpers reused by the GUI offline viewer.
"""
```

Adjust the bullet points to match the actual modules present. The goal is that a new student can open `__init__.py` and understand what “lives” in that package.

---

## Step 2 – Make buffer locations clearer with import shims

If the project uses both `sensepi.core` and `sensepi.data` for **buffer classes** (e.g. `RingBuffer`, `TimeSeriesBuffer`, `StreamingDataBuffer`), make their location explicit and add **backwards-compatible imports**.

1. Inspect these modules and confirm where buffers live:
   - `src/sensepi/core/ringbuffer.py` (or similar)
   - `src/sensepi/core/timeseries_buffer.py` (or similar)
   - `src/sensepi/data/stream_buffer.py`

2. If some buffer implementations live in `core` but logically belong to `data`, you have two options:

   **Option A – keep files where they are, just document**

   - In `src/sensepi/core/__init__.py`, add comments grouping “data structures” vs “controllers”.
   - Example:

     ```python
     # Data structures used by the streaming pipeline
     from .ringbuffer import RingBuffer  # circular buffer for recent samples
     from .timeseries_buffer import TimeSeriesBuffer  # time-indexed buffer
     ```

   **Option B – move low-level buffers into `sensepi.data` and add shims**

   - Physically move `ringbuffer.py` and `timeseries_buffer.py` into `src/sensepi/data/`.
   - Update `src/sensepi/data/__init__.py`:

     ```python
     """Generic streaming data buffers and queues for sensor samples."""

     from .stream_buffer import StreamingDataBuffer

     # Re-export moved classes for convenience
     try:
         from .ringbuffer import RingBuffer  # noqa: F401
         from .timeseries_buffer import TimeSeriesBuffer  # noqa: F401
     except ImportError:
         # If these modules are renamed later, keep this defensive
         pass
     ```

   - Add a small **shim** in `src/sensepi/core/__init__.py` so older imports keep working:

     ```python
     # Backwards-compatible imports for code that expects buffers in sensepi.core
     try:
         from sensepi.data.ringbuffer import RingBuffer  # noqa: F401
         from sensepi.data.timeseries_buffer import TimeSeriesBuffer  # noqa: F401
     except ImportError:
         pass
     ```

   - Search the codebase for imports like:

     ```python
     from sensepi.core.ringbuffer import RingBuffer
     ```

     and either leave them (they will still work thanks to the shim) or update them to the new location:

     ```python
     from sensepi.data.ringbuffer import RingBuffer
     ```

   Choose the option that best matches the actual current layout. If moving files feels too risky, **just do Option A** and add clear comments/docstrings.

---

## Step 3 – Clarify tools vs core plotting

The `sensepi.tools` package may contain a `plotter.py` module that is used by the GUI’s Offline/Recordings tab for decimating data before plotting.

To reduce confusion:

1. Open `src/sensepi/tools/plotter.py` and add a docstring to the module and the main class (e.g. `Plotter`):

   ```python
   """Helpers for decimating and smoothing time-series data for plotting.

   The Offline/Recordings GUI tab reuses these helpers to plot large CSV logs
   efficiently without overwhelming the GUI.
   """
   ```

   ```python
   class Plotter:
       """Prepare decimated/smoothed data for visualisation.

       This class is used by the offline viewer to downsample long time-series
       while preserving overall shape and extrema.
       """
   ```

2. In `src/sensepi/gui/tabs/tab_offline.py` (or wherever the Offline/Recordings tab lives), add a short comment near the import:

   ```python
   # Decimation helper used to downsample long recordings for plotting
   from sensepi.tools.plotter import Plotter
   ```

This makes it obvious to students that `tools.plotter` is not a random script but part of the plotting pipeline.

---

## Step 4 – Sanity checks

- Ensure all packages still import correctly (run `python -m sensepi.gui` or the test suite).
- If you moved files, make sure there are **no broken imports**; the shims in `__init__.py` should prevent regressions.
- Read through each `__init__.py` to confirm the descriptions match reality; adjust wording if some modules differ.

The goal is **clarity**, not large-scale reorganisation: a new student should be able to guess where a piece of code lives just from these package docstrings and comments.
