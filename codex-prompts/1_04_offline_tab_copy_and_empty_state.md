# SensePi GUI – Make the Offline tab’s wording more discoverable

You are an AI pair-programmer working on the SensePi repository.

**Goal:** Make it clearer that the “Offline” tab is specifically about **log files** and that it can both scan local logs and download logs from the Pi. This is purely a UI‑copy / wording change plus a slightly more helpful empty/idle state.

We’ll update:

- The tab title in `MainWindow`.
- The header label and status label in `OfflineTab`.
- The default empty state message when no files are listed.

---

## Context

Current pieces of UI wording:

- In `src/sensepi/gui/main_window.py`, the Offline tab is added as:

  ```python
  self._tabs.addTab(self.offline_tab, "Offline")
  ```

- In `src/sensepi/gui/tabs/tab_offline.py`, `OfflineTab.__init__` builds the header row and default status text:

  ```python
  top_row = QHBoxLayout()
  top_row.addWidget(QLabel("Recent logs:"))
  self.btn_refresh = QPushButton("Refresh")
  self.btn_sync = QPushButton("Sync logs from Pi")
  self.btn_browse = QPushButton("Browse…")
  # ...
  self.status_label = QLabel("Select a log file to view.", self)
  ```

This is functional but a bit vague for students—“Offline” could mean offline mode / no network, rather than “Offline log viewer”.

---

## Task

1. Rename the Offline tab to **Offline logs** in `MainWindow`.
2. Clarify the header + idle text in `OfflineTab` so that:
   - It’s obvious that this is a *log browser*.
   - The empty state explains that you can either scan local logs or sync from the Pi.

No behavioural changes; just strings and initial UI state.

---

## Step‑by‑step implementation

### 1. Rename the tab in `MainWindow`

In `src/sensepi/gui/main_window.py`, update the tab text when adding `OfflineTab`:

```python
self._tabs.addTab(self.signals_tab, "Signals")
self._tabs.addTab(self.fft_tab, "FFT")
self._tabs.addTab(self.settings_tab, "Settings")
self._tabs.addTab(self.offline_tab, "Offline logs")  # renamed
self._tabs.addTab(self.logs_tab, "Logs")
```

### 2. Improve the OfflineTab header label

In `OfflineTab.__init__` (`src/sensepi/gui/tabs/tab_offline.py`), change the header label to make its purpose explicit:

```python
top_row = QHBoxLayout()
top_row.addWidget(QLabel("Offline log files:"))
self.btn_refresh = QPushButton("Refresh")
self.btn_sync = QPushButton("Sync logs from Pi")
# (plus any new button you added, such as Sync & open latest)
self.btn_browse = QPushButton("Browse…")
```

If you created the `Sync && open latest` button from another task, keep that in place—only the static text needs adjusting.

### 3. Make the empty state message more helpful

Still in `OfflineTab.__init__`, adjust the initial status label to mention both local and Pi logs:

```python
self.status_label = QLabel(
    "No log file loaded. Use Refresh to scan local logs or "
    "Sync logs from Pi to download new runs.",
    self,
)
```

### 4. Optionally, update `_populate_files` to reflect when no files are present

At the end of `_populate_files()` you can update the status label based on whether any files were found.

Current method (simplified):

```python
def _populate_files(self) -> None:
    self.file_list.clear()
    for path in self._candidate_logs():
        self.file_list.addItem(str(path))
```

Extend it to set a more helpful message in the “no logs” case:

```python
def _populate_files(self) -> None:
    self.file_list.clear()
    count = 0
    for path in self._candidate_logs():
        self.file_list.addItem(str(path))
        count += 1

    if count == 0:
        self.status_label.setText(
            "No local logs found. After recording on the Pi, click "
            "Sync logs from Pi to download and view runs here."
        )
    else:
        self.status_label.setText(
            f"Found {count} log file(s). Select one to view, or sync new logs from the Pi."
        )
```

This keeps the status label in sync with the list contents and subtly reminds users about the Pi‑sync path even when local logs already exist.

---

## Acceptance criteria

- The main window’s tab now reads **Offline logs** instead of **Offline**.
- The Offline tab header and status label clearly communicate that it is a log browser.
- When there are no local log files, the status label explicitly tells users to:
  - Record on the Pi.
  - Use **Sync logs from Pi** to download and view those logs.
- No behavioural changes to syncing or plotting—only text and messaging are affected.
