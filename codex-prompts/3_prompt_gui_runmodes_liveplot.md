# Final Prompt 3 – Extend the existing Tkinter + SSH GUI (`main.py`) for run modes + live plotting

This prompt assumes you’ve already run:

- `Prompt_1_SSH_GUI_Design.md` and `Prompt_2_SSH_GUI_Implementation.md` (initial GUI with connect/start/stop/download).
- `prompt3_auto_download.md` (auto download at end of each run).
- `prompt4_convenience_features.md` (presets, status bar, validation, “Open local folder”).

So `main.py` already has:

- SSH connect/disconnect (Paramiko).
- Sensor type selection (ADXL vs MPU).
- Parameter fields.
- Start/Stop recording.
- Live log output in a `Text` widget via a background thread + queue.
- **Auto-download** of new files after each run + manual “Download newest files”.
- Preset dropdown + apply, status bar, validation, “Open local folder”.

Now we ONLY want to **extend** this existing app to:

- Use the new logger flags: `--no-record`, `--stream-stdout`, `--stream-every`, `--stream-fields`.
- Add a “run mode” selector (Record only / Record + live plot / Live plot only).
- Parse JSON streaming lines for plotting.
- Add a simple live plot (Matplotlib in Tkinter is fine).

```text
You are extending an existing Tkinter + Paramiko GUI in main.py that already:

- Connects to the Raspberry Pi over SSH.
- Lets me choose ADXL vs MPU6050 and set all logger parameters.
- Starts/stops a remote run.
- Streams stdout/stderr into a log Text widget via a background thread + queue.
- Automatically downloads new log files at the end of each run (using a RemoteRunContext).
- Has presets, a status bar, basic validation, and an “Open local folder” button.

Do NOT remove or break any of that functionality. You are only adding:

- Run mode controls for streaming.
- Command-line flags for `--no-record`, `--stream-stdout`, `--stream-every`, `--stream-fields`.
- JSON parsing and a live plot.

Assume the loggers have been updated as described in the previous prompts (ADXL and MPU6050 now support those flags and emit one JSON object per line on stdout when streaming).
```

---

## 1) Add GUI controls for run mode and stream decimation

In the main window (near the existing controls for starting a run), add:

- A “Run mode” selector, e.g. a `tk.StringVar` + `ttk.Combobox` with three options:
  - `"Record only"`
  - `"Record + live plot"`
  - `"Live plot only (no-record)"`

- A `ttk.Spinbox` or `Entry` for “Stream every Nth sample”, bound to an `IntVar` with default 5 or 10.

Place these in a small “Run mode / Live plot” frame.

Map the run modes to flags when building the command:

- **Record only:**
  - Do **NOT** add any streaming flags.
- **Record + live plot:**
  - Add `--stream-stdout` and `--stream-every N` (from the spinbox).
- **Live plot only:**
  - Add `--no-record --stream-stdout` and `--stream-every N`.

Make this mapping work for BOTH logger types.

---

## 2) Extend command construction for ADXL

When building the command for ADXL in the existing “Start recording” handler, you currently do something like:

```python
cmd = f"python3 {remote_adxl_path} --rate {rate} --channels {channels} --out {remote_out}"
# plus optional duration, map, addr, calibrate, lp-cut, etc.
```

Update this logic to:

```python
cmd_parts = [
    "python3",
    remote_adxl_path,
    "--rate", str(rate),
    "--channels", channels,
    "--out", remote_out,
]
if duration:
    cmd_parts += ["--duration", str(duration)]
# existing options for addr, map, calibrate, lp-cut ...
# (keep your current behavior here)

# Now apply run mode
run_mode = self.run_mode_var.get()  # e.g., "Record only", "Record + live plot", "Live plot only (no-record)"
stream_every = max(1, int(self.stream_every_var.get() or 1))

if run_mode in ("Record + live plot", "Live plot only (no-record)"):
    if run_mode == "Live plot only (no-record)":
        cmd_parts.append("--no-record")
    cmd_parts.append("--stream-stdout")
    cmd_parts += ["--stream-every", str(stream_every)]
    # ADXL streaming focuses on filtered axes
    cmd_parts += ["--stream-fields", "x_lp,y_lp"]

cmd = " ".join(cmd_parts)
```

Keep all existing sanity checks, validation, and logging as they are.

---

## 3) Extend command construction for MPU6050

Similarly, when building the command for `mpu6050_multi_logger.py`, after you’ve added rate, sensors, channels, out, format, etc., append streaming flags based on the same `run_mode` and `stream_every`.

Example:

```python
cmd_parts = [
    "python3",
    remote_mpu_path,
    "--rate", str(rate),
    "--sensors", sensors_str,
    "--channels", channels,
    "--out", remote_out,
    "--format", fmt,
    "--prefix", prefix,
    "--dlpf", str(dlpf),
    # plus duration/samples/temp/flush options...
]

run_mode = self.run_mode_var.get()
stream_every = max(1, int(self.stream_every_var.get() or 1))

if run_mode in ("Record + live plot", "Live plot only (no-record)"):
    if run_mode == "Live plot only (no-record)":
        cmd_parts.append("--no-record")
    cmd_parts.append("--stream-stdout")
    cmd_parts += ["--stream-every", str(stream_every)]
    # For default channels, we care about ax, ay, gz
    cmd_parts += ["--stream-fields", "ax,ay,gz"]

cmd = " ".join(cmd_parts)
```

Again, keep all existing behavior for other flags intact.

---

## 4) Parse streaming JSON lines in the SSH stdout reader

In your SSH reading thread (the one that currently reads stdout from Paramiko and pushes lines onto a log queue), add a second queue for plotting:

```python
import json
import queue

self.plot_queue = queue.Queue()
```

Modify the reader loop to always forward lines to the log, and additionally try to parse them as JSON:

```python
def _stdout_reader_thread(self, channel):
    # channel is a Paramiko Channel or file-like stdout
    for raw_line in iter(channel.readline, ""):
        line = raw_line.rstrip("\n")
        # Always send to the GUI log (via the existing log queue mechanism)
        self.log_queue.put(line)

        # Try to parse JSON streaming objects
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and "timestamp_ns" in obj:
                # Push numeric streaming objects into plot queue
                self.plot_queue.put(obj)
        except json.JSONDecodeError:
            # Not JSON, just plain log line
            continue
```

Don’t break your existing use of `log_queue` and UI updates; just add `plot_queue` alongside it.

---

## 5) Add a Matplotlib live plot in Tkinter

Use Matplotlib + `FigureCanvasTkAgg` (since you’re already in Tkinter) to embed a simple plot:

- Create a `Figure` and `Axes` in a dedicated frame.
- Add one `Line2D` object that you will update in place.

Maintain rolling buffers (e.g. `deque`s) in the App class, for example:

```python
from collections import deque

self.plot_time = deque(maxlen=2000)
self.plot_value = deque(maxlen=2000)
self.first_ts_ns = None  # to compute relative time
```

Add an update function that runs in the Tkinter thread using `root.after`:

```python
def _update_plot(self):
    # Drain plot_queue
    try:
        while True:
            obj = self.plot_queue.get_nowait()
            ts_ns = obj.get("timestamp_ns")
            if ts_ns is None:
                continue

            # Compute relative time
            if self.first_ts_ns is None:
                self.first_ts_ns = ts_ns
            t_s = (ts_ns - self.first_ts_ns) / 1e9

            # Choose which field to show, depending on current sensor type
            sensor_type = self.current_sensor_type  # "adxl" or "mpu"
            if sensor_type == "adxl":
                value = obj.get("x_lp")
            else:
                # For MPU, default to ax (assuming --stream-fields ax,ay,gz)
                value = obj.get("ax")

            if value is None:
                continue

            self.plot_time.append(t_s)
            self.plot_value.append(value)
    except queue.Empty:
        pass

    # Update Matplotlib line
    if self.plot_time:
        self.line.set_data(list(self.plot_time), list(self.plot_value))
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw_idle()

    # Schedule next update
    self.root.after(50, self._update_plot)
```

Call `_update_plot()` once after setting up the GUI to start the loop.

When each run starts:

- Clear `self.plot_time`, `self.plot_value`, and `self.first_ts_ns`.
- Set `self.current_sensor_type` appropriately (`"adxl"` or `"mpu"`).

---

## 6) Respect existing auto-download, presets, status bar, etc.

- Do **NOT** touch the `RemoteRunContext` and auto-download workflow from `prompt3_auto_download`.
- Keep presets, status bar variables, validation, and “Open local folder” button from `prompt4_convenience_features` intact.
- Only extend:
  - The command-building logic (to include streaming flags based on run mode).
  - The SSH reader thread (to push JSON objects into `plot_queue` in addition to `log_queue`).
  - The GUI layout (add run mode selector, N spinbox, and Matplotlib canvas).
  - The periodic `_update_plot` method.

At the end, the GUI must still be able to:

- Connect/disconnect over SSH.
- Start/stop recording.
- Auto-download new files.
- Use presets, show status, and open the local folder.
- **Plus** optionally stream and plot data live, either while recording or in stream‑only mode.
