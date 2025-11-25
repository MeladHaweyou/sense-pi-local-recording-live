# Prompt 2 — Phase 4.2: Auto‑download newest CSVs after a run (Qt + SSH)

You are an AI coding assistant working on the **same Qt project** as in Prompt 1.  
This task is **Phase 4.2** – add automatic download of the newest CSV files from the Pi’s `--out` folder after each remote run, plus a manual **“Download newest file(s)”** action in the Qt SSH tab.

---

## High‑level goals

- We already have SSH connection + remote run control from earlier phases (Qt “SSH” tab + `ssh_client/ssh_manager.py` or similar).
- The Pi logs CSV locally using:
  - `adxl203_ads1115_logger.py` (ADXL203 via ADS1115)fileciteturn0file0  
  - `mpu6050_multi_logger.py` (multi‑MPU6050)fileciteturn0file0  
- At **run start**: snapshot the remote `--out` directory (filename → mtime).
- At **run end**: snapshot again, diff, and download only **new** files to a configurable local folder.
- Provide a small Qt UI in the SSH tab:
  - `QLineEdit` for remote `--out` folder.
  - `QLineEdit` for local download folder + “Browse…” button.
  - Read‑only label: `Last download: X file(s) at YYYY-MM-DD HH:MM`.
  - Button: **“Download newest manually”** (newest N files by mtime).
- **Never block the UI thread** with SFTP operations:
  - Use `QThread` (or worker objects with signals) for listdir + file downloads.

You should reuse the working logic already present in the **Tkinter** app’s `main.py` under the root project.fileciteturn0file0  

---

## Step 0 — Reference: existing Tkinter auto‑download logic

The Tk GUI in `main.py` defines (simplified):

```python
@dataclass
class RemoteRunContext:
    command: str
    script_name: str
    sensor_type: str  # "adxl" or "mpu"
    remote_out_dir: str
    local_out_dir: str
    start_snapshot: Dict[str, float]
```

`SSHClientManager` has:

```python
class SSHClientManager:
    ...
    def listdir_with_mtime(self, remote_dir: str) -> Dict[str, float]:
        """Return {filename: mtime} for a remote directory."""
        entries = self.list_dir(remote_dir)
        return {entry.filename: entry.st_mtime for entry in entries}

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download one file via SFTP."""
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.sftp.get(remote_path, local_path)
```

After a run finishes, it calls:

```python
def _handle_run_finished(self, exit_status: int, ctx: Optional[RemoteRunContext]) -> None:
    if ctx is None:
        return
    try:
        self._log(f"Run finished (status {exit_status}). Scanning {ctx.remote_out_dir} for new files...")
        end_snapshot = self.manager.listdir_with_mtime(ctx.remote_out_dir)
        new_files = []
        for name, mtime in end_snapshot.items():
            old_mtime = ctx.start_snapshot.get(name)
            if old_mtime is None or mtime > old_mtime + 1e-6:
                new_files.append((name, mtime))

        self._log(f"Run finished, downloading {len(new_files)} new files...")
        if not new_files:
            self._set_status(self.download_status, f"Last run: no new files ({self._timestamp()})")
            return

        os.makedirs(ctx.local_out_dir, exist_ok=True)
        for fname, _ in sorted(new_files, key=lambda x: x[1]):
            remote_path = f"{ctx.remote_out_dir.rstrip('/')}/{fname}"
            local_path = os.path.join(ctx.local_out_dir, fname)
            self.manager.download_file(remote_path, local_path)
            self._log(f"Downloaded {fname} -> {local_path}")

        timestamp = self._timestamp()
        self._set_status(self.download_status, f"Last run: {len(new_files)} file(s) downloaded at {timestamp}")
    except Exception as exc:
        ...
```

Manual download (“newest 5 by mtime”) is implemented in `_download_worker`.

Your job is to **mirror this logic in the Qt app**, but using Qt threading + signals instead of Tk threads and `after()`.

---

## Step 1 — Ensure there is a reusable SSH manager for Qt

Assume we already have a Paramiko‑based SSH manager on the Qt side, in something like:

- `ssh_client/ssh_manager.py`

If it doesn’t exist, **derive it from the Tk manager** in `main.py`. A minimal version:

```python
# ssh_client/ssh_manager.py
from __future__ import annotations

import os
from typing import Dict, Optional

import paramiko

class SSHManager:
    def __init__(self) -> None:
        self.client: Optional[paramiko.SSHClient] = None
        self.sftp: Optional[paramiko.SFTPClient] = None

    def connect(self, host: str, port: int, username: str,
                password: str = "", pkey_path: str | None = None) -> None:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = {"hostname": host, "port": int(port), "username": username}
        if pkey_path:
            kwargs["key_filename"] = pkey_path
        else:
            kwargs["password"] = password
        ssh.connect(**kwargs, look_for_keys=not pkey_path, allow_agent=False, timeout=10)
        self.client = ssh
        self.sftp = ssh.open_sftp()

    def disconnect(self) -> None:
        if self.sftp is not None:
            try:
                self.sftp.close()
            except Exception:
                pass
            self.sftp = None
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    def is_connected(self) -> bool:
        return self.client is not None

    def listdir_with_mtime(self, remote_dir: str) -> Dict[str, float]:
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        entries = self.sftp.listdir_attr(remote_dir)
        return {e.filename: e.st_mtime for e in entries}

    def download_file(self, remote_path: str, local_path: str) -> None:
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.sftp.get(remote_path, local_path)
```

Adapt the constructor and connection details if you already wrapped this differently earlier.

---

## Step 2 — Extend the Qt SSH tab UI with download controls

You should have a Qt SSH control tab implemented in something like `to_be_integrated/ui/tab_ssh.py`.  

In that widget, add:

### 2.1 Attributes

```python
# ui/tab_ssh.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from PySide6.QtCore import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog
from PySide6.QtCore import QDateTime

from core.state import AppState
from ssh_client.ssh_manager import SSHManager

@dataclass
class RemoteRunContextQt:
    remote_out_dir: str
    local_out_dir: str
    start_snapshot: Dict[str, float]

class SSHTab(QWidget):
    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

        # SSH manager from earlier phases
        self.ssh_manager = SSHManager()

        self._current_run_ctx: Optional[RemoteRunContextQt] = None

        self._build_ui()
```

### 2.2 UI layout for download options

Inside `_build_ui()` add a “Download newest files” section:

```python
def _build_ui(self) -> None:
    root = QVBoxLayout(self)

    # ... existing SSH connection + run controls ...

    # --- Download section ---
    download_row = QHBoxLayout()
    download_row.addWidget(QLabel("Remote output dir:"))
    self.edit_remote_out = QLineEdit()
    download_row.addWidget(self.edit_remote_out)

    self.btn_use_run_out = QPushButton("Use run --out")
    self.btn_use_run_out.clicked.connect(self._copy_out_from_run_settings)
    download_row.addWidget(self.btn_use_run_out)

    root.addLayout(download_row)

    local_row = QHBoxLayout()
    local_row.addWidget(QLabel("Local download folder:"))
    self.edit_local_download = QLineEdit()
    local_row.addWidget(self.edit_local_download)

    btn_browse = QPushButton("Browse…")
    btn_browse.clicked.connect(self._choose_local_folder)
    local_row.addWidget(btn_browse)

    self.btn_download_newest = QPushButton("Download newest manually")
    self.btn_download_newest.clicked.connect(self.on_download_newest_clicked)
    local_row.addWidget(self.btn_download_newest)

    root.addLayout(local_row)

    self.lbl_last_download = QLabel("Last download: n/a")
    root.addWidget(self.lbl_last_download)

    self.setLayout(root)
```

Helper methods:

```python
def _copy_out_from_run_settings(self) -> None:
    # If you already have a run config panel where the user sets --out, read it here.
    out_dir = self._current_remote_out_dir_from_run_config()
    if out_dir:
        self.edit_remote_out.setText(out_dir)

def _choose_local_folder(self) -> None:
    folder = QFileDialog.getExistingDirectory(self, "Choose local download folder")
    if folder:
        self.edit_local_download.setText(folder)
```

`_current_remote_out_dir_from_run_config()` should return the path that will be passed to `--out` when you start the Pi logger. Implement it appropriately for your actual SSH run UI.

---

## Step 3 — Capture a “run context” at start

When the user clicks the **“Start run”** button in the SSH tab (or equivalent), you should:

1. Validate SSH connection.
2. Determine:
   - `remote_out_dir` (`--out` for the logger script),
   - `local_out_dir` (download folder on Windows/Linux host).
3. Call `ssh_manager.listdir_with_mtime(remote_out_dir)` to snapshot the directory **before** starting the run.
4. Store the snapshot + dirs in a `RemoteRunContextQt`.

Example:

```python
def on_start_run_clicked(self) -> None:
    if not self.ssh_manager.is_connected():
        self._show_error("Not connected", "Connect to the Pi first.")
        return

    remote_out = self.edit_remote_out.text().strip()
    local_out = self.edit_local_download.text().strip()
    if not remote_out:
        self._show_error("Missing remote dir", "Remote --out folder cannot be empty.")
        return
    if not local_out:
        self._show_error("Missing local folder", "Local download folder cannot be empty.")
        return

    try:
        start_snapshot = self.ssh_manager.listdir_with_mtime(remote_out)
    except Exception as e:
        self._show_error("Cannot start run", f"Failed to list remote output folder: {e}")
        return

    self._current_run_ctx = RemoteRunContextQt(
        remote_out_dir=remote_out,
        local_out_dir=local_out,
        start_snapshot=start_snapshot,
    )

    # now build the remote command for adxl/mpu and start it over SSH
    cmd, script_name = self._build_run_command()
    self._start_remote_command(cmd, script_name)
```

The run‑start logic should mirror what you already do in Tk (`build_command` + `exec_command_stream`) but inside Qt.

---

## Step 4 — Auto‑download worker (QThread)

When the remote command completes, you must:

- Compare a new snapshot of the remote dir to `start_snapshot`.
- Download only new/modified files.
- Update `lbl_last_download` in the main thread.

Use a `QThread` worker plus a small `signals` object.

### 4.1 Define signals and worker

Create `ssh_client/download_worker.py` (or place near your SSH tab):

```python
# ssh_client/download_worker.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict

from PySide6.QtCore import QObject, Signal, QThread

from .ssh_manager import SSHManager

@dataclass
class RemoteRunContextQt:
    remote_out_dir: str
    local_out_dir: str
    start_snapshot: Dict[str, float]

class DownloadSignals(QObject):
    log = Signal(str)
    result = Signal(int, str, bool, str)  # n_files, timestamp, ok, error_msg

class AutoDownloadWorker(QThread):
    def __init__(self, manager: SSHManager, ctx: RemoteRunContextQt,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.ctx = ctx
        self.signals = DownloadSignals()

    def run(self) -> None:
        import time
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.signals.log.emit(
                f"Run finished. Scanning {self.ctx.remote_out_dir} for new files..."
            )
            end_snapshot = self.manager.listdir_with_mtime(self.ctx.remote_out_dir)
            new_files: list[tuple[str, float]] = []
            for name, mtime in end_snapshot.items():
                old_mtime = self.ctx.start_snapshot.get(name)
                if old_mtime is None or mtime > old_mtime + 1e-6:
                    new_files.append((name, mtime))

            if not new_files:
                self.signals.log.emit("No new files to download.")
                self.signals.result.emit(0, ts, True, "")
                return

            os.makedirs(self.ctx.local_out_dir, exist_ok=True)
            for fname, _ in sorted(new_files, key=lambda x: x[1]):
                remote_path = f"{self.ctx.remote_out_dir.rstrip('/')}/{fname}"
                local_path = os.path.join(self.ctx.local_out_dir, fname)
                self.manager.download_file(remote_path, local_path)
                self.signals.log.emit(f"Downloaded {fname} -> {local_path}")

            self.signals.result.emit(len(new_files), ts, True, "")
        except Exception as exc:
            self.signals.log.emit(f"[ERROR] Auto-download failed: {exc}")
            self.signals.result.emit(0, ts, False, str(exc))
```

### 4.2 Use the worker in the SSH tab

In your SSH tab class:

```python
from ssh_client.download_worker import AutoDownloadWorker, DownloadSignals, RemoteRunContextQt

class SSHTab(QWidget):
    ...
    def _on_remote_run_finished(self, exit_status: int) -> None:
        ctx = self._current_run_ctx
        if ctx is None:
            return

        worker = AutoDownloadWorker(self.ssh_manager, ctx, parent=self)
        worker.signals.log.connect(self._append_log)      # if you have a log text widget
        worker.signals.result.connect(self._on_auto_download_result)
        worker.start()

        # keep reference if needed, to avoid GC:
        self._last_auto_worker = worker

    def _on_auto_download_result(self, n_files: int, ts: str, ok: bool, err: str) -> None:
        if ok:
            if n_files == 0:
                text = f"Last run: no new files ({ts})"
            else:
                text = f"Last run: {n_files} file(s) downloaded at {ts}"
        else:
            text = f"Last run: download failed at {ts}"
        self.lbl_last_download.setText(text)
        if not ok and err:
            self._show_error("Auto-download failed", err)
        # Clear context once done
        self._current_run_ctx = None
```

`_on_remote_run_finished` must be called from whatever logic tracks the SSH channel / process exit (e.g. a different worker thread or callback).

`_append_log` can simply append to a `QPlainTextEdit` if you have one.

---

## Step 5 — Manual “Download newest” worker

The **“Download newest manually”** button should:

- Use the current `remote_out_dir` and `local_out_dir` from the text fields.
- Download the latest N files by mtime (e.g. N = 5).
- Update `lbl_last_download`.

### 5.1 Worker

Add to `download_worker.py`:

```python
class DownloadNewestWorker(QThread):
    def __init__(self, manager: SSHManager, remote_dir: str, local_dir: str,
                 max_files: int = 5, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.remote_dir = remote_dir
        self.local_dir = local_dir
        self.max_files = max_files
        self.signals = DownloadSignals()

    def run(self) -> None:
        import time, os
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            snap = self.manager.listdir_with_mtime(self.remote_dir)
            items = sorted(snap.items(), key=lambda e: e[1], reverse=True)[: self.max_files]
            if not items:
                self.signals.log.emit("No files found to download.")
                self.signals.result.emit(0, ts, True, "")
                return

            os.makedirs(self.local_dir, exist_ok=True)
            for name, _ in items:
                remote_path = f"{self.remote_dir.rstrip('/')}/{name}"
                local_path = os.path.join(self.local_dir, name)
                self.manager.download_file(remote_path, local_path)
                self.signals.log.emit(f"Downloaded {name} -> {local_path}")

            self.signals.result.emit(len(items), ts, True, "")
        except Exception as exc:
            self.signals.log.emit(f"[ERROR] Manual download failed: {exc}")
            self.signals.result.emit(0, ts, False, str(exc))
```

### 5.2 Hook up the button

Back in `SSHTab`:

```python
from ssh_client.download_worker import DownloadNewestWorker

class SSHTab(QWidget):
    ...

    def on_download_newest_clicked(self) -> None:
        if not self.ssh_manager.is_connected():
            self._show_error("Not connected", "Connect to the Pi first.")
            return

        remote_dir = self.edit_remote_out.text().strip()
        local_dir = self.edit_local_download.text().strip()
        if not remote_dir:
            self._show_error("Missing remote dir", "Remote output directory is empty.")
            return
        if not local_dir:
            self._show_error("Missing local folder", "Local download folder is empty.")
            return

        worker = DownloadNewestWorker(self.ssh_manager, remote_dir, local_dir, max_files=5, parent=self)
        worker.signals.log.connect(self._append_log)
        worker.signals.result.connect(self._on_manual_download_result)
        worker.start()
        self._last_manual_worker = worker

    def _on_manual_download_result(self, n_files: int, ts: str, ok: bool, err: str) -> None:
        if ok:
            text = f"Manual download: {n_files} file(s) at {ts}"
        else:
            text = f"Manual download failed at {ts}"
        self.lbl_last_download.setText(text)
        if not ok and err:
            self._show_error("Download failed", err)
```

---

## Step 6 — End‑to‑end tests

After implementing the above:

1. **Connect** to the Pi from the Qt SSH tab.
2. Configure a remote logger script (ADXL/MPU) that writes to a known `--out` folder (e.g. `/home/verwalter/sensor/logs`).fileciteturn0file0  
3. Set that folder in “Remote output dir”.
4. Choose a local download folder in “Local download folder”.
5. Start a run:
   - On run start, the Qt SSH tab takes a `start_snapshot` of the remote dir.
   - After the run finishes, `AutoDownloadWorker` runs:
     - It diffs remote dir vs snapshot.
     - Downloads new files.
     - Updates `lbl_last_download` with something like:  
       `Last run: 2 file(s) downloaded at 2025-11-24 23:59`.
6. Confirm new CSVs appear in the chosen local folder.
7. Use the **Recorder → View CSV / Split CSV / FFT** tabs to open and inspect those files; they should behave like any other locally captured CSV.

Once this workflow is working and UI remains responsive during downloads, Phase 4.2 is complete.
