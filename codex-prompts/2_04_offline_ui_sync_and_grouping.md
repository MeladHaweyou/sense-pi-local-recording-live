    # SensePi Implementation Prompt 4 – Offline UI: Sync Guidance & Session Feedback

    This prompt focuses on the **Offline tab UI** so that students clearly
    understand the “Record → Sync → Open” workflow, and receive better feedback
    about which session/host they just synced from.

    You will **not** add large new features; instead, you will:
    - Improve labels and help text.
    - Show concise sync status messages.
    - (Optionally) tweak the file list to make newly downloaded files obvious.

    ---

    ## Goal

    - Make the Offline tab self-explanatory:
      1. You record on the Pi from the Recorder tab.
      2. You click “Sync from Pi” to download logs.
      3. You select a file and click “Open” to view it.

    - After sync, show a message like:
      - `Synced 3 log file(s) for session 'trial1'.`
      - or `Synced 2 log file(s) from host 'mypi'.`

    - Ensure this message uses the same session/host info as implemented in
      Prompt 3.

    ---

    ## Where to work

    Primarily in:

    - `src/sensepi/gui/tab_offline.py` (or equivalent Offline tab module).

    Look for:

    - The Offline tab class (e.g. `class TabOffline(QWidget):`).
    - The sync button signal (e.g. `self.sync_button.clicked.connect(...)`).
    - A status label or log display in the Offline tab.

    ---

    ## Step 1 – Add a short “how-to” label

    In the Offline tab’s UI setup (probably inside `__init__` or a private
    `_build_ui` method), add a small, non-intrusive label that explains the
    steps. For example:

    ```python
    # Inside TabOffline._build_ui or equivalent

    self.help_label = QLabel(
        "Offline workflow:
"
        "1. Record data on the Pi using the Recorder tab.
"
        "2. Click 'Sync from Pi' to download new log files.
"
        "3. Select a log file below and click 'Open' to view it."
    )
    self.help_label.setWordWrap(True)
    layout.addWidget(self.help_label)
    ```

    - Place it above the sync button or file list so students see it first.
    - Adjust the text to match your actual button names/labels.

    ---

    ## Step 2 – Use improved sync status messages

    In Prompt 3 you added logic to compute `num_downloaded`, `remote_session_name`
    and `host_slug` during sync. Now, wire that information into a status label.

    Find the code that currently sets the status message at the end of a sync
    (e.g. something like `self.status_label.setText("Sync completed")`). Replace
    or extend it with:

    ```python
    # After sync logic completes...
    if num_downloaded:
        if remote_session_name:
            msg = f"Synced {num_downloaded} log file(s) for session '{remote_session_name}'."
        else:
            msg = f"Synced {num_downloaded} log file(s) from host '{host_slug}'."
    else:
        msg = "No new log files to sync."

    self.status_label.setText(msg)
    ```

    Make sure `self.status_label` is defined in your UI build, for example:

    ```python
    self.status_label = QLabel("No logs synced yet.")
    layout.addWidget(self.status_label)
    ```

    If you already have such a label, reuse it.

    ---

    ## Step 3 – Highlight newly downloaded files (optional but helpful)

    After a successful sync, newly added file paths will be known (e.g. a list
    returned by your sync function). If your Offline file list is a `QListWidget`
    or `QTableView`, you can:

    - Refresh the file list to include the new files.
    - Optionally, auto-select the first newly added item.

    Example (assuming a simple `QListWidget`):

    ```python
    # Suppose new_files is a list of pathlib.Path objects that were just downloaded
    self.file_list_widget.clear()
    for path in sorted(all_local_log_files):
        item = QListWidgetItem(path.name)
        item.setData(Qt.UserRole, str(path))
        self.file_list_widget.addItem(item)

    # Auto-select the first of the newly downloaded paths, if any
    for i in range(self.file_list_widget.count()):
        item = self.file_list_widget.item(i)
        if Path(item.data(Qt.UserRole)) in new_files:
            self.file_list_widget.setCurrentRow(i)
            break
    ```

    Adjust this to your actual widget type and data model. If this feels too
    invasive, you can skip auto-selection and simply rely on the improved status
    text from Step 2.

    ---

    ## Step 4 – Docstrings and comments

    Add short docstrings or inline comments in the sync method to clarify the
    intended student workflow. For example:

    ```python
    def _on_sync_from_pi_clicked(self) -> None:
        """Download any new log files from the selected Pi into data/raw.

        This is step 2 of the offline workflow:
        1. Record on the Pi via the Recorder tab.
        2. Sync logs from the Pi (this method).
        3. Open downloaded logs for offline plotting.
        """
        # existing sync logic...
    ```

    This reinforces the concepts both in the code and in the UI.

    ---

    ## Testing

    1. Start the GUI and navigate to the Offline tab.
    2. Confirm the help text appears and is readable.
    3. Record a session on the Pi, then click “Sync from Pi”:
       - Status label should show `Synced N log file(s) for session '...'.`
       - File list should be updated; newly downloaded files should be visible.
    4. Sync again without new recordings:
       - Status label should say `No new log files to sync.`

    Once this is working, students should find the offline workflow much more
    intuitive.
