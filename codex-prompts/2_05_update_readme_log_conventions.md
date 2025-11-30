# SensePi Implementation Prompt 5 – README: Log Conventions & Decimation

This prompt is about **documentation**, not code changes. You will update
`README.md` (and optionally a student-facing doc like `docs/AI_AGENT_NOTES.md`)
so that the log directory, file naming conventions, and decimation behaviour
are clear to beginners.

You already implemented helpers and refactors in previous prompts; this
prompt makes those conventions explicit for users.

---

## Goal

- Add a “Log Conventions” section to `README.md` that explains:
  - Where logs live on the Pi.
  - Where logs end up on the PC.
  - How session names, sensor IDs, and timestamps appear in filenames.
  - What `.meta.json` files are and why they matter.
  - How decimation affects sample rate.

- Keep the language student-friendly and concrete, with examples.

---

## Where to work

- `README.md`
- Optionally `docs/AI_AGENT_NOTES.md` and/or `docs/json_protocol.md` if you
  want to cross-link.

---

## Suggested README section (adapt and paste)

Add the following section (you may tweak wording to match the rest of the
README style). Place it near the part where you describe recording and the
Offline tab.

```markdown
## Log Conventions (where your data lives)

SensePi keeps all your raw sensor logs as simple files on disk. This section
explains where they live and how to read their names.

### On the Raspberry Pi

By default, the Pi saves logs under:

- `~/logs` – root for all logs on the Pi
- `~/logs/mpu` – logs from the MPU6050 IMU logger

When you start a recording, you can optionally give it a **session name**
(for example, `Trial1`). If you do, the logger creates a subfolder for that
session:

- `~/logs/mpu/Trial1/` – all files from that recording session

If you leave the session name blank, the files are written directly into
`~/logs/mpu`. Either way, the logger creates **one file per physical sensor**
(e.g. `S1`, `S2`) plus a small metadata file.

### On the PC (after syncing)

When you click **“Sync from Pi”** in the Offline tab, SensePi downloads all
new log files from the Pi into the project’s data folder:

- `data/raw` – root for downloaded logs on your computer

If your recording had a session name (like `Trial1`), the files are grouped
under a session folder:

- `data/raw/trial1/` – all files for that session

If you didn’t provide a session name, logs are grouped by host and sensor
type instead, for example:

- `data/raw/mypi/mpu/` – logs from a Pi host called `mypi`

This structure keeps different experiments and different devices separate,
but everything remains just plain files on disk.

### File name pattern

Each data file has a name like:

```
[<session>_]<sensorPrefix>_S<sensorID>_<timestamp>.<ext>
```

Example:

- `Trial1_mpu_S1_2025-11-30_04-53-33.csv`
- `mpu_S2_2025-11-30_04-53-33.jsonl`

Where:

- `<session>` is your session name, turned into a filesystem-safe “slug”
  (lowercase, spaces replaced with hyphens). If you didn’t provide a session
  name, this part is omitted.
- `<sensorPrefix>` is a short code for the logger; for the IMU it is `mpu`.
- `S<sensorID>` is the sensor index (S1, S2, S3, ...).
- `<timestamp>` is the recording start time in UTC, formatted as
  `YYYY-MM-DD_HH-MM-SS`.
- `<ext>` is the file format: `.csv` or `.jsonl`.

For each data file there is a matching metadata file with a `.meta.json`
suffix, for example:

- `Trial1_mpu_S1_2025-11-30_04-53-33.csv.meta.json`

This metadata sidecar contains the sample rate, which axes were enabled,
and other run settings. The Offline tab uses it to plot data correctly.

### Sample rate and decimation

The MPU6050 can sample at a high device rate (e.g. 200 Hz), but SensePi
often **decimates** this to keep files and live plots manageable.

There are three related rates:

- **Device rate** – how fast the sensor is actually polled on the Pi
  (e.g. 200 Hz).
- **Record rate** – how often a sample is written to the CSV/JSONL file
  (e.g. every 4th sample → 50 Hz in the log).
- **Stream rate** – how often a sample is sent live to the GUI over SSH
  (e.g. every 8th sample → 25 Hz on the live plot).

That means your CSV might have fewer samples per second than the raw
device rate. This is intentional: it trades a tiny loss of resolution for
much smaller files and a smoother live experience.

You can inspect these rates in the config files, and in the `.meta.json`
for each run. The metadata records both the device sample rate and the
effective record/stream rate used during that recording.
```

---

## Integration steps

1. Insert the section above into `README.md` at an appropriate location
   (under a “Recording data” / “Offline analysis” heading).
2. Adjust wording to match your project tone if needed.
3. Optionally add a short pointer from `docs/AI_AGENT_NOTES.md` and
   `docs/json_protocol.md` that says “See README.md → Log Conventions for
   file layout and naming.”
4. Commit the updated docs alongside the code refactors from Prompts 1–4.

After this, new students should be able to read the README and immediately
understand where their data lives and how to find the right files.
