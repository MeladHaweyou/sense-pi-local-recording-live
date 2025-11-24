# Prompt 2 – Generate the first working GUI (Tkinter + Paramiko)

```text
You are an expert Python developer and desktop UI architect. Using the design you proposed previously (or a simple, self-contained design if none exists), implement the first full working version of a Tkinter + Paramiko GUI in a single file called main.py.

====== RUNTIME ENVIRONMENT ======
- Local OS: Windows 10/11
- Remote: Raspberry Pi running Linux with Python 3
- GUI: Tkinter
- SSH/SFTP: paramiko
- Allowed external dependencies: paramiko only; everything else must be from the Python standard library.

====== REMOTE SCRIPTS & THEIR INTERFACES ======
On the Raspberry Pi, I have two scripts:

1) adxl203_ads1115_logger.py
   - Purpose: log acceleration from an ADXL203 via ADS1115.
   - CLI arguments:
       --rate <float>         # required, Hz
       --channels {x,y,both}
       --duration <float>     # seconds, optional
       --out <path>           # output directory on Pi
       --addr <int/hex>       # e.g. 0x48
       --map "x:P0,y:P1"
       --calibrate <int>      # 0 means skip
       --lp-cut <float>       # LPF cutoff in Hz (0=auto)
   - Outputs a CSV file plus .meta.json under --out.

2) mpu6050_multi_logger.py
   - Purpose: log data from up to 3 MPU6050 sensors.
   - CLI arguments:
       --rate <float>              # required Hz, clamped 4..1000
       --sensors "1,2,3"
       --map "1:1-0x68,2:1-0x69,3:0-0x68"
       --channels {acc,gyro,both,default}
       --duration <float>          # seconds (optional)
       --samples <int>             # optional
       --out <path>                # output directory on Pi
       --format {csv,jsonl}
       --prefix <str>
       --dlpf <int 0..6>
       --temp                      # flag
       --flush-every <int>
       --flush-seconds <float>
       --fsync-each-flush          # flag
   - Outputs one log file per sensor, plus .meta.json, under --out.

====== FUNCTIONAL REQUIREMENTS ======
Implement everything in a single file main.py, but structure the code logically with classes.

1. CONNECTION SECTION (top of the GUI)
   - Text fields:
     * host/IP
     * port (default 22)
     * username
     * password
     * private key path (optional)
   - Buttons:
     * “Connect”
       - Creates a paramiko.SSHClient
       - Uses AutoAddPolicy for host keys (for now)
       - Opens both SSH and SFTP connections
       - Shows connection status in a label (“Connected” / “Disconnected” / “Error: …”)
     * “Disconnect”
       - Cleanly closes SSH and SFTP.
   - All network work (connect, disconnect) must be done in a background thread so the UI never freezes.
   - Errors should be shown via message boxes and/or an on-screen log.

2. SENSOR SETUP SELECTION
   - Provide a radio button group or dropdown control to choose:
     * “Single ADXL203 (ADS1115)”
     * “Multi MPU6050 (1–3 sensors)”
   - Below that, show a frame whose contents change based on the selected sensor type.

   a) For ADXL203 / ADS1115 (adxl203_ads1115_logger.py), fields with defaults:
      - Script path (editable, default something like /home/pi/adxl203_ads1115_logger.py)
      - rate (float, required; default 100.0)
      - channels (dropdown: x, y, both; default both)
      - duration (float, seconds, optional; empty = indefinite)
      - out (string; remote output folder, default e.g. /home/pi/logs-adxl)
      - addr (string; default 0x48)
      - map (string; default "x:P0,y:P1")
      - calibrate (int; default 300)
      - lp-cut (float; default 15.0)

   b) For Multi-MPU6050 (mpu6050_multi_logger.py), fields with defaults:
      - Script path (editable, default something like /home/pi/mpu6050_multi_logger.py)
      - rate (float, required; default 100.0)
      - sensors (string, e.g. "1,2,3"; default "1,2,3")
      - channels (dropdown: acc, gyro, both, default; default “default”)
      - duration (float seconds, optional)
      - samples (int, optional)
      - out (string; remote output folder, e.g. /home/pi/logs-mpu)
      - format (dropdown: csv, jsonl; default csv)
      - prefix (string; default "mpu")
      - dlpf (int 0..6; default 3)
      - temp (checkbox; default unchecked)
      - flush-every (int; default 2000)
      - flush-seconds (float; default 2.0)
      - fsync-each-flush (checkbox; default unchecked)

3. COMMAND BUILDING
   - When I click “Start recording”, build the exact python3 command string for the selected script, e.g.:
     - ADXL:
       python3 /path/on/pi/adxl203_ads1115_logger.py --rate 100 --channels both --duration 10 --out /home/pi/logs-adxl --addr 0x48 --map "x:P0,y:P1" --calibrate 300 --lp-cut 15
     - MPU6050:
       python3 /path/on/pi/mpu6050_multi_logger.py --rate 100 --sensors 1,2 --channels default --duration 10 --out /home/pi/logs-mpu --format csv --prefix mpu --dlpf 3 --flush-every 2000 --flush-seconds 2.0
   - The script paths on the Pi must be editable in the GUI (as text fields with default values).
   - Only include arguments that the user has actually set; if a field is blank for an optional parameter (e.g. duration), omit that CLI flag entirely.

4. RUNNING THE REMOTE COMMAND
   - Execute the command over SSH using exec_command or a lower-level Channel.
   - Never block the Tkinter mainloop:
     * Use a background worker thread to call SSHClient.exec_command and read stdout/stderr.
     * Have that thread push lines into a queue.Queue.
   - In the Tkinter thread, use root.after(...) to periodically poll the queue and append lines to a scrollable Text widget labeled “Remote log output”.

5. STOPPING THE RUN
   - Provide a “Stop recording” button that:
     * Attempts to terminate the remote process gracefully (e.g. channel.close()).
     * As a fallback, runs a separate command like:
       pkill -f adxl203_ads1115_logger.py
       or
       pkill -f mpu6050_multi_logger.py
       depending on which script type is active.
   - After the process ends, the background thread must exit cleanly and the UI must update status accordingly.

6. DOWNLOADING RESULTS
   - Provide two directory inputs:
     * Remote output base folder (may be different for each sensor type).
     * Local destination folder on Windows (default something like C:\Users\<me>\Downloads\sense-pi-logs).
   - Add a button “Download newest files” that:
     * Runs in a background thread.
     * Uses SFTP to list files in the remote output folder.
     * Downloads “newest” files according to a simple heuristic such as:
       - “files modified in the last N minutes”, OR
       - “files sorted by mtime, take the latest K files”.
     * Save them to the selected local folder without deleting anything on the Pi.
   - In v1, it’s OK if “newest files” is approximate; DOCUMENT IN COMMENTS which heuristic you use.

7. RESPONSIVENESS & ERROR HANDLING
   - All network operations (connect/disconnect, exec, SFTP listing and download) must run in background threads.
   - GUI must never freeze.
   - Use try/except blocks around network operations and:
     * Update the status label and/or log Text widget on errors.
     * Also show a Tkinter messagebox.showerror for serious errors (e.g. auth failure).

8. SAVE / LOAD CONFIG (NICE-TO-HAVE, BUT PLEASE IMPLEMENT IF POSSIBLE)
   - Add two small buttons: “Save config” and “Load config”.
   - Store/restore the following to/from a JSON file in the same directory as main.py:
     * SSH host/port/username
     * Remote script paths
     * Default remote output folders
     * Default local download folder
   - It’s acceptable for now if the password is also stored in plain text, but:
     * Add a clear comment in the code (TODO) warning that this is insecure and should be improved later.

====== IMPLEMENTATION DETAILS ======
- Use classes to keep the code organized even though it’s a single file. For example:
  * SSHClientManager: owns paramiko.SSHClient, connect/disconnect logic, exec_command with streaming, and SFTP client.
  * RemoteRunWorker: a small helper or method to run a command in a background thread and push output to a queue.
  * App (or MainWindow): encapsulates the Tkinter root, frames, widgets, event handlers, and the queue polling loop.

- Use Python’s threading and queue modules, not asyncio.

- Convenient defaults:
  * Use sensible initial values for text fields so the app is usable immediately after filling in SSH credentials.
  * Consider using os.path.expanduser to handle local paths.

- Coding style:
  * Make the script runnable with: python main.py
  * Include clear inline comments explaining:
    - Where to customize default paths on the Pi and on Windows.
    - How the “newest files” heuristic works.
    - Where future improvements could plug in (e.g. better preset handling).

====== OUTPUT FORMAT ======
Please output:

1. A short “how to run” note, including pip install commands in a code block (e.g. pip install paramiko).
2. A complete main.py implementation in one code block that I can copy directly.
   - The code should be syntactically correct and self-contained.
   - It’s OK if some behavior is basic, but the connection, running commands, and log output must work in practice.
3. Brief comments in the code where I should adapt paths and defaults for my own Pi.

Focus on getting a robust, working first version rather than a perfectly polished UI.
```