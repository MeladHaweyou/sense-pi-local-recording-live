# SensePi Docs – Add a “Download logs from the Pi” workflow section to README

You are an AI pair-programmer working on the SensePi repository.

**Goal:** Extend the project’s README with a short, step‑by‑step section that explains how to:

1. Start a recording on the Raspberry Pi from the GUI.
2. Download those logs onto the desktop using the Offline tab.
3. Open the newest log for offline inspection.

This should tie together the Signals/Settings and Offline tabs for students so the “record → download → inspect” story is clear.

---

## Context

The README already describes:

- How to launch the GUI (e.g. via `python -m sensepi.gui` or `sensepi-gui`).
- The high‑level GUI layout (Signals, FFT, Settings, Offline, Logs tabs).
- The architecture (Raspberry Pi logger + desktop GUI).

However, there is no explicit “recipe” showing a student how to go from “click Start” to “see my recorded log offline”.

We have just added or clarified GUI features such as:

- A clearer **Offline logs** tab label.
- Improved hints in the Signals tab about where data is written on the Pi.
- Optional **Sync & open latest** behaviour in the Offline tab.

The README should now include a concise “Download logs from the Pi” section that references these elements.

---

## Task

Update `README.md` to add a new section (or subsection) titled something like:

> `## Download logs from the Pi`

The section should:

1. Assume the student already has a Pi host configured in the Settings tab (hosts.yaml etc.).
2. Walk through the workflow using the GUI vocabulary:

   - **Signals tab** – start a recording.
   - **Settings tab** – where hosts and sensor defaults are configured (only briefly referenced).
   - **Offline logs tab** – where to sync and open log files.

3. Mention the new “Sync logs from Pi” (and optionally “Sync & open latest”) actions by their exact button labels so learners can recognise them in the UI.

---

## Suggested README text (edit as needed)

Append this section near the existing GUI overview:

```markdown
## Download logs from the Pi

A common workflow in SensePi is:

1. **Configure your Raspberry Pi host**  
   Open the **Settings** tab and make sure your Pi appears under *Raspberry Pi hosts* with a valid
   `host`, `user`, `base_path` and `data_dir`. Use the **Sync config to Pi** button to push the
   current sampling settings if needed.

2. **Start a recording from the Signals tab**  
   Go to the **Signals** tab, select your Pi host, choose a sample rate, and tick the **Recording**
   checkbox. Optionally enter a *Session name* to label the run. Press **Start**.  
   The hint text under the buttons will tell you which directory on the Pi the data is being written to.

3. **Stop the recording**  
   Press **Stop** when you’re done. The main window status bar will remind you where the logs were
   saved on the Pi and point you to the **Offline logs** tab.

4. **Download logs to your desktop**  
   Switch to the **Offline logs** tab. Click **Sync logs from Pi** to download any new `.csv` or
   `.jsonl` files from the Pi’s data directory into your local `data/raw` folder.  
   If you prefer a shortcut, you can use **Sync & open latest** to download and immediately open the
   newest log from that host.

5. **Inspect the recording offline**  
   Use the *Offline log files* list to pick a file and double‑click it, or rely on **Sync & open latest**
   to select it for you. The embedded Matplotlib viewer will render acceleration/gyro traces using the
   same conventions as the live Signals tab.
```

Keep the wording consistent with the actual tab labels and button texts in the GUI. It is fine to shorten or slightly rephrase the bullets as long as all three phases—**record**, **sync**, **inspect**—are clearly described.

---

## Acceptance criteria

- `README.md` contains a dedicated section documenting the “record on Pi → download logs → inspect offline” workflow.
- The section uses the exact GUI terminology (tab names and button labels) used in the code.
- No existing README content is removed; only additive changes are made.
