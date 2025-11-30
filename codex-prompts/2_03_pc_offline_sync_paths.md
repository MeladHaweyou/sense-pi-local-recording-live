# SensePi Implementation Prompt 3 – PC Offline Sync Uses Shared Path Helpers

In this prompt you will refactor the **PC-side log sync code** so that it
uses the same conventions as the Pi helper module from Prompt 1/2, and
fixes the confusing double session folder nesting.

Typical issue today: a session called `Trial1` may end up under
`data/raw/Trial1/mpu/Trial1/...` on the PC. We want to simplify this so
that the local structure is predictable and student-friendly.

---

## Goal

- Use the shared log path helpers from `sensepi.config.log_paths` to compute
  the **local** root directory for downloaded logs.
- Derive a **single session folder** on the PC for each named session:
  - `data/raw/<session_slug>/...` (or a host-based folder when no session).
- Avoid duplicating the session name in nested directories.
- Keep host-based grouping for unnamed sessions (e.g. `data/raw/<host_slug>/mpu/...`).

Behavioural constraints:

- Do not change the SSH/ SFTP transport layer – keep using existing
  `ssh_client` / `log_sync` code.
- Do not change file **names** that the Pi produces – only the **local
  destination tree** on the PC.

---

## Where to work

The sync logic typically lives in one or more of:

- `src/sensepi/gui/tab_offline.py`
- `src/sensepi/remote/log_sync.py` or `src/sensepi/remote/pi_recorder.py`
- Any helper that walks the remote `~/logs/mpu` tree and copies to
  `data/raw/...`

Look for methods named something like:

- `_download_remote_logs(...)`
- `_sync_from_pi(...)`
- `sync_logs_from_host(...)`

and for code that computes a target root like:

```python
target_root = app_paths.data_raw_dir / session_slug  # or host_name, etc.
```

---

## Suggested helper additions

Extend `sensepi.config.log_paths` with a PC-side helper:

```python
# in src/sensepi/config/log_paths.py

from pathlib import Path
from typing import Optional

def build_pc_session_root(
    raw_root: Path,
    host_slug: str,
    session_name: Optional[str],
    sensor_prefix: str,
) -> Path:
    """Return the local root directory for logs downloaded from the Pi.

    Rules:
    - If session_name is provided: group under data/raw/<session_slug>/
      (no extra nested session directory).
    - If session_name is not provided: group under
      data/raw/<host_slug>/<sensor_prefix>/

    This mirrors the conventions documented in the README.
    """
    if session_name:
        from .log_paths import slugify_session_name  # or import at top
        session_slug = slugify_session_name(session_name)
        return raw_root / session_slug

    # Unnamed session: keep host + sensor grouping
    return raw_root / host_slug / sensor_prefix
```

Adjust names as needed to fit your existing `AppPaths` / config pattern.

---

## Integrate into sync code

Find the code where the local destination directory is currently computed.
It might look something like this (pseudo-approximation):

```python
# src/sensepi/gui/tab_offline.py or similar

raw_root = self.app_paths.data_raw_dir
host_slug = self.current_host.slug

if remote_session_name:
    # Previously this might have created nested Trial1/Trial1 folders
    target_root = raw_root / remote_session_name / "mpu"
else:
    target_root = raw_root / host_slug / "mpu"
```

Replace this with a call to the helper:

```python
from sensepi.config.log_paths import LOG_SUBDIR_MPU, build_pc_session_root

raw_root = self.app_paths.data_raw_dir
host_slug = self.current_host.slug  # or however host is represented

target_root = build_pc_session_root(
    raw_root=raw_root,
    host_slug=host_slug,
    session_name=remote_session_name,
    sensor_prefix=LOG_SUBDIR_MPU,
)
```

Then, when you create directories for individual files, simply do:

```python
local_path = target_root / relative_path_from_pi
local_path.parent.mkdir(parents=True, exist_ok=True)
sftp.get(remote_path.as_posix(), local_path.as_posix())
```

where `relative_path_from_pi` should *not* redundantly include the session
directory twice. Typically, `relative_path_from_pi` should be the path
**inside** `~/logs/mpu` (or inside `~/logs/mpu/<session_slug>`), so that the
destination tree under `target_root` mirrors just the sensor-level folder
or substructure.

---

## Deriving `remote_session_name`

There are several options depending on your existing code:

1. **From GUI / RecorderSession**: If your `RecorderSession` already tracks
   the session name, and you call sync immediately after recording, you can
   pass that in directly.
2. **From remote directory names**: If you are walking `~/logs/mpu` and
   encounter a directory whose name matches a session slug, you can treat
   that as `remote_session_name`.
3. **From `.meta.json`**: If your meta files contain a `session_name` field,
   you can read it once and group accordingly.

For now, pick the simplest approach that fits your current code. A common
pattern is:

```python
# pseudo-code while walking remote tree under ~/logs/mpu
for remote_dir, _, filenames in sftp_walk(log_root):
    rel = remote_dir.relative_to(log_root)
    parts = rel.parts

    if parts:
        remote_session_name = parts[0]  # first level subdir under 'mpu'
    else:
        remote_session_name = None

    target_root = build_pc_session_root(
        raw_root=raw_root,
        host_slug=host_slug,
        session_name=remote_session_name,
        sensor_prefix=LOG_SUBDIR_MPU,
    )
    # then download files into target_root / remaining_parts
```

Adjust the logic to your actual tree structure.

---

## UX: status message

Once files are downloaded, update the Offline tab’s status label or log
message to indicate where they landed, e.g.:

```python
if num_downloaded:
    if remote_session_name:
        msg = f"Synced {num_downloaded} log file(s) for session '{remote_session_name}'."
    else:
        msg = f"Synced {num_downloaded} log file(s) from host '{host_slug}'."
else:
    msg = "No new log files to sync."

self.status_label.setText(msg)
```

This will help students understand which session/host their files are
associated with.

---

## Testing

1. Run a recording on the Pi with a `--session-name` and sync:
   - Confirm the new path under `data/raw` looks like:
     - `data/raw/<session_slug>/mpu_S1_...csv`
     - `data/raw/<session_slug>/mpu_S1_...csv.meta.json`
2. Run a recording *without* a session name and sync:
   - Confirm the path looks like:
     - `data/raw/<host_slug>/mpu/mpu_S1_...csv`
3. Ensure any existing scripts or notebooks that open files from `data/raw`
   are updated if they depended on the old nested structure.

After this prompt, log paths should be consistent and simpler for students
to navigate.
