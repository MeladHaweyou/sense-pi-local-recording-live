# SensePi New GUI Design

## Overview
The current GUI centers around `MainWindow` wiring together workflow tabs: **Device** (`RecorderTab`), **Sensors & Rates** (`SettingsTab`), **Live Signals** (`SignalsTab`), **Spectrum** (`FftTab`), **Recordings** (`OfflineTab`), and **App Logs** (`LogsTab`). RecorderTab handles host discovery and sensor/channel toggles while orchestrating recording/streaming jobs. SignalsTab consumes streamed samples for pyqtgraph plots, controls acquisition refresh, and initiates start/stop. FftTab reads from SignalsTab/RecorderTab buffers to display spectra. OfflineTab lists on-device and local recordings with sync helpers, and LogsTab shows application logs.

## New Layout
The redesigned interface keeps a tabbed workflow but separates responsibilities to satisfy the new requirements and highlight device/sensor setup, acquisition rates, live plotting, spectral view, and recordings/imports.

### Tabs / Windows

1. **Device & Sensors**
   - Host selection (Raspberry Pi / remote device) with discovered host list from existing YAML configs.
   - Sensor selection and count per host, including per-sensor channel presets (accelerometer, gyroscope, or both/6-axis).
   - Calibration entry point to capture a baseline and zero gravity components before streaming/recording.

2. **Acquisition & Rates**
   - Sampling rate and recording mode (FIFO/stream) using the existing SamplingConfig defaults.
   - Streaming/plotting rate preview derived from sampling + decimation, with an explicit “Record only (no live streaming)” toggle.
   - Controls for GUI refresh cadence (adaptive vs fixed intervals) shared by signals and FFT views.

3. **Live Signals**
   - Multi-sensor, multi-channel time-series plots using pyqtgraph with grid layout driven by chosen channels.
   - Status indicator showing whether streaming is active or disabled due to record-only mode.
   - Per-sensor visibility presets plus calibration status/controls.

4. **Spectrum (FFT)**
   - Dedicated FFT/spectrum view fed from the same data as Live Signals.
   - Shares sampling/streaming config but may expose its own refresh interval when adaptive plotting is insufficient.

5. **Recordings**
   - Lists previous recordings with basic metadata (paths, modified time) and replay previews.
   - “Import recording…” action to copy external CSV/JSONL files into the project data directory and refresh the list.

6. **App Logs** (optional)
   - Shows internal logs/debug info using the existing LogsTab, appended at the end of the workflow.

## Mapping to Existing Code
- **Device & Sensors**
  - Refactors the host and sensor/channel selection logic currently in `RecorderTab` (`src/sensepi/gui/tabs/tab_recorder.py`). The new tab can wrap or extract host combobox handling and `MpuGuiConfig` assembly while keeping RecorderTab as the backend orchestrator for start/stop signals.
  - Calibration actions reuse SignalsTab’s `calibrate_from_buffer()` and `enable_base_correction()` in `tab_signals.py` once data is available.

- **Acquisition & Rates**
  - Reuses `AcquisitionSettingsWidget` and `AcquisitionSettings` from `src/sensepi/gui/widgets/acquisition_settings.py` for sampling mode, device rate, and refresh hints. A new record-only toggle can sit alongside existing adaptive/fixed refresh controls.
  - Streaming/plotting rate preview continues to rely on `SamplingConfig`/`GuiSamplingDisplay` calculations already surfaced through RecorderTab label updates.

- **Live Signals**
  - Builds on `SignalsTab` in `src/sensepi/gui/tabs/tab_signals.py`, preserving its timers, start/stop hooks, and buffer plumbing from RecorderTab. Plot layout adapts to selected channel profile (3 vs 6 axes) using the existing `SignalPlotWidgetPyQtGraph` backend.
  - Remains the source for FFT windows and calibration routines applied client-side.

- **Spectrum (FFT)**
  - Uses `FftTab` in `src/sensepi/gui/tabs/tab_fft.py`, still wired to SignalsTab/RecorderTab buffers and refreshed via timers. It should read the shared acquisition config while allowing a per-FFT refresh override.

- **Recordings**
  - Extends `OfflineTab` in `src/sensepi/gui/tabs/tab_offline.py` to add the import workflow while keeping sync and preview behaviour intact.
  - Continues to rely on `AppPaths` for locating `raw_data`/`processed_data` roots and `Plotter` for rendering selected files.

- **App Logs**
  - Keeps `LogsTab` from `src/sensepi/gui/tabs/tab_logs.py` with minimal change beyond tab placement.

Classes expected to remain mostly stable initially: `RecorderTab` start/stop orchestration, `SignalsTab` buffer consumption/plotting, `FftTab` FFT computation pipeline, and `OfflineTab` listing/sync logic. Heavier refactors will occur around UI layout, shared acquisition config propagation, and new import/calibration controls.

## Open Questions
- Do we need to support more than the current host list (single Pi) or multiple concurrent Pi connections in the Device tab?
- What exact file types and naming conventions should the import action accept and how should conflicts be resolved in `raw_data`?
- Should calibration offsets persist between runs (stored on disk) or reset on each session?
- How should record-only mode signal the backend logger—skip ingest worker only or also adjust remote logger flags?
- How tightly should channel profile choices map to existing logger modes (`default`/`acc`/`gyro`/`both`) when exposing explicit 3- vs 6-channel presets?
