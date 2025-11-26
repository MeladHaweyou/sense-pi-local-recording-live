# SensePi Local Recording & Live View

This repository hosts a desktop application for managing Raspberry Pi–based sensor loggers alongside the scripts that run directly on the Pi. The PC/WSL side provides a PySide6 GUI for recording, live viewing, and analyzing data, while the Pi side supplies lightweight logger scripts for specific sensors. The desktop app focuses on inspecting logs from the MPU6050 logger.

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
