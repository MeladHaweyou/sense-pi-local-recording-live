# Prompt: Clarify PC vs Pi roles in README and add lightweight architecture overview

You are an AI coding assistant working on an existing Python project called **sensepi**.
Your task is to update the documentation so that the roles of the **desktop GUI** and the **Pi logger**
are clearly described for new contributors.

The goal is **clarity and integration**, not a big rewrite.

---

## Project context (high level)

The repo has roughly this structure (for context only):

- `sensepi/gui/`
  - `main_window.py` – main Qt window and tab wiring
  - `tabs/`
    - `tab_recorder.py` – controls remote Pi loggers
    - `tab_signals.py` – live time‑domain plots
    - `tab_fft.py` – live FFT plots
    - `tab_offline.py` – offline log browser
- `sensepi/remote/pi_recorder.py` – starts / stops loggers on the Pi
- `raspberrypi_scripts/` – Pi‑side logging scripts and `pi_config.yaml`
- `docs/` – rendered documentation
- `README.md` – root README you will modify

The architecture is essentially:

- A **desktop GUI** running on a PC/laptop (“host”).
- One or more **Raspberry Pi** units running sensor logger scripts.
- Communication over SSH/SFTP, plus local viewing and offline analysis.

---

## What you should implement

Update **`README.md`** so that a new contributor immediately understands
what runs on the **PC** vs what runs on the **Pi**, and how they talk.

Implement the following:

1. **Add a short "Architecture & Roles" section** near the top of `README.md`,
   ideally after any short project intro.

   It should contain **both**:
   - A compact bullet list
   - And a tiny ASCII or Mermaid diagram (your choice, but keep it simple)

   The bullet list should communicate roughly this content (you can rephrase):

   ```text
   Desktop GUI
   - Starts/stops Pi loggers over SSH
   - Displays live time-domain and FFT plots
   - Syncs sensor defaults -> pi_config.yaml on the Pi
   - Downloads / views offline logs

   Raspberry Pi logger
   - Runs local CSV/JSONL logging scripts
   - Streams JSON lines over stdout to the desktop (document the protocol)
   ```

   If you choose Mermaid, use a fenced code block like:

   ```markdown
   ```mermaid
   flowchart LR
     PC[Desktop GUI] <--> Pi[Pi logger]
     PC -->|SSH/SFTP| Pi
     Pi -->|JSON lines over stdout| PC
   ```
   ```

   Make sure GitHub can render it reasonably.

2. **Link to the JSON streaming protocol doc**

   Somewhere in that section, add a sentence linking to the existing protocol documentation
   (for example, a `docs/json_protocol.md` or similar file, if present in the repo).
   If there is no dedicated file, add a short note pointing to where the protocol is defined
   in the code (e.g. which module parses JSON lines).

   Example phrasing (adjust to actual paths):
   > The JSON streaming format is documented in `docs/json_protocol.md`.

3. **Clarify where configuration files live**

   Briefly explain in the README:
   - Where `hosts.yaml` and `sensors.yaml` live on the PC side.
   - Where `pi_config.yaml` lives on the Pi.
   - That the GUI can push sensor defaults from the host to `pi_config.yaml` on the Pi.

   Keep it **one short paragraph**, designed for a newcomer who just cloned the repo.

4. **Do NOT change code in this task**

   This prompt is docs‑only:
   - Do not modify any `.py` files.
   - Only update `README.md` and, if absolutely necessary, small cross‑links from other
     Markdown docs (for example to point to the new Architecture section).

---

## Coding & style constraints

- Keep the README changes **short and skimmable**.
- Use plain Markdown, no heavy formatting.
- Prefer neutral, technical language (aimed at developers).
- Ensure that headings and links render correctly on GitHub.

---

## Deliverable

- A patch or set of edits that:
  - Adds a clearly titled "Architecture & Roles" (or similar) section
  - Explains PC vs Pi responsibilities
  - Points to the JSON streaming protocol
  - Mentions where the key config files live
- No functional changes to the Python code base.
