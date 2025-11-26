# Prompt: Logs tab, remote log sync, session naming, and clearer recording feedback

You are an AI coding assistant working on the **sensepi** project.
This prompt bundles a set of small but high‑impact UX improvements:

1. Add a simple **Logs** tab that shows local application logs (and optionally last remote stderr).
2. Add **remote log sync** from the Pi using the existing SFTP support.
3. Expose a **session name** concept in the GUI and propagate it into filenames/paths.
4. Improve **recording vs streaming** visual feedback in the Signals tab.

Focus on incremental integration; avoid big refactors.

---

## Context: existing pieces

Relevant modules:

- `sensepi/gui/main_window.py`
- `sensepi/gui/tabs/tab_signals.py`
- `sensepi/gui/tabs/tab_offline.py`
- `sensepi/remote/ssh_client.py` (SFTP)
- `sensepi/remote/pi_recorder.py`
- Logging configuration (where app logs are written, e.g. `logs/` under `AppPaths.logs_dir`)

SignalsTab already has:

- Start/Stop buttons.
- A "Recording" checkbox that toggles `--no-record` flag in the Pi logger.
- A hint label (`_mode_hint_label`) which shows some explanatory text.

The project already has SFTP/SSH helpers used to sync configs to the Pi.

---

## Part 1: Simple Logs tab (local logs viewer)

1. Create a new tab class, e.g. `LogsTab` in `sensepi/gui/tabs/tab_logs.py`:

   - Inherits from `QWidget`.
   - Contains:
     - A `QComboBox` to select a log file from `AppPaths.logs_dir`.
     - A read‑only `QPlainTextEdit` to display log content.
     - A **Refresh** button to re‑read the selected file.

   Sketch:

   ```python
   class LogsTab(QWidget):
       def __init__(self, app_config: AppConfig, parent: QWidget | None = None):
           super().__init__(parent)
           self._app_config = app_config
           self._file_combo = QComboBox()
           self._view = QPlainTextEdit()
           self._view.setReadOnly(True)
           self._refresh_button = QPushButton("Refresh")
           ...
   ```

2. Implement behaviour:

   - On init (and when Refresh is clicked), list files in `app_config.paths.logs_dir` with a reasonable pattern (e.g. `*.log`).
   - Populate the combo box with filenames.
   - When a filename is selected or Refresh is clicked:
     - Read the file (tail‑style or whole file, depending on size; start with whole file).
     - Show the content in the text edit.

   Optional extras (only if easy):

   - A "Follow tail" checkbox to auto‑scroll to end when the file grows.
   - Basic search within the log view.

3. Wire LogsTab into `MainWindow`:

   - Instantiate `LogsTab` in `MainWindow.__init__`.
   - Add it to the tab widget with a title like `"Logs"`.

---

## Part 2: Remote log sync from Pi

1. Add a button somewhere sensible (either in **Settings** or **Offline** tab):

   - For this prompt, prefer adding to **OfflineTab**, e.g. `"Sync logs from Pi"`.

   In `OfflineTab`:

   - Add a `QPushButton("Sync logs from Pi")` near the file list.
   - Connect it to a slot `_on_sync_from_pi_clicked`.

2. Implement `_on_sync_from_pi_clicked` using existing SSH/SFTP logic:

   - Determine the **current host** configuration (you may need a reference from `RecorderTab` or `AppConfig.host_inventory`).
   - Establish an SSH connection (`SSHClient`) and open an SFTP session.
   - List files under `host_cfg.data_dir` (or equivalent) on the Pi.
   - For a first iteration, you can:
     - Download all new files into `AppPaths.data_root / "raw"` (preserving filenames), or
     - Show a simple modal dialog listing files and let the user pick which to download (if you have an existing selection UI).

   Example sketch using `paramiko.SFTPClient` via your wrapper:

   ```python
   with ssh_client.open_sftp() as sftp:
       for entry in sftp.listdir_attr(host_cfg.data_dir):
           if not entry.filename.endswith((".csv", ".jsonl")):
               continue
           remote_path = f"{host_cfg.data_dir}/{entry.filename}"
           local_path = raw_dir / entry.filename
           sftp.get(remote_path, str(local_path))
   ```

   - After sync completes, call `_refresh_file_list()` so the new files appear in the Offline tab.

3. Surface errors via existing error pipeline:

   - Catch network or auth exceptions.
   - Emit/forward error messages using the same mechanism as `RecorderTab.error_reported`
     (or create a simple error dialog in OfflineTab).

---

## Part 3: Session naming / metadata

1. In **SignalsTab**, add a `QLineEdit` for a "Session name":

   - Default value can be empty or something like `"session"` with an increment.
   - Place it near the Start/Stop buttons.

   Example:

   ```python
   self._session_name_edit = QLineEdit()
   self._session_name_edit.setPlaceholderText("Session name (optional)")
   ```

2. Pass the session name into the recording/streaming pipeline:

   - When `RecorderTab` starts a stream with recording enabled, pass the session name along
     as part of the extra arguments sent to the Pi logger, e.g. `--session-name` or `--prefix`,
     depending on what the Pi script supports.
   - If the Pi script does not currently accept a session name, add an optional CLI flag to it
     in `raspberrypi_scripts/mpu6050_multi_logger.py` and incorporate the session name into
     the log filename or directory.

   This part will require **coordinated changes** in:

   - `SignalsTab` → pass session name via signal or method call to `RecorderTab`.
   - `RecorderTab._start_stream` → include it in the `extra_args` passed to `PiRecorder`.
   - Pi‑side script → use it to prefix filenames or session directory.

3. Optionally, when downloading logs from Pi (Part 2), use the session name to suggest
   a target subdirectory under `data/raw` (e.g. `data/raw/<session_name>/`).

---

## Part 4: Better feedback on recording vs streaming

1. In **SignalsTab**, change the appearance of the Start/Stop/Recording controls:

   - When the **Recording** checkbox is enabled and streaming is active:
     - Make the Start button (or a dedicated small "REC" indicator) visibly red,
       e.g. via `setStyleSheet("background-color: red; ...")`.
   - When not recording:
     - Use the normal style.

   Make sure to reset styles when stopping the stream.

2. Enhance `_mode_hint_label` to show:

   - Whether recording is enabled or disabled.
   - Where the remote logs are going (if known), e.g. `Recording to: <data_dir>`.

   Use the config information from `pi_config.yaml` or from `HostConfig`/`PiRecorder`
   to derive the path. If an exact path is not available, keep the text generic.

3. Ensure that the visual state is updated:

   - When the Recording checkbox changes.
   - When the stream actually starts/stops (using existing `stream_started` / `stream_stopped` signals).

---

## Behaviour expectations

After your changes:

- The GUI has a **Logs** tab where users can inspect application log files
  without leaving the app.
- Users can click **Sync logs from Pi** to pull remote logs into `data/raw`,
  then open them from the Offline tab.
- Users can specify a **session name**, which is carried into Pi log filenames
  and/or local directory names, making offline logs easier to organise.
- When recording is enabled, the UI makes it **very obvious** (colour/icon/text)
  that data is being recorded, not just streamed.

---

## Constraints & style

- Do not introduce new dependencies beyond what the project already uses (Qt, paramiko, etc.).
- Reuse existing SSH/SFTP helper classes instead of talking to `paramiko` directly where possible.
- Keep changes incremental; avoid rewriting the main window or tabs.
