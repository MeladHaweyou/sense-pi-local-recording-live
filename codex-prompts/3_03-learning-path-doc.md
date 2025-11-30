# Prompt: Add `docs/LEARNING_PATH.md` with student milestones

You are working in the SensePi repository. Your task is to create a **learning path document** aimed at students who are new to the codebase.

Goal: add a new markdown file `docs/LEARNING_PATH.md` that describes a sequence of milestones, each with:

- A short description of the goal.
- Files to read (in order).
- A small hands-on task achievable with local edits.

Do **not** add new features – all tasks should be based on existing code and configs.

---

## Step 1 – Create `docs/LEARNING_PATH.md`

Create a new file at:

- `docs/LEARNING_PATH.md`

Use the following structure as a starting point (you can refine wording, but keep the overall flow and headings):

```markdown
# SensePi Learning Path

This guide walks you through the SensePi codebase in small, hands-on steps.
Each milestone includes:
- Files to read (in order).
- A small change to make.
- What you should observe after the change.

## Milestone 1 – Get oriented: main window and tabs

**Goal:** See how the GUI starts and where tabs are created.

**Read:**
1. `main.py` (or the CLI entrypoint)
2. `src/sensepi/gui/main_window.py` – especially the `MainWindow` class.

**Task:**
- Change the window title (e.g. from `SensePi` to `SensePi – My Test`) in `MainWindow.__init__`.
- Run the GUI and confirm the new title appears.

---

## Milestone 2 – Connecting to the Raspberry Pi

**Goal:** Understand how Pi hosts are configured and shown in the GUI.

**Read:**
1. `src/sensepi/config/hosts.yaml`
2. `src/sensepi/config/app_config.py` (or wherever hosts are loaded)
3. `src/sensepi/gui/tabs/tab_recorder.py` – the host combo box.

**Task:**
- Add a new fake host entry to `hosts.yaml` (e.g. `name: MyTestPi`).
- Run the GUI and confirm the new host appears in the host selector.

---

## Milestone 3 – Sensor settings and defaults

**Goal:** See how default sensor options are configured.

**Read:**
1. `src/sensepi/config/sensors.yaml`
2. `src/sensepi/gui/tabs/tab_recorder.py` – the MPU6050 settings group.
3. `src/sensepi/gui/tabs/tab_settings.py` – the Settings tab editor.

**Task:**
- Change a default (e.g. the default sensor IDs text) in the Recorder tab code.
- Run the GUI and confirm the new default appears.

---

## Milestone 4 – From Start button to Pi script

**Goal:** Trace what happens when you press “Start”.

**Read:**
1. `src/sensepi/gui/tabs/tab_signals.py` – `_on_start_clicked` (or similar).
2. `src/sensepi/gui/main_window.py` – where `start_stream_requested` is connected.
3. `src/sensepi/remote/pi_recorder.py` – where the Pi logging script is launched.

**Task:**
- Add a `print("Start clicked")` in the start handler in `tab_signals.py`.
- Run the GUI from a terminal, press Start, and confirm the message is printed.

---

## Milestone 5 – Live data pipeline and plotting

**Goal:** Understand how incoming samples reach the live plot.

**Read:**
1. `src/sensepi/remote/sensor_ingest_worker.py` – where data is read from the Pi.
2. `src/sensepi/core` buffer classes (e.g. `ringbuffer.py` or `stream_buffer.py`).
3. `src/sensepi/gui/tabs/tab_signals.py` – the method that drains samples and updates the plot.

**Task:**
- In the “drain samples” method, add a debug print showing how many samples were processed each call.
- Run the GUI and watch the terminal to see sample counts appear.

---

## Milestone 6 – Sampling rate and decimation

**Goal:** See how sampling and “stream every Nth sample” are configured.

**Read:**
1. `src/sensepi/gui/widgets/acquisition_settings.py` (or equivalent).
2. `src/sensepi/config/sampling.py` or similar config helpers.

**Task:**
- Change the default “stream every Nth sample” value (e.g. from 5 to 1).
- Run the GUI and confirm the GUI’s effective stream rate label updates accordingly.

---

## Milestone 7 – Performance HUD and refresh modes

**Goal:** Explore performance tuning and the HUD overlay.

**Read:**
1. `src/sensepi/gui/main_window.py` – menu/action that toggles the performance HUD.
2. `src/sensepi/gui/tabs/tab_signals.py` – where the perf HUD label is created and updated.

**Task:**
- Enable the performance HUD by default (set the corresponding QAction’s checked state to True).
- Run the GUI, start streaming, and confirm the HUD appears on the plot.

---

## Milestone 8 – Recording and offline logs

**Goal:** Understand how data is recorded and replayed.

**Read:**
1. `src/sensepi/dataio/csv_writer.py` (or other writer module).
2. `src/sensepi/gui/tabs/tab_offline.py` – offline/recordings tab.

**Task:**
- Run a short recording (with recording enabled).
- Use the Recordings tab to open the new file and verify the data appears.
- Optionally, add a `print("Loaded:", path)` in the Offline tab to confirm which file is loaded.

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
- For each package, write a one-sentence summary in your own notes.
- (Optional) Sketch a small diagram showing how GUI → Remote → Core → DataIO → Analysis fit together.
```

You may adjust filenames if they differ slightly in the actual repo, but keep the **milestone structure** and the “Read / Task” pattern.

---

## Step 2 – Link the learning path from existing docs

If there is an existing docs index, README, or `docs/AI_AGENT_NOTES.md`, add a short link to the new learning path, e.g.:

```markdown
See [docs/LEARNING_PATH.md](./LEARNING_PATH.md) for a step-by-step tour of the codebase aimed at new students.
```

Place this in a sensible place (e.g. near “Getting Started” or “Architecture overview”).

---

## Step 3 – Sanity check

- Ensure `docs/LEARNING_PATH.md` renders correctly in a Markdown viewer.
- Ensure all referenced paths exist (or adjust them to the actual file layout).
- Keep all changes additive and documentation-only; **do not modify behaviour**.
