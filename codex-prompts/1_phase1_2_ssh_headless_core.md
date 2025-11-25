# Prompt – Phase 1.2: Headless SSH + sensor runner (no Tk / Qt)

You are an AI coding agent continuing work on the same repo as in Phase 1.1.

Now you will **extract all non‑Tkinter SSH + remote run logic from `main.py` into a pure‑Python module** and add a small console test script.

The goal is to have:

- A reusable, UI‑agnostic SSH client + sensor runner module (`ssh_client/ssh_manager.py`).
- A simple CLI test that:
  1. Connects to the Pi over SSH.
  2. Runs a short `mpu6050_multi_logger.py` or `adxl203_ads1115_logger.py` job with `--stream-stdout`.
  3. Prints the JSON lines as they arrive.
  4. Downloads the newly created CSV files when the run is done.

**Important:** This module must have **no Tkinter or Qt imports** so it can be used from the existing Tk app, future Qt app, or from CLI scripts.

---

## 1. Create the `ssh_client` package

At the repo root (next to `main.py` and `to_be_integrated/`), create:

```text
ssh_client/
  __init__.py
  ssh_manager.py
```

### 1.1 `ssh_client/__init__.py`

Export the public API so other code can import from `ssh_client` directly:

```python
# ssh_client/__init__.py
from .ssh_manager import (
    SSHClientManager,
    RemoteRunContext,
    RUN_MODE_RECORD_ONLY,
    RUN_MODE_RECORD_AND_LIVE,
    RUN_MODE_LIVE_ONLY,
    AdxlParams,
    MpuParams,
    build_adxl_command,
    build_mpu_command,
)
```

---

## 2. Implement `ssh_client/ssh_manager.py` (pure Python, no UI)

**File:** `ssh_client/ssh_manager.py`

Start the file with imports and data types:

```python
# ssh_client/ssh_manager.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import os
import threading

import paramiko  # ensure paramiko is installed (already in requirements.txt)
```

### 2.1 Shared dataclasses

Move `RemoteRunContext` from `main.py` into this module and make it UI‑agnostic:

```python
@dataclass
class RemoteRunContext:
    """
    Holds info about a remote sensor run and its outputs.

    This is UI-agnostic and can be used from Tk, Qt, or console scripts.
    """
    command: str
    script_name: str
    sensor_type: str          # "adxl" or "mpu"
    remote_out_dir: str
    local_out_dir: str
    start_snapshot: Dict[str, float] = field(default_factory=dict)
```

Add two parameter dataclasses to describe logger configuration without UI:

```python
@dataclass
class AdxlParams:
    script_path: str
    rate: float
    channels: str = "both"
    out_dir: str = "/home/verwalter/sensor/logs"
    duration: Optional[float] = None
    addr: Optional[str] = "0x48"
    channel_map: Optional[str] = "x:P0,y:P1"
    calibrate: Optional[int] = 300
    lp_cut: Optional[float] = 15.0


@dataclass
class MpuParams:
    script_path: str
    rate: float
    sensors: str = "1,2,3"
    channels: str = "default"
    out_dir: str = "/home/verwalter/sensor/logs"
    duration: Optional[float] = None
    samples: Optional[int] = None
    fmt: str = "csv"
    prefix: str = "mpu"
    dlpf: Optional[str] = "3"
    temp: bool = False
    flush_every: Optional[int] = 2000
    flush_seconds: Optional[float] = 2.0
    fsync_each_flush: bool = False
```

Define run‑mode constants that match the Tk app’s combobox strings, so both UIs can share them:

```python
RUN_MODE_RECORD_ONLY = "Record only"
RUN_MODE_RECORD_AND_LIVE = "Record + live plot"
RUN_MODE_LIVE_ONLY = "Live plot only (no-record)"
```

### 2.2 `SSHClientManager`

Move the existing `SSHClientManager` from `main.py` into this module with minimal changes:

```python
class SSHClientManager:
    """Encapsulates SSH and SFTP connections to the Raspberry Pi."""

    def __init__(self) -> None:
        self.client: Optional[paramiko.SSHClient] = None
        self.sftp: Optional[paramiko.SFTPClient] = None
        self._lock = threading.Lock()

    # ---- connection handling ----
    def connect(
        self,
        host: str,
        port: int,
        username: str,
        password: str = "",
        pkey_path: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        """Establish SSH + SFTP connections."""
        with self._lock:
            if self.client:
                self.disconnect()

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            kwargs = {"hostname": host, "port": int(port), "username": username}
            if pkey_path:
                kwargs["key_filename"] = pkey_path
            else:
                kwargs["password"] = password

            ssh.connect(**kwargs, look_for_keys=not pkey_path, allow_agent=False, timeout=timeout)
            self.client = ssh
            self.sftp = ssh.open_sftp()

    def disconnect(self) -> None:
        with self._lock:
            if self.sftp:
                try:
                    self.sftp.close()
                except Exception:
                    pass
                self.sftp = None
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None

    def is_connected(self) -> bool:
        return self.client is not None

    # ---- command helpers ----
    def exec_command_stream(self, command: str) -> Tuple[paramiko.Channel, any, any]:
        """
        Execute a command and return (channel, stdout_file, stderr_file)
        so the caller can stream lines as they arrive.
        """
        if not self.client:
            raise RuntimeError("SSH not connected")
        transport = self.client.get_transport()
        if not transport:
            raise RuntimeError("SSH transport not available")
        channel = transport.open_session()
        channel.exec_command(command)
        stdout = channel.makefile("r")
        stderr = channel.makefile_stderr("r")
        return channel, stdout, stderr

    def exec_quick(self, command: str) -> Tuple[str, str, int]:
        """
        Run a short command and return (stdout_str, stderr_str, exit_status).
        """
        if not self.client:
            raise RuntimeError("SSH not connected")
        stdin, stdout, stderr = self.client.exec_command(command)
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        status = stdout.channel.recv_exit_status()
        return out, err, status

    # ---- SFTP helpers ----
    def list_dir(self, remote_dir: str):
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        return self.sftp.listdir_attr(remote_dir)

    def listdir_with_mtime(self, remote_dir: str) -> Dict[str, float]:
        """Return {filename: mtime} for a remote directory."""
        entries = self.list_dir(remote_dir)
        return {entry.filename: float(entry.st_mtime) for entry in entries}

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download one file via SFTP."""
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        local_dir = os.path.dirname(os.path.abspath(local_path))
        os.makedirs(local_dir, exist_ok=True)
        self.sftp.get(remote_path, local_path)
```

### 2.3 Command builders (`build_adxl_command` and `build_mpu_command`)

Move the logic in `App.build_command` into pure functions that take `AdxlParams` / `MpuParams` and a run mode.

```python
def build_adxl_command(
    params: AdxlParams,
    run_mode: str = RUN_MODE_RECORD_ONLY,
    stream_every: int = 1,
) -> Tuple[str, str]:
    """
    Build the python3 command line for an ADXL203 logger run.

    Returns (command_str, script_name).
    """
    remote_path = params.script_path.strip() or "/home/verwalter/sensor/adxl203_ads1115_logger.py"
    cmd_parts = [
        "python3",
        remote_path,
        "--rate", str(params.rate),
        "--channels", params.channels,
        "--out", params.out_dir,
    ]

    if params.duration is not None:
        cmd_parts += ["--duration", str(params.duration)]
    if params.addr:
        cmd_parts += ["--addr", str(params.addr)]
    if params.channel_map:
        cmd_parts += ["--map", params.channel_map]
    if params.calibrate is not None:
        cmd_parts += ["--calibrate", str(params.calibrate)]
    if params.lp_cut is not None:
        cmd_parts += ["--lp-cut", str(params.lp_cut)]

    if run_mode in (RUN_MODE_RECORD_AND_LIVE, RUN_MODE_LIVE_ONLY):
        if run_mode == RUN_MODE_LIVE_ONLY:
            cmd_parts.append("--no-record")
        cmd_parts.append("--stream-stdout")
        cmd_parts += ["--stream-every", str(int(max(1, stream_every)))]
        cmd_parts += ["--stream-fields", "x_lp,y_lp"]

    script_name = os.path.basename(remote_path) or "adxl203_ads1115_logger.py"
    return " ".join(cmd_parts), script_name


def build_mpu_command(
    params: MpuParams,
    run_mode: str = RUN_MODE_RECORD_ONLY,
    stream_every: int = 1,
) -> Tuple[str, str]:
    """
    Build the python3 command line for an MPU6050 multi-sensor logger run.

    Returns (command_str, script_name).
    """
    remote_path = params.script_path.strip() or "/home/verwalter/sensor/mpu6050_multi_logger.py"
    cmd_parts = [
        "python3",
        remote_path,
        "--rate", str(params.rate),
        "--sensors", params.sensors,
        "--channels", params.channels,
        "--out", params.out_dir,
        "--format", params.fmt,
    ]

    if params.duration is not None:
        cmd_parts += ["--duration", str(params.duration)]
    if params.samples is not None:
        cmd_parts += ["--samples", str(params.samples)]
    if params.prefix:
        cmd_parts += ["--prefix", params.prefix]
    if params.dlpf:
        cmd_parts += ["--dlpf", str(params.dlpf)]
    if params.temp:
        cmd_parts.append("--temp")
    if params.flush_every is not None:
        cmd_parts += ["--flush-every", str(params.flush_every)]
    if params.flush_seconds is not None:
        cmd_parts += ["--flush-seconds", str(params.flush_seconds)]
    if params.fsync_each_flush:
        cmd_parts.append("--fsync-each-flush")

    if run_mode in (RUN_MODE_RECORD_AND_LIVE, RUN_MODE_LIVE_ONLY):
        if run_mode == RUN_MODE_LIVE_ONLY:
            cmd_parts.append("--no-record")
        cmd_parts.append("--stream-stdout")
        cmd_parts += ["--stream-every", str(int(max(1, stream_every)))]
        cmd_parts += ["--stream-fields", "ax,ay,gz"]

    script_name = os.path.basename(remote_path) or "mpu6050_multi_logger.py"
    return " ".join(cmd_parts), script_name
```

These are essentially the same semantics as `App.build_command`, just parameterized and reusable.

---

## 3. Add a console test script: stream JSON and download CSV

Create a script at the repo root (next to `main.py`) to test the new module headlessly.

**File (NEW):** `ssh_headless_test.py`

```python
#!/usr/bin/env python3
"""
ssh_headless_test.py

Headless test of ssh_client/ssh_manager.py.

- Connects to the Raspberry Pi via SSH.
- Runs a short mpu6050_multi_logger.py job with --stream-stdout.
- Prints JSON lines from stdout as they arrive.
- Downloads the new CSV/JSONL files created by that run.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from ssh_client import (
    SSHClientManager,
    RemoteRunContext,
    MpuParams,
    RUN_MODE_RECORD_AND_LIVE,
    build_mpu_command,
)


def main() -> int:
    # Connection parameters (override via env if needed)
    host = os.environ.get("SENSE_PI_HOST", "192.168.0.6")
    port = int(os.environ.get("SENSE_PI_PORT", "22"))
    username = os.environ.get("SENSE_PI_USER", "verwalter")
    password = os.environ.get("SENSE_PI_PASSWORD", "")

    # Remote paths consistent with existing loggers
    remote_script = os.environ.get(
        "SENSE_PI_MPU_SCRIPT", "/home/verwalter/sensor/mpu6050_multi_logger.py"
    )
    remote_out_dir = os.environ.get(
        "SENSE_PI_REMOTE_OUT", "/home/verwalter/sensor/logs"
    )
    local_out_dir = Path(os.environ.get("SENSE_PI_LOCAL_OUT", "./logs_from_pi")).resolve()
    local_out_dir.mkdir(parents=True, exist_ok=True)

    mgr = SSHClientManager()
    print(f"Connecting to {username}@{host}:{port} ...")
    mgr.connect(host, port, username, password=password)

    params = MpuParams(
        script_path=remote_script,
        rate=100.0,
        sensors="1",
        channels="default",
        out_dir=remote_out_dir,
        duration=5.0,         # short run for testing
        fmt="csv",
        prefix="mpu_headless",
        dlpf="3",
        temp=False,
        flush_every=2000,
        flush_seconds=2.0,
        fsync_each_flush=False,
    )

    cmd, script_name = build_mpu_command(
        params,
        run_mode=RUN_MODE_RECORD_AND_LIVE,
        stream_every=10,
    )

    print(f"Command: {cmd}")
    start_snapshot = mgr.listdir_with_mtime(remote_out_dir)
    ctx = RemoteRunContext(
        command=cmd,
        script_name=script_name,
        sensor_type="mpu",
        remote_out_dir=remote_out_dir,
        local_out_dir=str(local_out_dir),
        start_snapshot=start_snapshot,
    )

    channel, stdout, stderr = mgr.exec_command_stream(ctx.command)

    print("Streaming JSON lines from stdout:")
    for raw_line in iter(stdout.readline, ""):
        if not raw_line:
            break
        line = raw_line.strip()
        print(line)
        # optional: parse to ensure it's valid JSON
        try:
            _ = json.loads(line)
        except json.JSONDecodeError:
            pass

        if channel.exit_status_ready():
            break

    exit_status = channel.recv_exit_status()
    print(f"Remote command finished with status {exit_status}")

    # Diff remote directory and download new files
    end_snapshot = mgr.listdir_with_mtime(ctx.remote_out_dir)

    new_files = []
    for name, mtime in end_snapshot.items():
        old_mtime = ctx.start_snapshot.get(name)
        if old_mtime is None or mtime > old_mtime + 1e-6:
            new_files.append(name)

    if not new_files:
        print("No new files detected.")
        return exit_status

    print(f"Downloading {len(new_files)} new file(s) to {local_out_dir}...")
    for fname in sorted(new_files):
        remote_path = f"{ctx.remote_out_dir.rstrip('/')}/{fname}"
        local_path = local_out_dir / fname
        print(f"  {remote_path} -> {local_path}")
        mgr.download_file(remote_path, str(local_path))

    return exit_status


if __name__ == "__main__":
    sys.exit(main())
```

You can later extend this in another prompt to support an ADXL test mode using `AdxlParams` and `build_adxl_command`.

---

## 4. (Optional) Refactor `main.py` to use the new module

You don’t need to fully refactor the Tk GUI in this prompt, but you **may** start using the shared module right away:

1. Remove the `RemoteRunContext` and `SSHClientManager` definitions from `main.py`.
2. At the top of `main.py`, add:

   ```python
   from ssh_client import (
       SSHClientManager,
       RemoteRunContext,
       AdxlParams,
       MpuParams,
       RUN_MODE_RECORD_ONLY,
       RUN_MODE_RECORD_AND_LIVE,
       RUN_MODE_LIVE_ONLY,
       build_adxl_command,
       build_mpu_command,
   )
   ```

3. Change `App.build_command` so it just builds `AdxlParams` / `MpuParams` from Tk variables and calls the appropriate builder:

   - Map `self.run_mode_var.get()` to one of the three `RUN_MODE_*` constants.
   - Use `self._get_stream_every()` for `stream_every`.
   - Return `(cmd_str, script_name)` from `build_adxl_command` / `build_mpu_command`.

This keeps all SSH + command‑building logic in one place, usable from both Tk and the future Qt app.

---

## 5. Acceptance criteria for Phase 1.2

- `ssh_client/ssh_manager.py` contains:
  - `SSHClientManager` with `connect`, `disconnect`, `exec_command_stream`, `exec_quick`, `listdir_with_mtime`, `download_file`.
  - `RemoteRunContext`, `AdxlParams`, `MpuParams` dataclasses.
  - `RUN_MODE_RECORD_ONLY`, `RUN_MODE_RECORD_AND_LIVE`, `RUN_MODE_LIVE_ONLY` constants.
  - `build_adxl_command` and `build_mpu_command` that replicate `App.build_command` behavior.
- `ssh_headless_test.py`:
  - Connects to the Pi using env or defaults.
  - Runs a short `mpu6050_multi_logger.py` job with `--stream-stdout`.
  - Prints JSON lines as they arrive.
  - Downloads new files into `./logs_from_pi`.
  - Exits with the remote command’s exit code.
- The new `ssh_client` module has **no Tk / Qt imports** and can be imported from:
  - `main.py` (Tk GUI),
  - the future Qt GUI (`to_be_integrated`),
  - and standalone scripts like `ssh_headless_test.py`.
