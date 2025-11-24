# Prompt 1 – Design & tech choices for the SSH + GUI tool

```text
You are an expert Python developer and desktop UI architect. Help me design a Windows desktop GUI app that controls sensor logging scripts on a remote Raspberry Pi over SSH.

====== CONTEXT ======
On the Raspberry Pi I already have two working Python scripts:

1) adxl203_ads1115_logger.py
   - Purpose: log acceleration from an ADXL203 via ADS1115.
   - Key CLI arguments (as implemented in the script):
       --rate <float>         # required, Hz
       --channels {x,y,both}  # which axes to record
       --duration <float>     # seconds, optional (omit = run until Ctrl+C)
       --out <path>           # output directory on Pi
       --addr <int/hex>       # I2C address, e.g. 0x48
       --map "x:P0,y:P1"      # ADS1115 channel mapping
       --calibrate <int>      # N samples for zero-g calibration (0=skip)
       --lp-cut <float>       # LPF cutoff in Hz (0=auto)
   - It writes CSV files plus a .meta.json file into the directory given by --out.

2) mpu6050_multi_logger.py
   - Purpose: log up to 3 MPU6050 sensors (accelerometers/gyros) on the Pi.
   - Key CLI arguments (as implemented in the script):
       --list                      # optional, lists detected devices then exits
       --rate <float>              # required Hz, clamped ~4..1000
       --sensors "1,2,3"           # which logical sensors to use
       --map "1:1-0x68,2:1-0x69,3:0-0x68"  # bus/address override
       --channels {acc,gyro,both,default}  # columns to record
       --duration <float>          # seconds (optional)
       --samples <int>             # sample count (optional)
       --out <path>                # output directory on Pi
       --format {csv,jsonl}        # output format
       --prefix <str>              # filename prefix
       --dlpf <int 0..6>           # low-pass filter config
       --temp                      # also log on-die temperature
       --flush-every <int>         # writer flush interval (rows)
       --flush-seconds <float>     # writer flush interval (seconds)
       --fsync-each-flush          # enable fsync on every flush
   - It creates one file per sensor (plus .meta.json) under --out.

On the PC side:
- OS: Windows 10/11
- I want to use Python + a GUI toolkit (prefer Tkinter unless you have strong, clearly explained reasons to choose another).
- SSH library: paramiko (or a very similar pure-Python SSH/SFTP library).

====== WHAT I WANT THE GUI TO DO ======
High-level features the app must support:

1. Run as a Python desktop app on Windows using Tkinter by default.

2. Manage SSH connection details to the Raspberry Pi:
   - Host/IP
   - Port
   - Username
   - Password OR private key path
   - Ability to save/load these connection profiles locally.

3. When I click “Connect”, the app should:
   - Open a persistent SSH session to the Pi.
   - Optionally open a persistent SFTP session reusing the SSH connection.
   - Show connection status in the GUI (e.g. Connected / Disconnected / Error).

4. Let me choose which logging setup I want:
   - “Single ADXL203 (ADS1115)” → maps to adxl203_ads1115_logger.py
   - “Multi MPU6050 (1–3 sensors)” → maps to mpu6050_multi_logger.py

5. Based on the selected setup, dynamically show the appropriate parameter fields with sensible defaults and basic validation:
   a) ADXL script:
      - rate, channels, duration, out, addr, map, calibrate, lp-cut
   b) MPU6050 script:
      - rate, sensors, channels, duration or samples, out, format,
        prefix, dlpf, temp (checkbox), flush-every, flush-seconds,
        fsync-each-flush (checkbox)

6. Provide control buttons:
   - “Start recording” → Build the correct command line for the selected script and execute it on the Pi over SSH.
   - “Stop recording” → Send a polite termination to the running script (SIGINT via SSH channel if possible, or pkill fallback).
   - “Download results” (or automatic download when a run finishes).

7. While recording:
   - Show live console output (stdout & stderr) from the remote script in a scrollable text area inside the GUI.
   - Keep the GUI responsive at all times (no blocking calls in the Tkinter main thread).
   - Use background threads, queues, or an async pattern as appropriate.

8. After the logging script exits:
   - Detect which new files were created in the remote --out folder since the run started.
   - Download those new files to a user-selected local folder on the Windows PC using SFTP.
   - Keep remote files in place.

9. Provide options for default directories:
   - A default remote project directory on the Pi (e.g. /home/pi/sense-pi-local-recording-live and /home/pi/logs).
   - A default local directory where downloaded logs are stored.

10. Optional but desired:
   - Save connection + parameter presets to a small local JSON or INI file.
   - Restore them when the GUI restarts.

====== DESIGN QUESTIONS TO ANSWER ======
Propose a concrete architecture for this tool:

1. TECHNOLOGY STACK
   - Confirm Python version(s) you target.
   - Choose the GUI toolkit (prefer Tkinter) and justify if you recommend anything else.
   - Choose the SSH/SFTP library (prefer paramiko).
   - Mention any other standard-library modules you’ll rely on (threading, queue, json, pathlib, etc.).

2. ARCHITECTURE & MODULES
   - Outline the main Python modules and classes you would create in a multi-file project, e.g.:
     * ssh_client_manager.py → SSHClientManager (handles connect, disconnect, exec, SFTP).
     * remote_logger_controller.py → RemoteLoggerController (builds commands, tracks runs, knows which script is active).
     * gui_main_window.py → MainWindow (Tkinter UI, frames, forms, buttons).
     * config_store.py → small utility for saving/loading JSON or INI config.
   - Explain each class’s responsibilities and how they collaborate.

3. CONCURRENCY / RESPONSIVENESS
   - Explain how you will keep SSH exec and SFTP transfers off the GUI thread.
   - Describe your threading model (e.g. worker threads + queue feeding a Tkinter .after loop).
   - Explain how you will stream remote stdout/stderr into a thread-safe queue and then into the Text widget without freezing the UI.

4. RUN MANAGEMENT & NEW FILE DETECTION
   - Explain how you will track which process is currently running (per-setup) and how “Stop recording” works.
   - Propose a strategy to detect “new” files:
     * For example, snapshot the contents of the remote --out folder immediately before launching a run, and again after it finishes, then take the set difference.
     * Or: track modification times (mtime) and consider files with mtime > “run start time” as new.
   - Discuss pros/cons of each strategy and recommend one.

5. FILE TRANSFER & PATHS
   - Explain how you’ll structure:
     * Remote script paths (editable fields in the GUI, with reasonable defaults).
     * Remote output directories (--out).
     * Local download path (user-chosen via a file dialog).
   - Explain how you’ll map each run’s remote files to local filenames and subfolders.

6. CONFIG / PRESETS
   - Outline a simple config format (e.g. JSON file next to main.py) to store:
     * SSH host/port/username
     * Last-used password or key path (with a big TODO warning about security)
     * Default remote script paths
     * Default remote output folders
     * Default local download folder
     * Last-used parameters for each script preset (optional).
   - Explain when the config is loaded and when it’s saved.

7. SECURITY CAVEATS
   - Explain the security implications of:
     * Using paramiko.AutoAddPolicy for host keys.
     * Storing SSH passwords or private key paths in plain JSON.
     * Allowing arbitrary command execution on the Pi (since we are building shell commands).
   - Suggest practical mitigations (even if we don’t fully implement them in v1).

8. DELIVERABLE FORMAT
   Please respond with:

   - A concise architecture description (2–4 paragraphs).
   - A short list of concrete technical requirements:
     * Target Python version(s)
     * pip install dependencies
   - A proposed file structure for a future multi-file version (e.g., main.py, ssh_client_manager.py, gui_main_window.py, config_store.py, remote_logger_controller.py).
   - Any key design decisions that will matter when we implement the first working version (e.g. choice of threading vs asyncio, how you structure Tkinter frames, how you encapsulate SSH).

Keep the explanation practical and implementation-oriented, so I can hand your design straight into a second prompt that asks for a full implementation.
```