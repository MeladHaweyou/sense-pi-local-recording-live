# Prompt: Implement GUI tab re-organisation for SensePi

You are an assistant working **inside the SensePi repository**. Your task is to **reorganise and rename the main GUI tabs** so the workflow is clearer for first-time students, *without changing behaviour*.

Focus on:
- `src/sensepi/gui/main_window.py`
- `src/sensepi/gui/tabs/tab_recorder.py`
- `src/sensepi/gui/tabs/tab_signals.py`
- `src/sensepi/gui/tabs/tab_fft.py`
- `src/sensepi/gui/tabs/tab_offline.py`
- `src/sensepi/gui/tabs/tab_settings.py`
- `src/sensepi/gui/tabs/tab_logs.py`

The main goals:

1. Make the **RecorderTab** visible as the first tab, labeled **“Device”** (or similar).
2. Rename and reorder the existing tabs to match this approximate workflow:

   1. Device (connect to Pi)
   2. Sensors & Rates (configure sensors and default sampling)
   3. Live Signals (time‑domain view and recording controls)
   4. Spectrum (FFT/frequency view)
   5. Recordings (offline log viewer)
   6. App Logs (text logs / debug output)

3. Remove the pattern where `SignalsTab` “steals” controls from `RecorderTab` (via an `attach_recorder_controls(...)` call) – RecorderTab should own and display its own widgets in the **Device** tab.
4. Do **not** change core behaviour: starting/stopping streaming, recording, and plotting must still work exactly as before.

---

## Step 1 – Make RecorderTab a visible “Device” tab

Open `src/sensepi/gui/main_window.py`.

You should find something like this when the tabs are created (names may differ slightly):

```python
# Somewhere in MainWindow.__init__
self.recorder_tab = RecorderTab(app_config=self._app_config, parent=self)
self.signals_tab = SignalsTab(app_config=self._app_config, parent=self)
self.fft_tab = FftTab(app_config=self._app_config, parent=self)
self.offline_tab = OfflineTab(app_config=self._app_config, parent=self)
self.settings_tab = SettingsTab(app_config=self._app_config, parent=self)
self.logs_tab = LogsTab(app_config=self._app_config, parent=self)

# Previous tab order
self._tabs.addTab(self.signals_tab, self.tr("Signals"))
self._tabs.addTab(self.fft_tab, self.tr("FFT"))
self._tabs.addTab(self.offline_tab, self.tr("Offline"))
self._tabs.addTab(self.settings_tab, self.tr("Settings"))
self._tabs.addTab(self.logs_tab, self.tr("Logs"))
```

**Change the tab order and labels** to:

```python
# New tab order & labels
self._tabs.addTab(self.recorder_tab, self.tr("Device"))
self._tabs.addTab(self.settings_tab, self.tr("Sensors && Rates"))
self._tabs.addTab(self.signals_tab, self.tr("Live Signals"))
self._tabs.addTab(self.fft_tab, self.tr("Spectrum"))
self._tabs.addTab(self.offline_tab, self.tr("Recordings"))
self._tabs.addTab(self.logs_tab, self.tr("App Logs"))
```

Notes:

- Use `self.tr(...)` consistently for translatable strings, matching existing style.
- `"Sensors && Rates"` uses `&&` so Qt will show a literal `&` in the UI.

---

## Step 2 – Stop injecting Recorder controls into SignalsTab

Previously, the Signals tab took over some RecorderTab widgets (host/sensor settings) via a helper like:

```python
# In MainWindow.__init__ or similar
self.signals_tab.attach_recorder_controls(self.recorder_tab)
```

or inside `SignalsTab.__init__` itself.

**Remove this behaviour** so that:

- `RecorderTab` fully owns the “Device”/connection UI and is displayed in its own tab.
- `SignalsTab` only owns the **live plotting / recording controls**, not Pi host/sensor configuration group boxes.

Concretely:

1. **Delete** the call to `attach_recorder_controls(...)` wherever it lives.
2. In `src/sensepi/gui/tabs/tab_signals.py`, remove any code that:
   - Takes `QGroupBox`es or layouts from `RecorderTab` and adds them into the Signals tab.
   - Assumes the RecorderTab widgets live inside the Signals UI.

If there is a method like:

```python
def attach_recorder_controls(self, recorder_tab: RecorderTab) -> None:
    # moves or re-parents widgets out of RecorderTab
    ...
```

either:

- Remove it entirely, and delete its call sites, **or**
- Leave it as a no-op (with a comment explaining it’s kept for backwards compatibility but not used any more).

Example transformation:

```python
# BEFORE – in MainWindow.__init__
self.signals_tab.attach_recorder_controls(self.recorder_tab)

# AFTER – remove entirely
# RecorderTab now shows its own controls in the "Device" tab.
```

Make sure that the **RecorderTab still works** in isolation (you should still be able to change host, sensor IDs, etc. in the Device tab).

---

## Step 3 – Rename tabs and tweak wording

Make sure tab labels match the new names:

- `"Device"` – RecorderTab
- `"Sensors && Rates"` – SettingsTab (same underlying class, new label)
- `"Live Signals"` – SignalsTab
- `"Spectrum"` – FftTab
- `"Recordings"` – OfflineTab
- `"App Logs"` – LogsTab

If there are any references to tab names in status messages or tooltips (e.g. “See the Offline tab”), update them for clarity, but **don’t change behaviour**.

---

## Step 4 – Sanity checks

After changes:

1. Run the GUI (whatever the usual entry point is, e.g. `python -m sensepi.gui` or `sensepi-gui`).
2. Verify manually that you can:
   - Select a Pi in the **Device** tab.
   - Adjust sensor IDs and other settings (where they already existed).
   - Switch to **Live Signals** and start a stream.
   - See data in **Live Signals** and **Spectrum**.
   - Open a recorded file in **Recordings**.
   - View application logs in **App Logs**.
3. Confirm there are **no regressions** in start/stop, logging, or plotting.

Do **not** introduce new functionality. This change is purely about *renaming and rearranging* existing widgets so they match the student workflow better.
