# Prompt: Wire host updates into RecorderTab and unify error handling

You are an AI coding assistant working on the **sensepi** project.
Your task is to improve how **host configuration updates** and **error reporting**
propagate through the Qt GUI.

Focus on **integration work** in the existing `MainWindow`, `SettingsTab`, and `RecorderTab`.

---

## Context: relevant pieces

- `sensepi/gui/main_window.py`
- `sensepi/gui/tabs/tab_settings.py`
- `sensepi/gui/tabs/tab_recorder.py`
- `sensepi/gui/tabs/tab_signals.py`

### Main window wiring (simplified)

```python
class MainWindow(QMainWindow):
    def __init__(self, app_config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        ...
        self.settings_tab = SettingsTab(app_config=app_config)
        self.recorder_tab = RecorderTab(app_config=app_config)
        self.signals_tab = SignalsTab(app_config=app_config)
        ...

        # signals/slots wiring
        self.settings_tab.sensorsUpdated.connect(
            self.recorder_tab.on_sensors_updated
        )

        self.recorder_tab.sample_received.connect(
            self.signals_tab.on_sample_received
        )
        self.recorder_tab.stream_started.connect(
            self.signals_tab.on_stream_started
        )
        self.recorder_tab.stream_stopped.connect(
            self.signals_tab.on_stream_stopped
        )
        self.recorder_tab.error_reported.connect(
            self.signals_tab.handle_error
        )
```

Note that **hostsUpdated** from `SettingsTab` is **not** connected anywhere yet.

### SettingsTab emits hostsUpdated

```python
class SettingsTab(QWidget):
    hostsUpdated = Signal(list)   # list[dict]
    sensorsUpdated = Signal(list) # list[dict]

    def _on_save_hosts_clicked(self) -> None:
        ...
        # after writing hosts.yaml
        self.hostsUpdated.emit(host_dicts)
```

### RecorderTab currently loads hosts only on init

```python
class RecorderTab(QWidget):
    def __init__(self, app_config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self._hosts: dict[str, HostConfig] = {}
        self._host_combo = QComboBox()
        ...
        self._load_hosts()

    def _load_hosts(self) -> None:
        self._hosts.clear()
        self._host_combo.clear()
        inventory = self._app_config.host_inventory
        for host in inventory.iter_hosts():
            self._hosts[host.name] = host
            self._host_combo.addItem(host.name)
```

Error handling in `MainWindow` still has some `print` calls:

```python
class MainWindow(QMainWindow):
    ...

    def _on_start_stream_requested(self):
        try:
            self.recorder_tab.start_stream()
        except Exception as exc:
            print(f"Failed to start stream: {exc!r}")

    def _on_stop_stream_requested(self):
        try:
            self.recorder_tab.stop_stream()
        except Exception as exc:
            print(f"Failed to stop stream: {exc!r}")
```

We already have a central error pipeline via `RecorderTab.error_reported` → `SignalsTab.handle_error`.

---

## What you must implement

### 1. Wire host updates from SettingsTab into RecorderTab

1. Add a new slot method to `RecorderTab`:

   ```python
   def on_hosts_updated(self, host_list: list[dict]) -> None:
       """Update internal hosts mapping and host combo when SettingsTab saves hosts."""
       ...
   ```

   Implement it to:

   - Rebuild `self._hosts` from the provided `host_list`.
   - Repopulate `self._host_combo` with the new host names.
   - Try to preserve the currently selected host **by name** if it still exists.
   - If the previously selected host no longer exists, select the first host (if any).

   You can reuse the structure used by `HostInventory` (e.g. fields like `name`, `hostname`, `port`, `username`)
   to rebuild `HostConfig` objects as needed.

   Example sketch (adjust to actual types and imports):

   ```python
   def on_hosts_updated(self, host_list: list[dict]) -> None:
       current_name = self._host_combo.currentText() if self._host_combo.count() else None

       self._hosts.clear()
       self._host_combo.clear()

       for host_dict in host_list:
           host_cfg = HostConfig.from_dict(host_dict)  # or equivalent constructor
           self._hosts[host_cfg.name] = host_cfg
           self._host_combo.addItem(host_cfg.name)

       if current_name and current_name in self._hosts:
           index = self._host_combo.findText(current_name)
           if index >= 0:
               self._host_combo.setCurrentIndex(index)
       elif self._host_combo.count():
           self._host_combo.setCurrentIndex(0)
   ```

2. In `MainWindow.__init__`, connect `hostsUpdated` to this slot:

   ```python
   self.settings_tab.hostsUpdated.connect(
       self.recorder_tab.on_hosts_updated
   )
   ```

   Place this next to the existing `sensorsUpdated` connection for consistency.

### 2. Unify error handling: remove direct print calls

Replace `print`‑based error handling in `MainWindow` with the existing
**error_reported** signal from `RecorderTab`.

1. In `_on_start_stream_requested` and `_on_stop_stream_requested`:

   - Catch exceptions.
   - Instead of `print`, emit a user‑visible error via `RecorderTab.error_reported` (which is already
     connected to `SignalsTab.handle_error`).

   Example:

   ```python
   def _on_start_stream_requested(self):
       try:
           self.recorder_tab.start_stream()
       except Exception as exc:
           self.recorder_tab.error_reported.emit(
               f"Failed to start stream: {exc!r}"
           )
   ```

   and similarly for `_on_stop_stream_requested`.

2. Ensure `SignalsTab.handle_error` still receives all error messages from:
   - `RecorderTab` internal failures
   - Remote stderr callbacks
   - These `MainWindow` start/stop exceptions

   You do **not** need to change `SignalsTab.handle_error` itself.

3. (Optional but nice) If the application already has a status bar or message‑box mechanism,
   consider updating `SignalsTab.handle_error` to also post a message to the status bar.
   This is optional; keep changes focused if it would require a lot of refactoring.

---

## Behaviour expectations

After your changes:

- Editing hosts in **Settings** and clicking **Save** should immediately update the host combo
  in **Recorder** without restarting the app.
- The previously selected host should remain selected when possible.
- If starting or stopping a stream fails, the user sees the error through the existing error UI
  (Signals tab / log area), with no raw `print` output required.

---

## Constraints & style

- Do not introduce new dependencies.
- Keep API changes minimal; use existing signals and patterns.
- Maintain type hints and follow the surrounding code style (PEP 8, f‑strings, etc.).
