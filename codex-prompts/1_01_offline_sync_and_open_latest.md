# SensePi GUI – Add “Sync & open latest” action in Offline tab

You are an AI pair-programmer working on the SensePi repository.

**Goal:** In the Offline tab (`src/sensepi/gui/tabs/tab_offline.py`), add a one-click action that:

- Syncs logs from the selected Raspberry Pi host (reusing existing `_on_sync_from_pi_clicked` logic).
- Automatically opens the newest log file in the embedded Matplotlib viewer after sync completes.
- Keeps the original **Sync logs from Pi** button behaviour unchanged.

---

## Context

The `OfflineTab` class currently defines three buttons (Refresh, Sync logs from Pi, Browse…) and a `QListWidget` for log files:

```python
top_row = QHBoxLayout()
top_row.addWidget(QLabel("Recent logs:"))
self.btn_refresh = QPushButton("Refresh")
self.btn_sync = QPushButton("Sync logs from Pi")
self.btn_browse = QPushButton("Browse…")
top_row.addWidget(self.btn_refresh)
top_row.addWidget(self.btn_sync)
top_row.addWidget(self.btn_browse)
top_row.addStretch()
layout.addLayout(top_row)

self.file_list = QListWidget(self)
layout.addWidget(self.file_list)
```

Sync logic already exists in `_on_sync_from_pi_clicked` and refreshes the file list via `_populate_files()`. The `_candidate_logs()` helper returns files sorted by modification time in descending order, so the newest log appears first in the list.

---

## Task

1. Add a new `QPushButton` labeled **Sync & open latest** next to the existing **Sync logs from Pi** button.
2. Wire the new button to a slot `_on_sync_and_open_latest_clicked`.
3. Implement `_on_sync_and_open_latest_clicked` so that it:
   - Calls `_on_sync_from_pi_clicked()` to reuse the existing SSH sync implementation and status messages.
   - If the file list is non-empty after sync, selects the first item and opens it via `_on_open_selected()`.
   - Updates the `status_label` with a concise summary (for example, `Synced and opened latest log: <filename>`).

Keep the change local to `OfflineTab` and do not alter the existing sync behaviour.

---

## Step‑by‑step implementation

### 1. Extend the toolbar in `OfflineTab.__init__`

In `src/sensepi/gui/tabs/tab_offline.py`, locate the `__init__` of `OfflineTab` and change the top-row construction to add the new button:

```python
top_row = QHBoxLayout()
top_row.addWidget(QLabel("Recent logs:"))
self.btn_refresh = QPushButton("Refresh")
self.btn_sync = QPushButton("Sync logs from Pi")
self.btn_sync_open = QPushButton("Sync && open latest")
self.btn_browse = QPushButton("Browse…")
top_row.addWidget(self.btn_refresh)
top_row.addWidget(self.btn_sync)
top_row.addWidget(self.btn_sync_open)
top_row.addWidget(self.btn_browse)
top_row.addStretch()
layout.addLayout(top_row)
```

Note the use of `Sync && open latest` so Qt renders a single `&` in the button text.

### 2. Connect the new button signal

Still in `__init__`, update the wiring so the new button is connected to a new slot:

```python
self.btn_refresh.clicked.connect(self._populate_files)
self.btn_browse.clicked.connect(self._on_browse)
self.btn_sync.clicked.connect(self._on_sync_from_pi_clicked)
self.btn_sync_open.clicked.connect(self._on_sync_and_open_latest_clicked)
self.file_list.itemDoubleClicked.connect(self._on_open_selected)
```

### 3. Implement `_on_sync_and_open_latest_clicked`

Add this method to `OfflineTab` (place it near `_on_sync_from_pi_clicked` for clarity):

```python
@Slot()
def _on_sync_and_open_latest_clicked(self) -> None:
    """
    Sync logs from the current Raspberry Pi host and immediately open
    the newest log file in the viewer.

    This reuses the existing SSH sync implementation in
    `_on_sync_from_pi_clicked` and then opens the top entry from the
    refreshed file list (which is already sorted newest‑first).
    """
    # Reuse existing sync logic (handles errors and status messages).
    self._on_sync_from_pi_clicked()

    # After sync, open the newest file if one is available.
    if self.file_list.count() <= 0:
        return

    first_item = self.file_list.item(0)
    if first_item is None:
        return

    # Select the item in the UI and reuse the existing open helper.
    self.file_list.setCurrentItem(first_item)
    self._on_open_selected()

    # Update the status label with a concise summary.
    self.status_label.setText(
        f"Synced and opened latest log: {first_item.text()}"
    )
```

This implementation deliberately reuses the existing sync slot so that:

- All error handling (missing host, missing data directory, SSH failures) stays in one place.
- `_populate_files()` is still called exactly once after a successful sync.
- The new feature is just a small layer on top.

---

## Acceptance criteria

- Clicking **Sync logs from Pi** behaves exactly as before.
- Clicking **Sync & open latest**:
  - Performs the same sync operation to download any new logs.
  - If there are log files in the list afterwards, automatically opens the newest one in the embedded plot.
- No behavioural changes outside `src/sensepi/gui/tabs/tab_offline.py`.
- Type hints, Qt `Slot` decorator usage, and imports remain consistent with the rest of the file.
