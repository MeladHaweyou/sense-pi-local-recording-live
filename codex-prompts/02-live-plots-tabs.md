# 02-live-plots-tabs.md

# Task: Move live plots to their own tab, show all MPU sensors in an array, and add a time window (x‑limits) control

Same project, same `main.py`.  
Now I want to improve the live plotting:

1. Put live plots on a **separate tab** using a `ttk.Notebook`.
2. For multi‑MPU6050, show **one subplot per sensor (1–3)** stacked vertically.
3. Add a UI control to set a **live time window (seconds)** that controls the Matplotlib x‑limits.

Below are concrete code changes you should implement.

---

## 1. Add per‑sensor plot buffers in `__init__`

In `App.__init__`, replace the current live‑plot state:

```python
self.log_queue: queue.Queue[str] = queue.Queue()
self.plot_queue: queue.Queue = queue.Queue()
self.current_channel: Optional[paramiko.Channel] = None
self.current_run: Optional[RemoteRunContext] = None
self.stop_event = threading.Event()
self.plot_time = deque(maxlen=2000)
self.plot_value = deque(maxlen=2000)
self.first_ts_ns: Optional[int] = None
self.current_sensor_type: Optional[str] = None
```

with:

```python
self.log_queue: queue.Queue[str] = queue.Queue()
self.plot_queue: queue.Queue = queue.Queue()
self.current_channel: Optional[paramiko.Channel] = None
self.current_run: Optional[RemoteRunContext] = None
self.stop_event = threading.Event()

# Live-plot state
self.first_ts_ns: Optional[int] = None
self.current_sensor_type: Optional[str] = None

# Per-sensor buffers for live plotting (sensor_id -> {t: deque, y: deque})
self.plot_buffers = {
    1: {"t": deque(maxlen=2000), "y": deque(maxlen=2000)},
    2: {"t": deque(maxlen=2000), "y": deque(maxlen=2000)},
    3: {"t": deque(maxlen=2000), "y": deque(maxlen=2000)},
}
```

We will no longer use `self.plot_time` / `self.plot_value`.

---

## 2. Add a `live_window_seconds` variable in `_build_vars`

In `_build_vars`, after the sensor choice section is a good place, add:

```python
    # Live plot window (seconds). 0 = show full history.
    self.live_window_seconds = tk.DoubleVar(value=5.0)
```

So `_build_vars` looks conceptually like:

```python
    # Sensor choice
    self.sensor_var = tk.StringVar(value="mpu")
    self.run_mode_var = tk.StringVar(value="Record only")
    self.stream_every_var = tk.IntVar(value=5)

    # Live plot window (seconds). 0 = show full history.
    self.live_window_seconds = tk.DoubleVar(value=5.0)

    # ADXL defaults
    ...
```

---

## 3. Create a `ttk.Notebook` with separate "Live plots" and "Logs" tabs

In `App._build_ui`, replace the current version:

```python
def _build_ui(self) -> None:
    self._build_connection_frame()
    self._build_sensor_frame()
    self._build_presets_frame()
    self._build_controls_frame()
    self._build_download_frame()
    self._build_plot_frame()
    self._build_log_frame()
    self._build_status_bar()
```

with:

```python
def _build_ui(self) -> None:
    self._build_connection_frame()
    self._build_sensor_frame()
    self._build_presets_frame()
    self._build_controls_frame()
    self._build_download_frame()

    # Notebook for separating live plots and logs
    self.notebook = ttk.Notebook(self.root)
    self.notebook.pack(fill="both", expand=True, padx=8, pady=6)

    self.plot_tab = ttk.Frame(self.notebook)
    self.log_tab = ttk.Frame(self.notebook)
    self.notebook.add(self.plot_tab, text="Live plots")
    self.notebook.add(self.log_tab, text="Logs")

    self._build_plot_frame(self.plot_tab)
    self._build_log_frame(self.log_tab)
    self._build_status_bar()
```

We’ll update `_build_plot_frame` and `_build_log_frame` to accept a `parent` argument next.

---

## 4. Refactor `_build_plot_frame` to use a parent and create a subplot array

Replace the current `_build_plot_frame`:

```python
def _build_plot_frame(self) -> None:
    frame = ttk.LabelFrame(self.root, text="Live plot")
    frame.pack(fill="both", expand=True, padx=8, pady=6)
    self.fig = Figure(figsize=(6, 3), dpi=100)
    self.ax = self.fig.add_subplot(111)
    self.ax.set_xlabel("Time (s)")
    self.ax.set_ylabel("Value")
    self.line, = self.ax.plot([], [], lw=1)
    self.canvas = FigureCanvasTkAgg(self.fig, master=frame)
    self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)
    self.canvas.draw_idle()
```

with a new version that:

1. Accepts a `parent`.
2. Adds a “Live window (s)” control row.
3. Creates three stacked subplots (one per sensor) that share the x‑axis.

```python
def _build_plot_frame(self, parent) -> None:
    frame = ttk.LabelFrame(parent, text="Live plots")
    frame.pack(fill="both", expand=True, padx=8, pady=6)

    # Controls for the live time window
    controls = ttk.Frame(frame)
    controls.pack(fill="x", padx=4, pady=2)

    ttk.Label(controls, text="Live window (s):").pack(side="left")
    ttk.Spinbox(
        controls,
        from_=0.0,
        to=3600.0,
        increment=0.5,
        textvariable=self.live_window_seconds,
        width=8,
    ).pack(side="left", padx=4)
    ttk.Label(controls, text="(0 = show full history)").pack(side="left")

    # Figure with 3 stacked subplots (one per sensor ID)
    self.fig = Figure(figsize=(6, 5), dpi=100)
    self.axes = []
    self.lines = {}

    for idx, sid in enumerate((1, 2, 3)):
        if idx == 0:
            ax = self.fig.add_subplot(3, 1, idx + 1)
        else:
            ax = self.fig.add_subplot(3, 1, idx + 1, sharex=self.axes[0])
        ax.set_ylabel(f"S{sid} ax")
        self.axes.append(ax)
        line, = ax.plot([], [], lw=1)
        self.lines[sid] = line

    self.axes[-1].set_xlabel("Time (s)")

    self.canvas = FigureCanvasTkAgg(self.fig, master=frame)
    self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)
    self.canvas.draw_idle()
```

For ADXL mode, we’ll simply use the **sensor 1** subplot to display the single time series and leave the others blank.

---

## 5. Refactor `_build_log_frame` to accept a parent

Replace:

```python
def _build_log_frame(self) -> None:
    frame = ttk.LabelFrame(self.root, text="Remote log output")
    frame.pack(fill="both", expand=True, padx=8, pady=6)
    self.log_text = scrolledtext.Scrolledtext(frame, height=18, wrap="word")
    self.log_text.pack(fill="both", expand=True, padx=4, pady=4)
```

with:

```python
def _build_log_frame(self, parent) -> None:
    frame = ttk.LabelFrame(parent, text="Remote log output")
    frame.pack(fill="both", expand=True, padx=8, pady=6)
    self.log_text = scrolledtext.ScrolledText(frame, height=18, wrap="word")
    self.log_text.pack(fill="both", expand=True, padx=4, pady=4)
```

The rest of the logging logic can stay unchanged.

---

## 6. Update `_reset_plot_state` to clear per‑sensor buffers and lines

Replace the current `_reset_plot_state`:

```python
def _reset_plot_state(self) -> None:
    self.plot_time.clear()
    self.plot_value.clear()
    self.first_ts_ns = None
    self._drain_plot_queue()
    if hasattr(self, "line"):
        self.line.set_data([], [])
        if hasattr(self, "canvas"):
            self.canvas.draw_idle()
```

with:

```python
def _reset_plot_state(self) -> None:
    self.first_ts_ns = None
    self._drain_plot_queue()

    # Clear buffers
    if hasattr(self, "plot_buffers"):
        for buf in self.plot_buffers.values():
            buf["t"].clear()
            buf["y"].clear()

    # Clear plotted lines
    if hasattr(self, "lines"):
        for line in self.lines.values():
            line.set_data([], [])

    if hasattr(self, "canvas"):
        self.canvas.draw_idle()
```

---

## 7. Replace `_update_plot` with a per‑sensor, windowed implementation

Completely replace the existing `_update_plot` with this version:

```python
def _update_plot(self) -> None:
    # 1) Drain queued JSON objects from the logger
    try:
        while True:
            obj = self.plot_queue.get_nowait()

            ts_ns = obj.get("timestamp_ns")
            if ts_ns is None:
                continue

            if self.first_ts_ns is None:
                self.first_ts_ns = ts_ns
            t_s = (ts_ns - self.first_ts_ns) / 1e9

            sensor_type = self.current_sensor_type or self.sensor_var.get()

            if sensor_type == "mpu":
                # Multi-MPU6050: use sensor_id and ax
                sid = int(obj.get("sensor_id", 1))
                value = obj.get("ax")
            else:
                # ADXL: single sensor; use sensor 1 slot and x_lp
                sid = 1
                value = obj.get("x_lp")

            try:
                value_f = float(value) if value is not None else None
            except (TypeError, ValueError):
                value_f = None

            if value_f is None:
                continue

            if sid not in self.plot_buffers:
                from collections import deque
                self.plot_buffers[sid] = {
                    "t": deque(maxlen=2000),
                    "y": deque(maxlen=2000),
                }

            self.plot_buffers[sid]["t"].append(t_s)
            self.plot_buffers[sid]["y"].append(value_f)
    except queue.Empty:
        pass

    # 2) Determine time window (seconds)
    try:
        window = float(self.live_window_seconds.get())
    except Exception:
        window = 0.0

    updated = False

    # 3) Update each subplot (sensor 1..3)
    if hasattr(self, "lines") and hasattr(self, "axes"):
        for idx, sid in enumerate((1, 2, 3)):
            line = self.lines.get(sid)
            if not line:
                continue

            buf = self.plot_buffers.get(sid)
            t_vals = list(buf["t"]) if buf else []
            y_vals = list(buf["y"]) if buf else []

            if not t_vals:
                line.set_data([], [])
                continue

            # Apply time window
            if window > 0:
                t_max = t_vals[-1]
                t_min = t_max - window
                t_plot = []
                y_plot = []
                for t, y in zip(t_vals, y_vals):
                    if t >= t_min:
                        t_plot.append(t)
                        y_plot.append(y)
            else:
                t_plot = t_vals
                y_plot = y_vals

            line.set_data(t_plot, y_plot)

            ax = self.axes[idx]
            if t_plot:
                if window > 0:
                    ax.set_xlim(max(t_plot[0], t_plot[-1] - window), t_plot[-1])
                else:
                    ax.set_xlim(min(t_plot), max(t_plot))
                ax.relim()
                ax.autoscale_view(scalex=False, scaley=True)

            updated = True

    if updated and hasattr(self, "canvas"):
        self.canvas.draw_idle()

    # Schedule next update
    self.root.after(50, self._update_plot)
```

This keeps the existing pattern of repeatedly calling `_update_plot` via `after(50, ...)`, but now:

- Uses per‑sensor buffers.
- Shows a stacked array of subplots.
- Applies the user’s live time window to the x‑axis.

---

## 8. Keep `_stdout_reader_thread` as-is

No change is needed here, except that it’s already pushing parsed JSON objects into `self.plot_queue`:

```python
def _stdout_reader_thread(self, stream) -> None:
    for raw_line in iter(stream.readline, ""):
        ...
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and "timestamp_ns" in obj:
                self.plot_queue.put(obj)
        except json.JSONDecodeError:
            pass
        ...
```

Leave that logic unchanged.

---

## Acceptance check

After your edits:

1. The bottom-middle of the GUI shows a **Notebook** with two tabs:
   - `Live plots`
   - `Logs`
2. The `Logs` tab contains the existing log text area.
3. The `Live plots` tab contains:
   - A **“Live window (s)”** control (spinbox + label).
   - A Matplotlib figure with **three stacked subplots**, labeled `S1 ax`, `S2 ax`, `S3 ax`.
4. When I run the MPU6050 logger with multiple sensors and `--stream-stdout`:
   - Each sensor’s `ax` data appears on its respective subplot.
5. Changing “Live window (s)”:
   - When > 0: I see only ~that many seconds of **recent** data on the x‑axis.
   - When 0: I see the **full** history of the current run.
6. ADXL mode still works:
   - Its `x_lp` stream appears on the **sensor 1** subplot,
   - Other subplots can stay empty.

Please apply these edits and return the updated `main.py` (or at least all modified methods) so I can paste it back into my project.
