# SensePi Learning Path

This guide walks you through the SensePi codebase in small, hands-on steps.
Each milestone includes:
- Files to read (in order).
- A small change to make.
- What you should observe after the change.

## Milestone 1 – Get oriented: main window and tabs

**Goal:** See how the GUI starts and where tabs are created.

**Read:**
1. `main.py` – notice that it just forwards to `sensepi.gui.application`.
2. `src/sensepi/gui/application.py` – follow how `MainWindow` is constructed.
3. `src/sensepi/gui/main_window.py` – especially the `MainWindow` class that wires the tabs together.

**Task:**
- In `MainWindow.__init__` change `self.setWindowTitle("SensePi Recorder")` to something like `self.setWindowTitle("SensePi – My Test")`.
- Launch the GUI with `python -m sensepi.gui.application` (from the repo root) to confirm you are editing the right entry point.

**Observe:** The title bar of the Qt window should show the new text after the app launches.

---

## Milestone 2 – Connecting to the Raspberry Pi

**Goal:** Understand how Pi hosts are configured and shown in the GUI.

**Read:**
1. `src/sensepi/config/hosts.yaml` – the YAML file that lists known Raspberry Pi hosts under the `pis:` array.
2. `src/sensepi/config/app_config.py` – skim `HostConfig`, `HostInventory`, and how host records are loaded.
3. `src/sensepi/gui/tabs/tab_recorder.py` – the `RecorderTab` host combo box and `_load_hosts`.

**Task:**
- Add a fake host entry to `hosts.yaml`, e.g.:
  ```yaml
  - name: MyTestPi
    host: 192.168.0.123
    user: pi
    password: "changeme"
    base_path: "/home/pi/sensor"
    data_dir: "/home/pi/logs"
    pi_config_path: "/home/pi/sensor/pi_config.yaml"
  ```
- Restart the GUI. Open the **Device** tab and drop down the host selector.

**Observe:** `MyTestPi` (or your chosen name) should appear in the host combo box, confirming that the YAML change was picked up.

---

## Milestone 3 – Sensor settings and defaults

**Goal:** See how default sensor options are configured.

**Read:**
1. `src/sensepi/config/sensors.yaml` – default sampling and per-sensor options.
2. `src/sensepi/gui/tabs/tab_recorder.py` – the "MPU6050 settings" group built inside `_build_ui`.
3. `src/sensepi/gui/tabs/tab_settings.py` – how the Settings tab edits those YAML-backed defaults.

**Task:**
- Change one of the hard-coded defaults in the Recorder tab, e.g. update `self.mpu_sensors_edit = QLineEdit("1,2,3", ...)` so it reads `"1"` instead.
- Run the GUI and switch to the **Device** tab.

**Observe:** The "Sensors" text field should now start with your modified default each time the app launches.

---

## Milestone 4 – From Start button to Pi script

**Goal:** Trace what happens when you press “Start”.

**Read:**
1. `src/sensepi/gui/tabs/tab_signals.py` – the `_on_start_clicked` slot and how it emits `start_stream_requested`.
2. `src/sensepi/gui/main_window.py` – where that signal is connected to `_on_start_stream_requested`, which coordinates the tabs.
3. `src/sensepi/remote/pi_recorder.py` – how the remote logging script is launched over SSH once `_on_start_stream_requested` delegates to `RecorderTab`.

**Task:**
- Add `print("Start clicked")` (or similar) near the top of `_on_start_clicked`.
- Launch the GUI from a terminal, open the **Live Signals** tab, and click **Start**.

**Observe:** The terminal running the GUI should print your message, proving that you have traced the button → signal → start pipeline path.

---

## Milestone 5 – Live data pipeline and plotting

**Goal:** Understand how incoming samples reach the live plot.

**Read:**
1. `src/sensepi/remote/sensor_ingest_worker.py` – how streamed samples are read and pushed into queues.
2. `src/sensepi/core/ringbuffer.py` (and nearby `timeseries_buffer.py`) – how buffers store rolling samples for the GUI.
3. `src/sensepi/gui/tabs/tab_signals.py` – the `_drain_samples` method that periodically consumes queued samples and updates the plot widget.

**Task:**
- Inside `_drain_samples`, after popping a batch from `_sample_queue`, add a debug statement such as `print(f"Drained {len(batch)} samples")`.
- Start a live stream (real Pi or loopback) so samples arrive.

**Observe:** The terminal prints how many samples were processed each timer tick, which helps you correlate ingest frequency with the live plot’s smoothness.

---

## Milestone 6 – Sampling rate and decimation

**Goal:** See how sampling and “stream every Nth sample” are configured.

**Read:**
1. `src/sensepi/gui/widgets/acquisition_settings.py` – how the GUI lets you pick device and refresh rates and displays the effective stream rate.
2. `src/sensepi/config/sampling.py` – the `SamplingConfig`/`RecordingMode` helpers that compute decimation (`stream_decimate`) and `stream_rate_hz`.

**Task:**
- Locate the `RECORDING_MODES` dictionary in `sampling.py`. For the `"high_fidelity"` mode, change `target_stream_hz` from `25.0` to match the device rate (e.g. `200.0`). This effectively changes the default “stream every Nth sample” ratio from 8 down to 1.
- Open the GUI, visit the **Live Signals** tab, and inspect the “GUI stream [Hz]” label in the Sampling box.

**Observe:** The label should show a much higher stream rate (equal to the device rate), confirming that the decimation setting – and thus the “stream every Nth sample” value – was updated.

---

## Milestone 7 – Performance HUD and refresh modes

**Goal:** Explore performance tuning and the HUD overlay.

**Read:**
1. `src/sensepi/gui/main_window.py` – the `QAction` named `_act_show_perf_hud` in the View menu that toggles the overlay.
2. `src/sensepi/gui/tabs/tab_signals.py` – the `_perf_hud_label` and `set_perf_hud_visible` logic that draws live FPS/timing data.

**Task:**
- In `MainWindow.__init__`, change `_act_show_perf_hud.setChecked(False)` to `True` so the HUD starts enabled.
- Run the GUI, start streaming data, and keep the Live Signals tab visible.

**Observe:** The translucent performance HUD should be visible immediately (no menu click required) and update while samples stream.

---

## Milestone 8 – Recording and offline logs

**Goal:** Understand how data is recorded and replayed.

**Read:**
1. `src/sensepi/dataio/csv_writer.py` – how recordings are written to disk and where metadata lives.
2. `src/sensepi/gui/tabs/tab_offline.py` – how the Recordings tab syncs logs over SSH and plots them via `plotter.build_plot_for_file`.

**Task:**
- Run a short recording with recording enabled (Device tab → check “Recording” → Start/Stop).
- Use the **Recordings** tab to click **Sync logs from Pi** and open the newest file.
- (Optional) Add `print(f"Loaded: {path}")` inside `OfflineTab.load_file` to see exactly which path is rendered.

**Observe:** A Matplotlib canvas should appear under the file list showing the recorded data, and (if you added the print) the terminal will log the path you opened.

---

## Milestone 9 – Big-picture architecture

**Goal:** Summarise the role of each top-level package.

**Read:**
1. `src/sensepi/analysis/__init__.py`
2. `src/sensepi/config/__init__.py`
3. `src/sensepi/core/__init__.py`
4. `src/sensepi/data/__init__.py`
5. `src/sensepi/dataio/__init__.py`
6. `src/sensepi/gui/__init__.py`
7. `src/sensepi/remote/__init__.py`
8. `src/sensepi/sensors/__init__.py`
9. `src/sensepi/tools/__init__.py`

**Task:**
- For each package, jot down a one-sentence summary in your own notes describing what code lives there.
- (Optional) Sketch a simple diagram like “GUI → Remote → Core → DataIO → Analysis” to reinforce how data flows through the system.

**Observe:** You should now be able to explain to another student where to look for GUI code, SSH/streaming helpers, buffering, and offline analysis utilities.
