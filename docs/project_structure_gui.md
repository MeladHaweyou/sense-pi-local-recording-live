# SensePi GUI – Project Structure (GUI-centric)

## Entry points
- `main.py`: convenience script to launch the Qt GUI and forward CLI args.
- `src/sensepi/gui/application.py`: sets up CLI flags, configures matplotlib for interactive use, creates `QApplication`, builds `MainWindow`, and runs the Qt event loop.
- `src/sensepi/gui/main_window.py`: constructs the tabbed main window that stitches together recorder control, live views, FFT, offline playback, and logs.

## Tabs overview
- **Device (`RecorderTab`, `src/sensepi/gui/tabs/tab_recorder.py`)**: connect to Raspberry Pi hosts, configure MPU6050 sensors/channels, and start/stop live streams or recordings. Emits parsed samples into the shared streaming buffer for other tabs.
- **Sensors & Rates (`SettingsTab`, `src/sensepi/gui/tabs/tab_settings.py`)**: edit SSH hosts plus sampling/default sensor settings via `AcquisitionSettingsWidget`; notifies `RecorderTab` when YAML config changes so device selection and rates stay aligned.
- **Live Signals (`SignalsTab`, `src/sensepi/gui/tabs/tab_signals.py`)**: live time-series plotting with `SignalPlotWidget` (PyQtGraph or Matplotlib backend). Requests start/stop from `RecorderTab`, tunes plotting refresh rates independently of sampling, and forwards FFT refresh hints.
- **Spectrum (`FftTab`, `src/sensepi/gui/tabs/tab_fft.py`)**: live spectrum/FFT derived from the same streaming buffer used by Signals. Adapts to sampling/refresh hints from Signals to stay in sync with the live stream.
- **Recordings (`OfflineTab`, `src/sensepi/gui/tabs/tab_offline.py`)**: browse, sync from the Pi, and open offline recordings using shared plotter helpers without affecting live buffers.
- **App Logs (`LogsTab`, `src/sensepi/gui/tabs/tab_logs.py`)**: inspect application log files with an optional follow/tail mode for debugging.

### Where to plug in common GUI concerns
- **Sensor selection**: `RecorderTab` (runtime toggle) and `SettingsTab` defaults feed `AcquisitionSettingsWidget` used by Signals when launching streams.
- **Sampling vs. streaming/plotting rate**: `RecorderTab` sets device and stream rates; `SignalsTab` adjusts GUI refresh cadence independently and publishes FFT refresh intervals to `FftTab`.
- **Calibration or processing hooks**: add per-sensor adjustments in the live path by subscribing to `RecorderTab.sample_received` before buffers are plotted, or add offline calibration when loading files in `OfflineTab`.
- **Recordings browser**: `OfflineTab` handles listing/downloading sessions and opening them with `Plotter`.

## Data flow (very high level)
1. `RecorderTab` configures and starts the Pi logger/stream (optionally recording to disk on the Pi).
2. Parsed samples are appended to the shared `StreamingDataBuffer` (with rate updates emitted alongside).
3. `SignalsTab` reads from that buffer to render live time-series plots and adjusts GUI refresh timers.
4. `FftTab` pulls buffered samples for FFT/spectrum displays, following refresh hints from Signals.
5. `OfflineTab` reads historical logs from disk (local sync) for playback, separate from the live buffer.

## Core modules for GUI refactor
- `src/sensepi/gui/**` (tabs, widgets, application, main window, performance helpers).
- `src/sensepi/config` for hosts/sensor defaults (`HostInventory`, `SensorDefaults`, `AppConfig`).
- Streaming/buffer utilities in `src/sensepi/core` and `src/sensepi/data` (`StreamingDataBuffer`, `TimeSeriesBuffer`, etc.).
- Sensor parsing in `src/sensepi/sensors` (e.g., `mpu6050`) that feeds live and offline views.
- Remote control and ingest plumbing in `src/sensepi/remote` (SSH clients, `PiRecorder`, ingest worker).
- Plotting/support utilities referenced by GUI tabs (`src/sensepi/tools`, `src/sensepi/analysis`).

## Optional / legacy scripts
- Top-level CLI/debug utilities: `debug_*.py`, `live_plot.py`, `run_live_plot.py`, `profile_benchmark.py`, `decimation.py`, `envelope_plot.py`, `ssh_client.py`, `pi_recorder.py`.
- AI helper/prompts and automation: `combined.py`, `run_codex_prompts.py`, `codex-prompts/`, `combine.bat`, `logs.txt`.
- Raspberry Pi helper scripts under `raspberrypi_scripts/` not directly invoked by the desktop GUI.

## Removed AI helper artifacts

- Deleted `combine.bat`, `combined.py`, `logs.txt` from the repo root.
  These were one-off helper artifacts for generating a combined code view
  and are not part of the maintained project source.
