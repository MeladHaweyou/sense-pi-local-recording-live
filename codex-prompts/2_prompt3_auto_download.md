# Prompt 3 – Improve auto-download after each run

You are continuing work on the same Tkinter + Paramiko GUI app in `main.py` that controls two sensor logging scripts on a remote Raspberry Pi:

- `adxl203_ads1115_logger.py` — ADXL203 via ADS1115 logger (single CSV + `.meta.json` under `--out`).
- `mpu6050_multi_logger.py` — multi‑MPU6050 logger (one file per sensor + `.meta.json` under `--out`).

The GUI already supports:

- Connecting to the Raspberry Pi over SSH (Paramiko).
- Selecting the sensor type (ADXL vs. MPU6050) and configuring parameters.
- Starting and stopping a recording run via SSH.
- Streaming stdout/stderr into a Tkinter `Text` widget using a background thread + queue.
- Manually downloading “newest files” from the remote `--out` directory via an SFTP helper (a button like “Download newest files”).

Now I want you to **upgrade `main.py` so that log file downloads happen automatically at the end of each recording run.**

## New behaviour I want

1. **When I click “Start recording”:**

   - Determine the remote output directory (`--out`) for the current sensor type (ADXL or MPU6050) based on the current GUI fields.
   - Take a **snapshot** of that remote output directory before starting the run:
     - Use SFTP to list all files in the folder.
     - Store a mapping `{filename: mtime}` (or similar).
   - Store this snapshot as part of a `RemoteRunContext` object for the current run.

2. **When the remote script terminates** (the background reader detects EOF and exit status is available):

   - Automatically trigger logic to:
     - List the remote output directory again via SFTP.
     - Compute which files are **new**:
       - Files that were not present in the initial snapshot, or
       - Files whose modification time is newer than in the snapshot.
     - Download exactly those “new” files into the selected local folder on the Windows PC.
   - Append messages into the log text area, for example:
     - `Run finished, downloading N new files…`
     - `Downloaded file X.csv to C:\path\to\logs\X.csv`
   - Do **not** delete remote files.

3. The logic must work for **both sensor types**:

   - For the ADXL script, use the `--out` folder configured for ADXL.
   - For the MPU6050 script, use its `--out` folder.
   - Keep track of which sensor type is active in the current run (e.g. a field like `"adxl"` vs `"mpu"` in the run context).

4. **Threading / UI rules:**

   - The detection of “process finished” can stay in the **same background thread** that reads stdout/stderr and receives the exit status.
   - The directory listing and file downloads must run in a background worker thread (you can reuse that same thread) and must **never block the Tkinter mainloop**.
   - Use Tkinter-safe mechanisms like `root.after(...)` or a `queue.Queue` to update the UI and log widget from worker threads.

5. **Code organization:**

   - Introduce a small `RemoteRunContext` class or `@dataclass` that holds at least:
     - `sensor_type` (e.g. `"adxl"` or `"mpu"`),
     - `command` (string that was executed),
     - `remote_out_dir` (string),
     - `local_out_dir` (string),
     - `start_snapshot` (e.g. `Dict[str, float]` mapping filename to mtime).
   - Centralize SFTP logic in a couple of helper methods (e.g. `list_remote_dir_with_mtime(...)`, `download_files(...)`) instead of duplicating code.
   - Add clear comments explaining the workflow:
     - start run → snapshot → run → finished → diff → download → log messages.

6. **Error handling and backwards compatibility:**

   - Keep the existing manual “Download newest files” button as a **manual override** (still usable if needed).
   - If a remote listing or download fails, show a user-friendly error message (e.g. via the log widget and/or `messagebox.showerror`) but do **not** crash the whole app.
   - Make sure the app behaves sensibly even if the run context is missing or partially initialized (graceful early returns with log messages).

## Tasks for you

1. Modify the existing `main.py` **in place** to add this automatic download behaviour.
2. Show the **full updated `main.py`** (not just a diff), so I can drop it into my project directly.
3. Ensure all Tkinter updates performed from background threads go through `root.after(...)` or a queue that is polled from the main thread.
4. Add enough comments so the flow is easy to understand, especially around:
   - how the run context is created,
   - how snapshots are taken,
   - how the finished-run event leads to downloads.

## Implementation guidance

- Assume there is already some kind of `SSHClientManager` with methods like:
  - `start_command(cmd: str, on_exit: Callable[[int], None])`
  - `listdir_with_mtime(remote_dir: str) -> Dict[str, float]`
  - `download_file(remote_path: str, local_path: str)`
- If needed, you may refactor or slightly extend that class, but keep its overall behaviour intact.
- You can introduce small helper methods on the GUI side, such as `_start_run_for_sensor_type(...)`, `_handle_run_finished(...)`, etc., if that keeps things clear.

## What to include in your answer

- The **complete `main.py` file** with the new automatic download functionality integrated.
- A brief explanation (a few paragraphs) at the top of your answer summarizing what you changed and how the auto-download workflow works.
- Inline comments near the threading and SFTP parts to highlight any tricky parts of the implementation.
