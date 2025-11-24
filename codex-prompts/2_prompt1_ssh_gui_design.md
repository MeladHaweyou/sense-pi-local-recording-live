# Prompt 1 – Design & tech choices for the SSH + GUI tool

You are an expert Python developer and UI architect. Help me design a desktop GUI app that will run on my Windows PC and control sensor logging scripts on a remote Raspberry Pi over SSH.

## Context – existing scripts on the Raspberry Pi

I already have two working Python scripts on the Pi:

1. `adxl203_ads1115_logger.py` — logs acceleration from an ADXL203 via ADS1115.

   **Key CLI arguments:**

   - `--rate <float>` (required, Hz)
   - `--channels {x,y,both}` (which axes to record)
   - `--duration <float>` (seconds, optional; omit = run until Ctrl+C)
   - `--out <path>` (output directory on Pi)
   - `--addr <int/hex>` (I2C address, e.g. `0x48`)
   - `--map "x:P0,y:P1"` (ADS1115 channel mapping)
   - `--calibrate <int>` (N samples for zero-g calibration, 0 = skip)
   - `--lp-cut <float>` (LPF cutoff in Hz, 0 = auto)

   It writes CSV files plus a `.meta.json` into the directory given by `--out`.

2. `mpu6050_multi_logger.py` — logs up to 3 MPU6050 sensors (accelerometers/gyros) on the Pi.

   **Key CLI arguments:**

   - `--rate <float>`              (required Hz, clamped 4..1000)
   - `--sensors "1,2,3"`           (which logical sensors to use)
   - `--map "1:1-0x68,2:1-0x69,3:0-0x68"`  (bus/address override)
   - `--channels {acc,gyro,both,default}`  (columns to record)
   - `--duration <float>`          (seconds, optional)
   - `--samples <int>`             (sample count, optional)
   - `--out <path>`                (output directory on Pi)
   - `--format {csv,jsonl}`        (output format)
   - `--prefix <str>`              (filename prefix)
   - `--dlpf <int 0..6>`           (low-pass filter config)
   - `--temp`                      (also log on-die temperature)
   - `--flush-every <int>`         (writer flush interval in rows)
   - `--flush-seconds <float>`     (writer flush interval in seconds)
   - `--fsync-each-flush`          (enable fsync on every flush)

   It creates one file per sensor (plus `.meta.json`) under `--out`.

## High-level features I want from the GUI

1. Run on **Windows** using **Python** and a GUI toolkit. Prefer **Tkinter** unless you have strong, clearly explained reasons to use something else (like PyQt/PySide).
2. Let me configure and save SSH connection details to the Raspberry Pi:
   - Host/IP
   - Port
   - Username
   - Password **OR** private key path
3. When I click **“Connect”**, the app should open a **persistent SSH session** to the Pi (e.g. using `paramiko`) and show connection status in the GUI.
4. Let me choose which logging setup I want:
   - “Single ADXL203 (ADS1115)” → runs `adxl203_ads1115_logger.py`
   - “Multi MPU6050 (1–3 sensors)” → runs `mpu6050_multi_logger.py`
5. Based on which setup is selected, dynamically show the appropriate parameter fields for that script, with sensible defaults and basic validation:
   - For ADXL: fields for `rate`, `channels`, `duration`, `out`, `addr`, `map`, `calibrate`, `lp-cut`.
   - For MPU6050: fields for `rate`, `sensors`, `channels`, `duration` or `samples`, `out`, `format`, `prefix`, `dlpf`, `temp` (checkbox), and flushing options.
6. Provide buttons:
   - **“Start recording”** → build the correct command line for the selected script and execute it on the Pi over SSH.
   - **“Stop recording”** → send a polite termination to the running script (e.g. SIGINT via the SSH channel, or a `pkill` fallback).
   - **“Download results”** (or similar manual button) → download the newest result files from the Pi via SFTP.
7. While recording:
   - Show live console output (stdout/stderr) from the remote script in a scrollable text area inside the GUI.
   - Keep the GUI responsive (no blocking calls in the main thread; use threads, queues, or async).
8. After the logging script exits:
   - Detect which new files were created in the remote `--out` folder since the run started (CSV/JSONL plus `.meta.json`).
   - Download these files to a **user-selected local folder** on Windows using SFTP.
   - Keep the remote files in place (do **not** delete them).
9. Provide a small section of the GUI for:
   - Choosing a default **remote project directory** on the Pi (e.g. `/home/pi/sense-pi-local-recording-live` and `/home/pi/logs`).
   - Choosing a default **local directory** where downloaded logs are stored.
10. Optionally: save connection + parameter presets to a small local JSON or INI file, and restore them when the GUI restarts.

## Tasks for you in this step

- Propose a **concrete architecture** for this tool.
- Choose specific libraries (e.g. Tkinter + Paramiko + standard Python).
- Outline the main Python modules/classes, for example:
  - `SSHClientManager` — wraps Paramiko and manages a persistent SSH + SFTP connection.
  - `RemoteLoggerController` — builds commands, tracks runs, and handles snapshots of remote directories.
  - `MainWindow` (Tkinter) — all GUI widgets, wiring, and high-level actions.
- Explain how to keep the SSH exec, stdout/stderr reading, and SFTP transfers **off the GUI thread**. You can assume I’m fine with background threads and `queue.Queue` + `root.after()` for UI updates.
- Explain how you will track which files are “new” for a run (e.g. snapshot remote directory before and after, and diff based on filenames + modification times).
- List any **security caveats** (storing passwords locally, handling host keys correctly, etc.).

## Answer format

Please answer with:

1. A clear architecture description (1–2 paragraphs plus a small diagram or bullet list).
2. A short list of requirements:
   - Python version.
   - All pip dependencies.
3. A suggested file structure, for example:
   - `main.py`
   - `ssh_client.py`
   - `remote_logger.py`
   - `config_store.py`
4. Any design decisions that will matter when I implement the code in the next step (e.g. how you abstract SSH vs SFTP, how logging is handled, how you model a “run”).

5. **Important:** Include **two short, self-contained code snippets** to illustrate the most important integration pieces:
   - A minimal `SSHClientManager` class that uses Paramiko, runs a long-lived command in the background, and pushes its stdout/stderr lines into a `queue.Queue`.
   - A minimal Tkinter window that:
     - Sets up a `Text` widget.
     - Periodically polls the queue using `root.after(...)`.
     - Appends new lines to the `Text` without blocking the GUI.

The snippets don’t have to be production-ready, but they should be syntactically correct and runnable with minor adjustments.
