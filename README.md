# SensePi Local Recording & Live View

This repository hosts a desktop application for managing Raspberry Pi–based sensor loggers alongside the scripts that run directly on the Pi. The PC/WSL side provides a PySide6 GUI for recording, live viewing, and analyzing data, while the Pi side supplies lightweight logger scripts for specific sensors. The desktop app focuses on inspecting logs from the MPU6050 logger.

New to the project? See [docs/LEARNING_PATH.md](docs/LEARNING_PATH.md) for a milestone-based walkthrough aimed at students.

## Architecture & Roles

- **Desktop GUI (PC/WSL)**
  - Starts/stops Pi loggers over SSH and synchronizes files over SFTP
  - Displays live time-domain and FFT plots
  - Pushes sensor defaults from `src/sensepi/config/sensors.yaml` into each Pi’s `pi_config.yaml`
  - Downloads recent CSV/JSONL logs for offline browsing
- **Raspberry Pi logger**
  - Runs the `raspberrypi_scripts/` CSV/JSONL logging scripts on the device
  - Streams JSON lines over stdout to the desktop (protocol: `docs/json_protocol.md`)

```mermaid
flowchart LR
  PC[Desktop GUI] <-->|SSH / SFTP| Pi[Raspberry Pi logger]
  Pi -->|JSON lines over stdout| PC
```

The JSON streaming format and field definitions are documented in `docs/json_protocol.md`.

Configuration files live with the GUI under `src/sensepi/config/hosts.yaml` and `src/sensepi/config/sensors.yaml`, while each Pi keeps its active settings in `raspberrypi_scripts/pi_config.yaml`; the GUI’s Sync action pushes the desktop sensor defaults to that Pi file so every logger shares the same baseline.

## Decimation & Plotting Configuration

Low-latency recording, streaming, and visualization all pull their settings from the `SensePiConfig` dataclass (`src/sensepi/config/runtime.py`).  Load it from YAML via `sensepi.config.load_config`, tweak the fields you care about, then pass it to `sensepi.core.pipeline_wiring.build_pipeline` (for the recorder/streamer/plotter fan-out) and `LivePlot.from_config` (for Matplotlib demos such as `run_live_plot.py`).  Adjusting the config object once at startup keeps rasterizer, streamer, and recorder behaviour in sync without editing multiple modules.

Recommended starting points for human-friendly refresh rates:

- `plot_fs ≈ 50 Hz` keeps the Matplotlib view smooth on Pi Zero 2 while keeping the decimator ratio large enough for 500–1000 Hz sensors.
- `smoothing_alpha ≈ 0.2` corresponds to ~20–50 ms of IIR smoothing—large enough to calm jitter but small enough to keep spikes visible.
- `plot_window_seconds ≈ 5–10 s` balances temporal context and responsivity for the scrolling plot.
- `spike_threshold ≈ 3×` the noise standard deviation works well for highlighting interesting transients without littering the plot with markers.

Create a YAML file with the fields you need (unknown keys are ignored) and point the demo at it:

```yaml
pipeline:
  sensor_fs: 1000.0
  stream_fs: 40.0
  plot_fs: 48.0
  plot_window_seconds: 8.0
  smoothing_alpha: 0.2
  spike_threshold: 0.6
```

```bash
python run_live_plot.py --config configs/pipeline.yaml
```

`run_live_plot.py` also exposes `--plot-window`, `--spike-threshold`, and `--plot-fs` flags for quick experiments without editing the YAML file.

## Project layout

```
sense-pi-local-recording-live/
├── main.py              # Thin launcher that delegates to sensepi.gui.application
├── src/sensepi/tools/   # Local plotting helpers and CLI plotter
├── pyproject.toml       # packaging metadata
├── requirements.txt     # desktop dependencies
├── requirements-pi.txt  # Pi dependencies
├── src/sensepi/         # desktop application package
├── raspberrypi_scripts/ # files copied to the Raspberry Pi
├── data/                # raw and processed data (ignored)
├── logs/                # application logs (ignored)
└── archive/             # legacy and experimental files
```

## Run the GUI

From the project root you can launch the Qt application via the canonical
entrypoint:

```bash
python -m sensepi.gui.application
# or, after installing the package:
sensepi-gui
```

`main.py` simply delegates to the same launcher so either form works. The
tabbed interface exposes Recorder, Signals, FFT, Offline, and Settings tabs.
Configuration defaults live under `src/sensepi/config/` and can be customised
per host and sensor.

### SSH authentication

The desktop app connects to each Raspberry Pi using a username and password.
Populate `src/sensepi/config/hosts.yaml` (or the Settings tab) with the host,
port, username, and password for each Pi. SSH key authentication and agent
forwarding are not supported in this version.

## Download logs from the Pi

A common SensePi workflow is:

1. **Configure your Raspberry Pi host**  
   Open the **Settings** tab and make sure your Pi appears under *Raspberry Pi hosts* with a working `host`, `user`, `base_path`, and `data_dir`. Use **Sync config to Pi** to push the current sampling defaults whenever you change sensors or rates.

2. **Start a recording from the Signals tab**  
   Go to the **Signals** tab, pick your Pi host, choose a sample rate, and tick the **Recording** checkbox. Optionally provide a *Session name* to label the run, then click **Start**. Hint text beneath the buttons confirms exactly which directory on the Pi the CSV/JSONL files will land in.

3. **Stop the recording**  
   Press **Stop** when you have captured enough data. The status bar repeats the path of the logs on the Pi and reminds you to visit the **Offline logs** tab to sync them.

4. **Download logs to your desktop**  
   Switch to the **Offline logs** tab. Click **Sync logs from Pi** to pull any new `.csv` or `.jsonl` files from that host’s `data_dir` into your local `data/raw` folder. If you want a shortcut that also opens the newest file, use **Sync & open latest** instead.

5. **Inspect the recording offline**  
Use the *Offline log files* list to double-click a file, or let **Sync & open latest** select it automatically. The embedded Matplotlib viewer renders the data with the same conventions as the live **Signals** tab so you can inspect the captured session without staying connected to the Pi.

## Log Conventions (where your data lives)

SensePi keeps all of your raw logs as plain files, both on the Pi and on your computer. Knowing where they live – and what the filenames mean – makes it much easier to grab the right run later.

### On the Raspberry Pi

By default the Pi creates the following folders:

- `~/logs` – root directory for all recordings on the device
- `~/logs/mpu` – files produced by the MPU6050 IMU logger

When you start a recording you can supply an optional **session name** (for example, `Trial1`). If you do, the logger writes that run into a dedicated folder:

- `~/logs/mpu/Trial1/` – all files for that session

Leaving the session field blank keeps the files directly under `~/logs/mpu`. Either way you will see one data file per physical sensor (e.g., `S1`, `S2`) plus a small metadata file.

### On the PC (after syncing)

Clicking **Sync logs from Pi** in the Offline tab pulls every new `.csv` or `.jsonl` file from the Pi into the desktop project’s data folder:

- `data/raw` – root directory for downloaded logs

If the run had a session name, that folder is recreated locally:

- `data/raw/trial1/` – the session folder after being slugified (lowercase, spaces to hyphens)

If no session name was supplied, the GUI groups logs by host and sensor type instead so devices never clobber one another:

- `data/raw/mypi/mpu/` – files recorded on a Pi host named `mypi`

Everything remains normal files on disk, so you can back them up, version them, or open them in other tools.

### File name pattern

Data files use the following pattern:

```
[<session>_]<sensorPrefix>_S<sensorID>_<timestamp>.<ext>
```

Examples:

- `Trial1_mpu_S1_2025-11-30_04-53-33.csv`
- `mpu_S2_2025-11-30_04-53-33.jsonl`

Where:

- `<session>` is your session name, turned into a filesystem-safe slug (lowercase, hyphenated). If you left the field blank, this part disappears.
- `<sensorPrefix>` is a short code for the logger. For the IMU it is `mpu`.
- `S<sensorID>` is the sensor index on the logger (S1, S2, ...).
- `<timestamp>` is the recording start time in UTC formatted as `YYYY-MM-DD_HH-MM-SS`.
- `<ext>` is the file format: `.csv` or `.jsonl`.

Each data file is paired with a metadata sidecar whose name ends in `.meta.json`, for example:

- `Trial1_mpu_S1_2025-11-30_04-53-33.csv.meta.json`

The metadata records the sample rate, which axes were enabled, and other run settings. The Offline tab uses it to plot data correctly, so keep it beside the data file when copying or renaming logs.

### Sample rate and decimation

The MPU6050 can be sampled very quickly (hundreds of Hertz), but SensePi purposely **decimates** those samples for recording and streaming so files stay small and the live plots stay responsive. You will see three related rates in configs and metadata:

- **Device rate** – how fast the sensor is polled on the Pi itself (for example, 200 Hz).
- **Record rate** – how often samples are written to the CSV/JSONL file (for example, keeping every 4th device sample → 50 Hz in the log).
- **Stream rate** – how often samples are forwarded live over SSH to the GUI (for example, every 8th device sample → 25 Hz on the live plot).

Because of decimation the stored CSV may contain fewer samples per second than the raw device rate, which is an intentional tradeoff for smaller files and smoother UI updates. Inspect `sensors.yaml`, `pi_config.yaml`, or the `.meta.json` file for a given run to see the exact rates that were used.

## Configuration paths

By default the GUI stores output under `data/` and `logs/` inside the project
root. Set `SENSEPI_DATA_ROOT` or `SENSEPI_LOG_DIR` (they both understand `~`)
before launching the app to relocate those folders for packaged installs or
custom deployments. The paths shown in `src/sensepi/config/hosts.yaml` and
`raspberrypi_scripts/pi_config.yaml` are only examples—update them to match
each Pi’s filesystem layout.

## Sync config to Pi

The Settings tab offers a **Sync config to Pi** action. It builds a
`pi_config.yaml` from the desktop sensor defaults, validates that the remote
scripts/data directories exist over SSH, and uploads the YAML to the path
configured for the selected host. The desktop configuration is the source of
truth; use this button to push updates to your Pis.

## Plotting from CSV logs

The Matplotlib-based CLI plotter lives at `src/sensepi/tools/plotter.py`. Run
it directly or import its helpers for embedding in Qt tabs:

```bash
python -m sensepi.tools.plotter --file data/raw/your_log.csv
```

An offline analysis tab in the GUI reuses the same plotting logic to view
recent CSV/JSONL logs without starting a live stream.

## Raspberry Pi scripts

The `raspberrypi_scripts/` folder contains the low-level loggers that run on the Pi. Copy the folder to your device (e.g., `/home/pi/raspberrypi_scripts`) and install dependencies:

```bash
scp -r raspberrypi_scripts pi@<host>:/home/pi/
ssh pi@<host> "bash /home/pi/raspberrypi_scripts/install_pi_deps.sh"
```

Use `run_all_sensors.sh` as a simple helper to start the provided logger scripts. Adjust `pi_config.yaml` to set sample rates, output paths, and channel selections.

The streaming JSON wire protocol used by the loggers is documented in
`docs/json_protocol.md`.

## Legacy content

The `archive/` directory is reserved for older or experimental scripts that
you don’t want to delete yet. You can move legacy entrypoints or prototypes
there to keep the main code paths focused on the current PySide6-based
workflow.
