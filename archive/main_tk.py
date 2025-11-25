"""
Tkinter + Paramiko GUI for controlling Raspberry Pi sensor loggers.

How to run:
1) Install Python 3 and pip on Windows.
2) Install paramiko (only external dependency):
   pip install paramiko
3) Run the GUI:
   python main.py

Customize the default remote script paths and output folders below to match your Pi,
and update the local download folder to a convenient Windows path. All network work
runs in background threads to keep the UI responsive.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import paramiko  # pip install paramiko
from ssh_client import (
    AdxlParams,
    MpuParams,
    RUN_MODE_LIVE_ONLY,
    RUN_MODE_RECORD_AND_LIVE,
    RUN_MODE_RECORD_ONLY,
    RemoteRunContext,
    SSHClientManager,
    build_adxl_command,
    build_mpu_command,
)

CONFIG_FILE = "config.json"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Sense Pi Logger")
        self.manager = SSHClientManager()

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

        self._build_vars()
        self._build_ui()
        self.local_download_dir.trace_add("write", lambda *args: self._update_open_local_button_state())
        self._update_open_local_button_state()
        self._load_config_if_exists()
        self._poll_output_queue()
        self._update_plot()

    # ------------------------------------------------------------------ UI construction
    def _build_vars(self) -> None:
        # Connection (defaults for my Raspberry Pi)
        self.host_var = tk.StringVar(value="192.168.0.6")
        self.port_var = tk.StringVar(value="22")
        self.user_var = tk.StringVar(value="verwalter")
        self.pass_var = tk.StringVar(value="!66442200")
        self.key_var = tk.StringVar(value="")
        self.conn_status = tk.StringVar(value="SSH: Disconnected")
        self.run_status = tk.StringVar(value="Run: Idle")
        self.download_status = tk.StringVar(value="Last download: n/a")

        # Sensor choice
        # Default to multi‑MPU6050 (1–3 sensors)
        self.sensor_var = tk.StringVar(value="mpu")
        self.run_mode_var = tk.StringVar(value="Record only")
        self.stream_every_var = tk.IntVar(value=5)

        # Live plot window (seconds). 0 = show full history.
        self.live_window_seconds = tk.DoubleVar(value=5.0)

        # ADXL203 / ADS1115 defaults
        # (Not my main use case, but keep it consistent with the same logs folder)
        self.adxl_script = tk.StringVar(value="/home/verwalter/sensor/adxl203_ads1115_logger.py")
        self.adxl_rate = tk.StringVar(value="100.0")
        self.adxl_channels = tk.StringVar(value="both")
        self.adxl_duration = tk.StringVar(value="")
        self.adxl_out = tk.StringVar(value="/home/verwalter/sensor/logs")
        self.adxl_addr = tk.StringVar(value="0x48")
        self.adxl_map = tk.StringVar(value="x:P0,y:P1")
        self.adxl_calibrate = tk.StringVar(value="300")
        self.adxl_lp_cut = tk.StringVar(value="15.0")

        # MPU6050 defaults (primary sensor type)
        self.mpu_script = tk.StringVar(value="/home/verwalter/sensor/mpu6050_multi_logger.py")
        self.mpu_rate = tk.StringVar(value="100.0")
        self.mpu_sensors = tk.StringVar(value="1,2,3")
        self.mpu_channels = tk.StringVar(value="default")
        self.mpu_duration = tk.StringVar(value="")
        self.mpu_samples = tk.StringVar(value="")
        self.mpu_out = tk.StringVar(value="/home/verwalter/sensor/logs")
        self.mpu_format = tk.StringVar(value="csv")
        self.mpu_prefix = tk.StringVar(value="mpu")
        self.mpu_dlpf = tk.StringVar(value="3")
        self.mpu_temp = tk.BooleanVar(value=False)
        self.mpu_flush_every = tk.StringVar(value="2000")
        self.mpu_flush_seconds = tk.StringVar(value="2.0")
        self.mpu_fsync_each = tk.BooleanVar(value=False)

        # Download vars
        # Remote logs live under /home/verwalter/sensor/logs
        self.remote_download_dir = tk.StringVar(value=self.mpu_out.get())

        # Local default on my Windows machine
        default_local = r"C:\Projects\sense-pi-local-recording-live\logs"
        self.local_download_dir = tk.StringVar(value=default_local)

        # Common presets for quick setup (in-memory for now; can be persisted later).
        self.presets = {
            "Quick ADXL test (10 s @ 100 Hz)": {
                "sensor_type": "adxl",
                "rate": "100",
                "duration": "10",
                "channels": "both",
                "out": "/home/pi/logs/adxl",
                "addr": "0x48",
                "map": "x:P0,y:P1",
                "calibrate": "300",
                "lp_cut": "15",
            },
            "3×MPU6050 full sensors (60 s @ 200 Hz)": {
                "sensor_type": "mpu",
                "rate": "200",
                "duration": "60",
                "sensors": "1,2,3",
                "channels": "both",
                "out": "/home/pi/logs/mpu",
                "format": "csv",
                "prefix": "mpu",
                "dlpf": "3",
                "temp": True,
            },
        }

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

    def _build_connection_frame(self) -> None:
        frame = ttk.LabelFrame(self.root, text="SSH Connection")
        frame.pack(fill="x", padx=8, pady=6)
        labels = ["Host/IP", "Port", "Username", "Password", "Private key path"]
        vars_ = [self.host_var, self.port_var, self.user_var, self.pass_var, self.key_var]
        show_opts = [None, None, None, "*", None]
        for i, (label, var, show) in enumerate(zip(labels, vars_, show_opts)):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(frame, textvariable=var, show=show, width=32).grid(row=i, column=1, sticky="w", padx=4, pady=2)
        btns = ttk.Frame(frame)
        btns.grid(row=0, column=2, rowspan=2, padx=6, pady=2)
        ttk.Button(btns, text="Connect", command=self.connect).grid(row=0, column=0, pady=2, sticky="ew")
        ttk.Button(btns, text="Disconnect", command=self.disconnect).grid(row=1, column=0, pady=2, sticky="ew")
        ttk.Label(frame, textvariable=self.conn_status, foreground="blue").grid(row=2, column=2, padx=4, pady=2)

    def _build_sensor_frame(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Sensor setup")
        frame.pack(fill="x", padx=8, pady=6)
        ttk.Label(frame, text="Choose sensor").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        ttk.Radiobutton(
            frame, text="Single ADXL203 (ADS1115)", variable=self.sensor_var, value="adxl", command=self._switch_sensor
        ).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(
            frame, text="Multi MPU6050 (1–3 sensors)", variable=self.sensor_var, value="mpu", command=self._switch_sensor
        ).grid(row=0, column=2, sticky="w")

        self.sensor_container = ttk.Frame(frame)
        self.sensor_container.grid(row=1, column=0, columnspan=3, sticky="ew", padx=4, pady=4)
        self.sensor_container.columnconfigure(1, weight=1)

        self.adxl_frame = self._build_adxl_fields(self.sensor_container)
        self.mpu_frame = self._build_mpu_fields(self.sensor_container)
        self._switch_sensor()

    def _build_presets_frame(self) -> None:
        # Quick presets for common setups (in-memory; ready for future persistence).
        frame = ttk.LabelFrame(self.root, text="Presets")
        frame.pack(fill="x", padx=8, pady=4)
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(frame, textvariable=self.preset_var, values=list(self.presets.keys()), state="readonly", width=40)
        self.preset_combo.grid(row=0, column=0, padx=4, pady=4, sticky="w")
        ttk.Button(frame, text="Apply preset", command=self.apply_selected_preset).grid(row=0, column=1, padx=4, pady=4, sticky="w")
        frame.columnconfigure(0, weight=1)

    def _build_adxl_fields(self, parent) -> ttk.Frame:
        frm = ttk.Frame(parent)
        fields = [
            ("Script path", self.adxl_script),
            ("rate (Hz)", self.adxl_rate),
            ("channels", self.adxl_channels, ["x", "y", "both"]),
            ("duration (s)", self.adxl_duration),
            ("out", self.adxl_out),
            ("addr", self.adxl_addr),
            ("map", self.adxl_map),
            ("calibrate", self.adxl_calibrate),
            ("lp-cut", self.adxl_lp_cut),
        ]
        for row, (label, var, *rest) in enumerate(fields):
            ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
            if rest:
                ttk.Combobox(frm, textvariable=var, values=rest[0], state="readonly").grid(
                    row=row, column=1, sticky="ew", padx=4, pady=2
                )
            else:
                ttk.Entry(frm, textvariable=var).grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        return frm

    def _build_mpu_fields(self, parent) -> ttk.Frame:
        frm = ttk.Frame(parent)
        combos = {
            "channels": (self.mpu_channels, ["acc", "gyro", "both", "default"]),
            "format": (self.mpu_format, ["csv", "jsonl"]),
        }
        fields = [
            ("Script path", self.mpu_script),
            ("rate (Hz)", self.mpu_rate),
            ("sensors", self.mpu_sensors),
            ("channels", self.mpu_channels),
            ("duration (s)", self.mpu_duration),
            ("samples", self.mpu_samples),
            ("out", self.mpu_out),
            ("format", self.mpu_format),
            ("prefix", self.mpu_prefix),
            ("dlpf", self.mpu_dlpf),
            ("flush-every", self.mpu_flush_every),
            ("flush-seconds", self.mpu_flush_seconds),
        ]
        for row, (label, var) in enumerate(fields):
            ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
            if label in combos:
                ttk.Combobox(frm, textvariable=var, values=combos[label][1], state="readonly").grid(
                    row=row, column=1, sticky="ew", padx=4, pady=2
                )
            else:
                ttk.Entry(frm, textvariable=var).grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        ttk.Checkbutton(frm, text="temp", variable=self.mpu_temp).grid(row=len(fields), column=0, sticky="w", padx=4)
        ttk.Checkbutton(frm, text="fsync-each-flush", variable=self.mpu_fsync_each).grid(
            row=len(fields), column=1, sticky="w", padx=4
        )
        return frm

    def apply_selected_preset(self) -> None:
        """Apply the currently selected preset to the form fields."""
        name = self.preset_var.get()
        preset = self.presets.get(name)
        if not preset:
            return

        def _set_if_present(key: str, var: tk.Variable) -> None:
            if key in preset:
                var.set(str(preset[key]))

        sensor_type = preset.get("sensor_type")
        if sensor_type == "adxl":
            self.sensor_var.set("adxl")
            _set_if_present("rate", self.adxl_rate)
            _set_if_present("duration", self.adxl_duration)
            _set_if_present("channels", self.adxl_channels)
            _set_if_present("out", self.adxl_out)
            _set_if_present("addr", self.adxl_addr)
            _set_if_present("map", self.adxl_map)
            _set_if_present("calibrate", self.adxl_calibrate)
            _set_if_present("lp_cut", self.adxl_lp_cut)
        else:
            self.sensor_var.set("mpu")
            _set_if_present("rate", self.mpu_rate)
            _set_if_present("duration", self.mpu_duration)
            _set_if_present("sensors", self.mpu_sensors)
            _set_if_present("channels", self.mpu_channels)
            _set_if_present("out", self.mpu_out)
            _set_if_present("format", self.mpu_format)
            _set_if_present("prefix", self.mpu_prefix)
            _set_if_present("dlpf", self.mpu_dlpf)
            if "temp" in preset:
                self.mpu_temp.set(bool(preset["temp"]))

        self._switch_sensor()
        self._sync_remote_download_dir()
        self._log(f"Applied preset: {name}")

    def _build_controls_frame(self) -> None:
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", padx=8, pady=4)
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Start recording", command=self.start_recording).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Stop recording", command=self.stop_recording).pack(side="left", padx=4)

        mode_frame = ttk.LabelFrame(frame, text="Run mode / Live plot")
        mode_frame.pack(side="left", padx=8, pady=2, fill="x", expand=True)
        ttk.Label(mode_frame, text="Run mode").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(
            mode_frame,
            textvariable=self.run_mode_var,
            values=["Record only", "Record + live plot", "Live plot only (no-record)"],
            state="readonly",
            width=24,
        ).grid(row=0, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(mode_frame, text="Stream every Nth sample").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        spin = ttk.Spinbox(mode_frame, from_=1, to=100000, textvariable=self.stream_every_var, width=8)
        spin.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        spin.set(self.stream_every_var.get())

    def _build_download_frame(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Download newest files")
        frame.pack(fill="x", padx=8, pady=6)
        ttk.Label(frame, text="Remote output dir").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(frame, textvariable=self.remote_download_dir, width=40).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(frame, text="Local destination").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(frame, textvariable=self.local_download_dir, width=40).grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Button(frame, text="Browse...", command=self._choose_local_folder).grid(row=1, column=2, padx=4)
        self.open_local_btn = ttk.Button(frame, text="Open local folder", command=self.open_local_folder, state="disabled")
        self.open_local_btn.grid(row=1, column=3, padx=4)
        ttk.Button(frame, text="Download newest files", command=self.download_newest).grid(
            row=0, column=2, padx=4, pady=2
        )
        ttk.Label(
            frame,
            text="Heuristic: newest = latest 5 files by mtime in the remote folder (non-destructive).",
            foreground="gray",
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=4, pady=2)
        frame.columnconfigure(1, weight=1)

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

    def _build_log_frame(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Remote log output")
        frame.pack(fill="both", expand=True, padx=8, pady=6)
        self.log_text = scrolledtext.ScrolledText(frame, height=18, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_status_bar(self) -> None:
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", padx=8, pady=4, side="bottom")
        ttk.Label(frame, textvariable=self.conn_status).pack(side="left", padx=4)
        ttk.Label(frame, textvariable=self.run_status).pack(side="left", padx=4)
        ttk.Label(frame, textvariable=self.download_status).pack(side="right", padx=4)

    # ------------------------------------------------------------------ Connection handlers
    def connect(self) -> None:
        thread = threading.Thread(target=self._connect_worker, daemon=True)
        thread.start()

    def _connect_worker(self) -> None:
        host = self.host_var.get().strip()
        port = int(self.port_var.get().strip() or 22)
        username = self.user_var.get().strip()
        password = self.pass_var.get()
        key_path = self.key_var.get().strip() or None
        self._set_status(self.conn_status, "SSH: Connecting...")
        try:
            self.manager.connect(host, port, username, password=password, pkey_path=key_path)
            connected_msg = f"SSH: Connected to {username}@{host}:{port}"
            self._set_status(self.conn_status, connected_msg)
            self._log(f"Connected to {username}@{host}:{port}")
        except Exception as exc:
            self._set_status(self.conn_status, "SSH: Disconnected")
            self._log(f"Connection error: {exc}")
            self.root.after(0, lambda: messagebox.showerror("Connection failed", str(exc)))

    def disconnect(self) -> None:
        thread = threading.Thread(target=self._disconnect_worker, daemon=True)
        thread.start()

    def _disconnect_worker(self) -> None:
        try:
            self.manager.disconnect()
            self._set_status(self.conn_status, "SSH: Disconnected")
            self._log("Disconnected.")
        except Exception as exc:
            self._log(f"Disconnect error: {exc}")

    # ------------------------------------------------------------------ Command building
    def build_command(self) -> Tuple[str, str]:
        """Construct the python3 command for the selected sensor. Optional args omitted if blank."""
        run_mode_label = self.run_mode_var.get()
        run_mode = {
            RUN_MODE_RECORD_ONLY: RUN_MODE_RECORD_ONLY,
            RUN_MODE_RECORD_AND_LIVE: RUN_MODE_RECORD_AND_LIVE,
            RUN_MODE_LIVE_ONLY: RUN_MODE_LIVE_ONLY,
        }.get(run_mode_label, RUN_MODE_RECORD_ONLY)

        stream_every = self._get_stream_every()

        if self.sensor_var.get() == "adxl":
            params = AdxlParams(
                script_path=self.adxl_script.get().strip(),
                rate=float(self.adxl_rate.get().strip()),
                channels=self.adxl_channels.get(),
                out_dir=self.adxl_out.get().strip(),
                duration=self._parse_optional_float(self.adxl_duration.get()),
                addr=self.adxl_addr.get().strip() or None,
                channel_map=self.adxl_map.get().strip() or None,
                calibrate=self._parse_optional_int(self.adxl_calibrate.get()),
                lp_cut=self._parse_optional_float(self.adxl_lp_cut.get()),
            )
            return build_adxl_command(params, run_mode=run_mode, stream_every=stream_every)

        params = MpuParams(
            script_path=self.mpu_script.get().strip(),
            rate=float(self.mpu_rate.get().strip()),
            sensors=self.mpu_sensors.get().strip(),
            channels=self.mpu_channels.get(),
            out_dir=self.mpu_out.get().strip(),
            duration=self._parse_optional_float(self.mpu_duration.get()),
            samples=self._parse_optional_int(self.mpu_samples.get()),
            fmt=self.mpu_format.get(),
            prefix=self.mpu_prefix.get().strip(),
            dlpf=self.mpu_dlpf.get().strip(),
            temp=self.mpu_temp.get(),
            flush_every=self._parse_optional_int(self.mpu_flush_every.get()),
            flush_seconds=self._parse_optional_float(self.mpu_flush_seconds.get()),
            fsync_each_flush=self.mpu_fsync_each.get(),
        )
        return build_mpu_command(params, run_mode=run_mode, stream_every=stream_every)

    # ------------------------------------------------------------------ Run handlers
    def start_recording(self) -> None:
        if not self.manager.is_connected():
            messagebox.showerror("Not connected", "Connect to the Pi first.")
            return
        if self.current_channel:
            messagebox.showinfo("Already running", "A recording is already in progress.")
            return
        if not self._validate_inputs():
            return
        command, script_name = self.build_command()
        sensor_type = self.sensor_var.get()
        remote_out_dir = self._current_out_dir()
        local_out_dir = os.path.expanduser(self.local_download_dir.get().strip())
        try:
            # Snapshot the remote output directory before the run starts.
            start_snapshot = self.manager.listdir_with_mtime(remote_out_dir)
        except Exception as exc:
            self._log(f"Could not read remote output folder before start: {exc}")
            messagebox.showerror("Cannot start run", f"Failed to list remote output folder: {exc}")
            return

        self.current_sensor_type = sensor_type
        self._reset_plot_state()
        self.stop_event.clear()
        self.current_run = RemoteRunContext(
            command=command,
            script_name=script_name,
            sensor_type=sensor_type,
            remote_out_dir=remote_out_dir,
            local_out_dir=local_out_dir,
            start_snapshot=start_snapshot,
        )
        sensor_label = "ADXL" if sensor_type == "adxl" else "MPU6050"
        self._set_status(self.run_status, f"Run: Running {sensor_label}")
        self._log(f"Starting remote command: {command}")
        self._log(f"Snapshot taken for {remote_out_dir} ({len(start_snapshot)} entries)")
        thread = threading.Thread(target=self._run_worker, args=(command, script_name), daemon=True)
        thread.start()

    def _run_worker(self, command: str, script_name: str) -> None:
        try:
            channel, stdout, stderr = self.manager.exec_command_stream(command)
            self.current_channel = channel
        except Exception as exc:
            self._log(f"Run start error: {exc}")
            self._set_status(self.run_status, "Run: Error")
            self.root.after(0, lambda: messagebox.showerror("Run failed", str(exc)))
            return
        out_thread = threading.Thread(target=self._stdout_reader_thread, args=(stdout,), daemon=True)
        err_thread = threading.Thread(target=self._stderr_reader_thread, args=(stderr,), daemon=True)
        out_thread.start()
        err_thread.start()

        while not channel.exit_status_ready():
            if self.stop_event.is_set():
                try:
                    channel.close()
                except Exception:
                    pass
                break
            time.sleep(0.1)

        try:
            status = channel.recv_exit_status()
        except Exception:
            status = -1
        out_thread.join(timeout=1.0)
        err_thread.join(timeout=1.0)
        self.log_queue.put(f"Command finished with status {status}")
        self._start_auto_download_thread(status)
        self.current_channel = None
        self._set_status(self.run_status, "Run: Idle")

    def _stdout_reader_thread(self, stream) -> None:
        for raw_line in iter(stream.readline, ""):
            if not raw_line:
                break
            line = raw_line.rstrip("\n")
            self.log_queue.put(line)
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "timestamp_ns" in obj:
                    self.plot_queue.put(obj)
            except json.JSONDecodeError:
                pass
            if self.stop_event.is_set():
                break

    def _stderr_reader_thread(self, stream) -> None:
        for raw_line in iter(stream.readline, ""):
            if not raw_line:
                break
            line = raw_line.rstrip("\n")
            self.log_queue.put(f"ERR: {line}")
            if self.stop_event.is_set():
                break

    def stop_recording(self) -> None:
        """Gracefully stop by closing the channel, then pkill as a fallback."""
        if not self.manager.is_connected():
            return
        self.stop_event.set()
        if self.current_channel:
            try:
                self.current_channel.close()
            except Exception:
                pass
        thread = threading.Thread(target=self._stop_worker, daemon=True)
        thread.start()

    def _stop_worker(self) -> None:
        script_name = (self.current_run.script_name if self.current_run else "")
        pattern = script_name or ("adxl203_ads1115_logger.py" if self.sensor_var.get() == "adxl" else "mpu6050_multi_logger.py")
        try:
            _, err, status = self.manager.exec_quick(f"pkill -f {pattern}")
            self._log(f"Stop command sent (pkill status {status}).")
            if err.strip():
                self._log(f"pkill stderr: {err.strip()}")
        except Exception as exc:
            self._log(f"Stop error: {exc}")
        finally:
            self.current_channel = None
            self._set_status(self.run_status, "Run: Idle")

    # ------------------------------------------------------------------ Auto-download after runs
    def _start_auto_download_thread(self, exit_status: int) -> None:
        """Kick off post-run download work on a background thread."""
        ctx = self.current_run
        thread = threading.Thread(target=self._handle_run_finished, args=(exit_status, ctx), daemon=True)
        thread.start()

    def _handle_run_finished(self, exit_status: int, ctx: Optional[RemoteRunContext]) -> None:
        """
        Workflow: run finishes -> snapshot remote dir -> diff vs start -> download new files.
        Keeps UI updates thread-safe via _log/_set_status.
        """
        if ctx is None:
            return
        try:
            self._log(f"Run finished (status {exit_status}). Scanning {ctx.remote_out_dir} for new files...")
            end_snapshot = self.manager.listdir_with_mtime(ctx.remote_out_dir)
            new_files = []
            for name, mtime in end_snapshot.items():
                old_mtime = ctx.start_snapshot.get(name)
                if old_mtime is None or mtime > old_mtime + 1e-6:
                    new_files.append((name, mtime))

            self._log(f"Run finished, downloading {len(new_files)} new files...")
            if not new_files:
                self._set_status(self.download_status, f"Last run: no new files ({self._timestamp()})")
                return

            os.makedirs(ctx.local_out_dir, exist_ok=True)
            for fname, _ in sorted(new_files, key=lambda x: x[1]):
                remote_path = f"{ctx.remote_out_dir.rstrip('/')}/{fname}"
                local_path = os.path.join(ctx.local_out_dir, fname)
                self.manager.download_file(remote_path, local_path)
                self._log(f"Downloaded {fname} -> {local_path}")

            timestamp = self._timestamp()
            self._set_status(self.download_status, f"Last run: {len(new_files)} file(s) downloaded at {timestamp}")
        except Exception as exc:
            self._log(f"[ERROR] Auto-download failed: {exc}")
            self._set_status(self.download_status, f"Last run: download failed at {self._timestamp()}")
            self.root.after(0, lambda: messagebox.showerror("Auto-download failed", str(exc)))
        finally:
            # Clear run context once the post-run tasks are done.
            if self.current_run is ctx:
                self.current_run = None

    # ------------------------------------------------------------------ Download helpers
    def download_newest(self) -> None:
        if not self.manager.is_connected():
            messagebox.showerror("Not connected", "Connect before downloading.")
            self._set_status(self.download_status, "Manual download: not connected")
            return
        thread = threading.Thread(target=self._download_worker, daemon=True)
        thread.start()

    def _download_worker(self) -> None:
        remote_dir = self.remote_download_dir.get().strip()
        local_dir = os.path.expanduser(self.local_download_dir.get().strip())
        if not remote_dir:
            self._log("Remote output directory is empty; nothing to download.")
            self._set_status(self.download_status, "Manual download: remote dir missing")
            return
        self._set_status(self.download_status, "Manual download: in progress")
        try:
            snapshot = self.manager.listdir_with_mtime(remote_dir)
            # Heuristic: newest = latest 5 files by mtime (documented in UI label).
            newest = sorted(snapshot.items(), key=lambda e: e[1], reverse=True)[:5]
            if not newest:
                self._log("No files found to download.")
                self._set_status(self.download_status, "Manual download: no files found")
                return
            for filename, _ in newest:
                remote_path = f"{remote_dir.rstrip('/')}/{filename}"
                local_path = os.path.join(local_dir, filename)
                self.manager.download_file(remote_path, local_path)
                self._log(f"Downloaded {filename} -> {local_path}")
            timestamp = self._timestamp()
            self._set_status(self.download_status, f"Manual download: {len(newest)} file(s) at {timestamp}")
        except Exception as exc:
            self._log(f"Download error: {exc}")
            self._set_status(self.download_status, f"Manual download failed at {self._timestamp()}")
            self.root.after(0, lambda: messagebox.showerror("Download failed", str(exc)))

    # ------------------------------------------------------------------ Config save/load
    def save_config(self) -> None:
        cfg = {
            "host": self.host_var.get(),
            "port": self.port_var.get(),
            "username": self.user_var.get(),
            "password": self.pass_var.get(),  # TODO: storing password in plain text is insecure.
            "key": self.key_var.get(),
            "adxl_script": self.adxl_script.get(),
            "adxl_out": self.adxl_out.get(),
            "mpu_script": self.mpu_script.get(),
            "mpu_out": self.mpu_out.get(),
            "local_download": self.local_download_dir.get(),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._log("Config saved.")
        except Exception as exc:
            self._log(f"Save failed: {exc}")
            messagebox.showerror("Save config", str(exc))

    def load_config(self) -> None:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.host_var.set(cfg.get("host", self.host_var.get()))
            self.port_var.set(cfg.get("port", self.port_var.get()))
            self.user_var.set(cfg.get("username", self.user_var.get()))
            self.pass_var.set(cfg.get("password", ""))
            self.key_var.set(cfg.get("key", ""))
            self.adxl_script.set(cfg.get("adxl_script", self.adxl_script.get()))
            self.adxl_out.set(cfg.get("adxl_out", self.adxl_out.get()))
            self.mpu_script.set(cfg.get("mpu_script", self.mpu_script.get()))
            self.mpu_out.set(cfg.get("mpu_out", self.mpu_out.get()))
            self.local_download_dir.set(cfg.get("local_download", self.local_download_dir.get()))
            self._log("Config loaded.")
            self._sync_remote_download_dir()
        except FileNotFoundError:
            messagebox.showinfo("Load config", "No config file found yet.")
        except Exception as exc:
            messagebox.showerror("Load config", str(exc))
            self._log(f"Load failed: {exc}")

    def _load_config_if_exists(self) -> None:
        if Path(CONFIG_FILE).exists():
            try:
                self.load_config()
            except Exception:
                # Continue with defaults if config is bad.
                pass

    # ------------------------------------------------------------------ Misc helpers
    def _switch_sensor(self) -> None:
        for child in self.sensor_container.winfo_children():
            child.grid_forget()
        if self.sensor_var.get() == "adxl":
            self.adxl_frame.grid(row=0, column=0, sticky="ew")
            self.remote_download_dir.set(self.adxl_out.get())
        else:
            self.mpu_frame.grid(row=0, column=0, sticky="ew")
            self.remote_download_dir.set(self.mpu_out.get())

    def _validate_inputs(self) -> bool:
        """Basic validation before starting a run."""
        sensor_type = self.sensor_var.get()
        try:
            rate_raw = self.adxl_rate.get() if sensor_type == "adxl" else self.mpu_rate.get()
            rate = float(rate_raw)
            if rate <= 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Invalid rate", "Rate must be a positive number.")
            return False

        out_dir = self._current_out_dir()
        if not out_dir:
            messagebox.showerror("Missing output dir", "Remote --out folder cannot be empty.")
            return False

        if sensor_type == "mpu":
            sensors_raw = self.mpu_sensors.get().strip()
            if not sensors_raw:
                messagebox.showerror("Invalid sensors", "Sensors must be a comma-separated subset of 1,2,3.")
                return False
            try:
                sensors = {int(part.strip()) for part in sensors_raw.split(",") if part.strip()}
            except ValueError:
                messagebox.showerror("Invalid sensors", "Sensors must be a comma-separated subset of 1,2,3.")
                return False
            if not sensors or not sensors.issubset({1, 2, 3}):
                messagebox.showerror("Invalid sensors", "Sensors must be a comma-separated subset of 1,2,3.")
                return False

        return True

    def _get_stream_every(self) -> int:
        """Return a safe integer for stream decimation."""
        try:
            value = int(self.stream_every_var.get())
        except Exception:
            value = 1
        return max(1, value)

    def _parse_optional_float(self, raw: str) -> Optional[float]:
        value = raw.strip() if isinstance(raw, str) else ""
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _parse_optional_int(self, raw: str) -> Optional[int]:
        value = raw.strip() if isinstance(raw, str) else ""
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _current_out_dir(self) -> str:
        return self.adxl_out.get().strip() if self.sensor_var.get() == "adxl" else self.mpu_out.get().strip()

    def _choose_local_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select local download folder")
        if folder:
            self.local_download_dir.set(folder)
            self._update_open_local_button_state()

    def _update_open_local_button_state(self) -> None:
        """Enable/disable the 'Open local folder' button based on folder validity."""
        if not hasattr(self, "open_local_btn"):
            return
        folder = os.path.expanduser(self.local_download_dir.get().strip())
        if folder and os.path.isdir(folder):
            self.open_local_btn.state(["!disabled"])
        else:
            self.open_local_btn.state(["disabled"])

    def open_local_folder(self) -> None:
        folder = os.path.expanduser(self.local_download_dir.get().strip())
        if not folder or not os.path.isdir(folder):
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", folder])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as exc:
            self._log(f"Open folder failed: {exc}")
            messagebox.showerror("Open folder", f"Could not open folder: {exc}")

    def _set_status(self, var: tk.StringVar, text: str) -> None:
        self.root.after(0, lambda: var.set(text))

    def _timestamp(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.root.after(0, lambda: self._append_log(f"[{timestamp}] {text}"))

    def _append_log(self, line: str) -> None:
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)

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

    def _drain_plot_queue(self) -> None:
        try:
            while True:
                self.plot_queue.get_nowait()
        except queue.Empty:
            pass

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

    def _poll_output_queue(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_output_queue)

    def _sync_remote_download_dir(self) -> None:
        if self.sensor_var.get() == "adxl":
            self.remote_download_dir.set(self.adxl_out.get())
        else:
            self.remote_download_dir.set(self.mpu_out.get())


def main() -> None:
    root = tk.Tk()
    root.geometry("880x800")
    app = App(root)

    # Config buttons at the bottom to keep the main UI simple.
    cfg_frame = ttk.Frame(root)
    cfg_frame.pack(fill="x", padx=8, pady=4)
    ttk.Button(cfg_frame, text="Save config", command=app.save_config).pack(side="left", padx=4)
    ttk.Button(cfg_frame, text="Load config", command=app.load_config).pack(side="left", padx=4)

    root.mainloop()


if __name__ == "__main__":
    main()
