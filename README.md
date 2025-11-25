# SensePi Local Recording & Live View

This repository hosts a desktop application for managing Raspberry Pi–based sensor loggers alongside the scripts that run directly on the Pi. The PC/WSL side provides a PySide6 GUI for recording, live viewing, and analyzing data, while the Pi side supplies lightweight logger scripts for specific sensors.

## Project layout

```
sense-pi-local-recording-live/
├── main.py                 # PySide6 entry point
├── pyproject.toml          # packaging metadata
├── requirements.txt        # desktop dependencies
├── requirements-pi.txt     # Pi dependencies
├── src/sensepi/            # desktop application package
├── raspberrypi_scripts/    # files copied to the Raspberry Pi
├── data/                   # raw and processed data (ignored)
├── logs/                   # application logs (ignored)
└── archive/                # legacy and experimental files
```

## Desktop application

Run the PySide6 GUI from the repository root:

```bash
python -m sensepi.gui.application
```

or simply:

```bash
python main.py
```

The GUI exposes tabs for recording control, live signal viewing, FFT/analysis, and settings management. Configuration defaults live under `src/sensepi/config/` and can be customized per host and sensor.

## Raspberry Pi scripts

The `raspberrypi_scripts/` folder contains the low-level loggers that run on the Pi. Copy the folder to your device (e.g., `/home/pi/raspberrypi_scripts`) and install dependencies:

```bash
scp -r raspberrypi_scripts pi@<host>:/home/pi/
ssh pi@<host> "bash /home/pi/raspberrypi_scripts/install_pi_deps.sh"
```

Use `run_all_sensors.sh` as a simple helper to start the provided logger scripts. Adjust `pi_config.yaml` to set sample rates, output paths, and channel selections.

## Legacy content

Older Tkinter, MQTT, and experimental code has been relocated to `archive/` to keep the main application focused on the new PySide6-based workflow.
