# Prompt 4 – Add convenience features to the SSH + GUI tool

You are extending the same Tkinter + Paramiko GUI in `main.py` that controls the two Raspberry Pi logging scripts:

- `adxl203_ads1115_logger.py` (ADXL203 via ADS1115, single CSV + `.meta.json` under `--out`).
- `mpu6050_multi_logger.py` (multi‑MPU6050, one file per sensor + `.meta.json` under `--out`).

The app already supports:

- SSH connection management (connect/disconnect, Paramiko-based).
- Selecting sensor type (ADXL or MPU6050) and configuring CLI parameters.
- Starting and stopping a recording run.
- Live console output in a `Text` widget via a background thread and queue.
- Automatic download of new log files at the end of each run, plus a **manual “Download newest files”** button.

Now I want to add **quality-of-life features**: presets, a status bar, basic validation, and an “open local folder” button.

## 1. Preset configurations

Add a dropdown (ComboBox) of “presets” for common recording configurations, for example:

- `Quick ADXL test (10 s @ 100 Hz)`
- `3×MPU6050 full sensors (60 s @ 200 Hz)`

Requirements:

- Presets should be defined as simple in-memory structures (e.g. a dict of dicts). No persistence is required yet, but it should be easy to persist later.
- Selecting a preset should:
  - Automatically switch the sensor type (ADXL vs MPU).
  - Pre-fill all relevant parameter fields in the GUI, e.g.:
    - For ADXL: `rate`, `duration`, `channels`, `out`, `addr`, `map`, `calibrate`, `lp-cut`.
    - For MPU6050: `rate`, `duration` or `samples`, `sensors`, `channels`, `out`, `format`, `prefix`, `dlpf`, `temp` flag, flushing options if appropriate.
- Provide an **“Apply preset”** button next to the ComboBox that applies the currently selected preset.

## 2. Status bar at the bottom of the window

Add a small status bar at the bottom of the main window that displays three pieces of information:

1. **SSH connection status**, e.g.:
   - `SSH: Disconnected`
   - `SSH: Connected to pi@192.168.1.10`
2. **Current running state**, e.g.:
   - `Run: Idle`
   - `Run: Running ADXL`
   - `Run: Running MPU6050`
3. **Last download summary**, e.g.:
   - `Last download: 3 files at 2025-11-24 10:32:15`
   - `Last download: error – see log`

Implementation notes:

- Use `tk.StringVar` (or similar) for each status field so they can be updated easily from the code.
- Update these fields at appropriate times:
  - When SSH connects/disconnects.
  - When a run starts/finishes.
  - When automatic or manual downloads complete or fail.

## 3. Basic validation with popup errors

Before starting a run, perform some basic validation. On **“Start recording”**:

- Validate that the **rate** is a positive number (> 0).
- Validate that the **remote `out` folder** for the selected sensor type is not empty.
- In **MPU6050 mode**:
  - Validate that the `sensors` field is a comma-separated list of integers in `{1,2,3}`.
  - Ensure the parsed set is a non-empty subset of `{1,2,3}`.

If validation fails:

- Show a `messagebox.showerror("Title", "Error message")` with a clear explanation.
- Do **not** start the run.

Keep the validation logic in a small helper method (e.g. `_validate_params()` that returns `True/False`) and call it at the very start of the run-start logic.

## 4. Button to open the local download folder

Add a button (for example, “Open local folder”) that opens the current local download directory in the system file explorer.

- Assume we are on Windows; you can use `subprocess.Popen(["explorer", folder])` or similar.
- Only enable the button when the local folder path is set and actually exists on disk.
- If the path is invalid or cannot be opened, show a simple error message via `messagebox.showerror` and log a short message to the log widget.

## Requirements and constraints

- Keep **all existing functionality** intact:
  - SSH connection management.
  - Run control.
  - Live log output.
  - Auto-download + manual download.
- You may refactor the code slightly (e.g. small helper methods or a `Preset` data structure) to keep things clean, but avoid heavy over-engineering.
- Ensure that all Tkinter updates that originate from background threads still go through `root.after(...)` or a main-thread-safe mechanism.
- Use clear, concise comments for the new features (presets, status bar, validation, open-folder button).

## Tasks for you

1. Update the existing `main.py` in-place to add:
   - Preset dropdown + apply button.
   - Status bar with 3 textual fields.
   - Parameter validation on “Start recording”.
   - “Open local folder” button.
2. Show the **full updated `main.py`** file in your answer (not a diff).
3. At the top of your answer, provide a short summary of what you added/changed so I can quickly scan the new features.

## What to include in your answer

- The complete, updated `main.py` file.
- A brief explanation (a few paragraphs) of how:
  - Presets are represented in code and applied.
  - Status bar is updated.
  - Validation logic is structured.
  - The “Open local folder” button works.

You do **not** need to touch the Raspberry Pi scripts themselves; only modify the desktop GUI application.
