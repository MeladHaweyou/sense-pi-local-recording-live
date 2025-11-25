# SensePi Local Recording & Live View

This repository hosts a desktop application for managing Raspberry Pi–based sensor loggers alongside the scripts that run directly on the Pi. The PC/WSL side provides a PySide6 GUI for recording, live viewing, and analyzing data, while the Pi side supplies lightweight logger scripts for specific sensors.

## Project layout

```
sense-pi-local-recording-live/
├── main.py              # PySide6 GUI entry point
├── plotter.py           # CLI plotter for CSV logs (used by LocalPlotRunner)
├── local_plot_runner.py # Small helper to spawn/stop plotter.py
├── pyproject.toml       # packaging metadata
├── requirements.txt     # desktop dependencies
├── requirements-pi.txt  # Pi dependencies
├── src/sensepi/         # desktop application package
├── raspberrypi_scripts/ # files copied to the Raspberry Pi
├── data/                # raw and processed data (ignored)
├── logs/                # application logs (ignored)
└── archive/             # legacy and experimental files
```

## Desktop application

Run the main PySide6 GUI from the repository root:

```bash
python main.py
```

This window lets you connect to a Raspberry Pi over SSH, start/stop the
MPU6050 and ADXL203 loggers, and (optionally) launch a local plotting
process via LocalPlotRunner, which in turn starts plotter.py.

There is also an example, tabbed GUI under src/sensepi/gui/ that you can
launch directly:

```bash
python -m sensepi.gui.application
```

It currently provides basic “Recorder”, “Signals”, “FFT”, and “Settings”
tabs and is intended as a starting point for a more integrated UI.

Configuration defaults live under src/sensepi/config/ and can be
customised per host and sensor.

## Plotting from CSV logs

`plotter.py` is a small Matplotlib-based CLI tool for visualising CSV logs
produced by the Raspberry Pi loggers. You can run it directly:

```bash
python plotter.py --file data/raw/your_log.csv
```

or let the GUI start it automatically via LocalPlotRunner when you press
“Start Recording + Plot”. In “follow” mode the plotter periodically reloads
the CSV file to approximate a live view.

## Raspberry Pi scripts

The `raspberrypi_scripts/` folder contains the low-level loggers that run on the Pi. Copy the folder to your device (e.g., `/home/pi/raspberrypi_scripts`) and install dependencies:

```bash
scp -r raspberrypi_scripts pi@<host>:/home/pi/
ssh pi@<host> "bash /home/pi/raspberrypi_scripts/install_pi_deps.sh"
```

Use `run_all_sensors.sh` as a simple helper to start the provided logger scripts. Adjust `pi_config.yaml` to set sample rates, output paths, and channel selections.

## Legacy content

The `archive/` directory is reserved for older or experimental scripts that
you don’t want to delete yet. You can move legacy entrypoints or prototypes
there to keep the main code paths focused on the current PySide6-based
workflow.
