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
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Dict, Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import paramiko  # pip install paramiko

CONFIG_FILE = "config.json"


@dataclass
class RemoteRunContext:
    """Holds info about the currently running remote process and its outputs."""

    command: str
    script_name: str
    sensor_type: str  # "adxl" or "mpu"
    remote_out_dir: str
    local_out_dir: str
    start_snapshot: Dict[str, float]


class SSHClientManager:
    """Encapsulates SSH and SFTP connections to the Raspberry Pi."""

    def __init__(self) -> None:
        self.client: Optional[paramiko.SSHClient] = None
        self.sftp = None
        self._lock = threading.Lock()

    def connect(
        self, host: str, port: int, username: str, password: str = "", pkey_path: Optional[str] = None
    ) -> None:
        """Establish SSH + SFTP connections."""
        with self._lock:
            if self.client:
                self.disconnect()
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kwargs = {"hostname": host, "port": int(port), "username": username}
            if pkey_path:
                kwargs["key_filename"] = pkey_path
            else:
                kwargs["password"] = password
            ssh.connect(**kwargs, look_for_keys=not pkey_path, allow_agent=False, timeout=10)
            self.client = ssh
            self.sftp = ssh.open_sftp()

    def disconnect(self) -> None:
        with self._lock:
            if self.sftp:
                try:
                    self.sftp.close()
                except Exception:
                    pass
                self.sftp = None
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None

    def is_connected(self) -> bool:
        return self.client is not None

    def exec_command_stream(self, command: str) -> Tuple[paramiko.Channel, any, any]:
        """Execute a command and return (channel, stdout, stderr) for streaming."""
        if not self.client:
            raise RuntimeError("SSH not connected")
        transport = self.client.get_transport()
        if not transport:
            raise RuntimeError("SSH transport not available")
        channel = transport.open_session()
        channel.exec_command(command)
        stdout = channel.makefile("r")
        stderr = channel.makefile_stderr("r")
        return channel, stdout, stderr

    def exec_quick(self, command: str) -> Tuple[str, str, int]:
        """Run a short command and return stdout, stderr, and exit status."""
        if not self.client:
            raise RuntimeError("SSH not connected")
        stdin, stdout, stderr = self.client.exec_command(command)
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        status = stdout.channel.recv_exit_status()
        return out, err, status

    def list_dir(self, remote_dir: str):
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        return self.sftp.listdir_attr(remote_dir)

    def listdir_with_mtime(self, remote_dir: str) -> Dict[str, float]:
        """Return {filename: mtime} for a remote directory."""
        entries = self.list_dir(remote_dir)
        return {entry.filename: entry.st_mtime for entry in entries}

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download one file via SFTP."""
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.sftp.get(remote_path, local_path)


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
        self.plot_time = deque(maxlen=2000)
        self.plot_value = deque(maxlen=2000)
        self.first_ts_ns: Optional[int] = None
        self.current_sensor_type: Optional[str] = None

        self._build_vars()
        self._build_ui()
        self.local_download_dir.trace_add("write", lambda *args: self._update_open_local_button_state())
        self._update_open_local_button_state()
        self._load_config_if_exists()
        self._poll_output_queue()
        self._update_plot()

    # ------------------------------------------------------------------ UI construction
    def _build_vars(self) -> None:
        # Connection
        self.host_var = tk.StringVar(value="raspberrypi.local")  # TODO: set your Pi host/IP
        self.port_var = tk.StringVar(value="22")
        self.user_var = tk.StringVar(value="pi")
        self.pass_var = tk.StringVar(value="")
        self.key_var = tk.StringVar(value="")
        self.conn_status = tk.StringVar(value="SSH: Disconnected")
        self.run_status = tk.StringVar(value="Run: Idle")
        self.download_status = tk.StringVar(value="Last download: n/a")

        # Sensor choice
        self.sensor_var = tk.StringVar(value="adxl")
        self.run_mode_var = tk.StringVar(value="Record only")
        self.stream_every_var = tk.IntVar(value=5)

        # ADXL203 / ADS1115 defaults
        self.adxl_script = tk.StringVar(value="/home/pi/adxl203_ads1115_logger.py")  # TODO: adjust path
        self.adxl_rate = tk.StringVar(value="100.0")
        self.adxl_channels = tk.StringVar(value="both")
        self.adxl_duration = tk.StringVar(value="")
        self.adxl_out = tk.StringVar(value="/home/pi/logs-adxl")  # TODO: adjust path
        self.adxl_addr = tk.StringVar(value="0x48")
        self.adxl_map = tk.StringVar(value="x:P0,y:P1")
        self.adxl_calibrate = tk.StringVar(value="300")
        self.adxl_lp_cut = tk.StringVar(value="15.0")

        # MPU6050 defaults
        self.mpu_script = tk.StringVar(value="/home/pi/mpu6050_multi_logger.py")  # TODO: adjust path
        self.mpu_rate = tk.StringVar(value="100.0")
        self.mpu_sensors = tk.StringVar(value="1,2,3")
        self.mpu_channels = tk.StringVar(value="default")
        self.mpu_duration = tk.StringVar(value="")
        self.mpu_samples = tk.StringVar(value="")
        self.mpu_out = tk.StringVar(value="/home/pi/logs-mpu")  # TODO: adjust path
        self.mpu_format = tk.StringVar(value="csv")
        self.mpu_prefix = tk.StringVar(value="mpu")
        self.mpu_dlpf = tk.StringVar(value="3")
        self.mpu_temp = tk.BooleanVar(value=False)
        self.mpu_flush_every = tk.StringVar(value="2000")
        self.mpu_flush_seconds = tk.StringVar(value="2.0")
        self.mpu_fsync_each = tk.BooleanVar(value=False)

        # Download vars
        default_local = os.path.expanduser(r"~/Downloads/sense-pi-logs")  # TODO: adjust Windows folder
        self.remote_download_dir = tk.StringVar(value=self.adxl_out.get())
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
        self._build_plot_frame()
        self._build_log_frame()
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

    def _build_log_frame(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Remote log output")
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
        run_mode = self.run_mode_var.get()
        stream_every = self._get_stream_every()
        if self.sensor_var.get() == "adxl":
            remote_adxl_path = self.adxl_script.get().strip()
            cmd_parts = [
                "python3",
                remote_adxl_path,
                "--rate",
                self.adxl_rate.get().strip(),
                "--channels",
                self.adxl_channels.get(),
                "--out",
                self.adxl_out.get().strip(),
            ]
            if self.adxl_duration.get().strip():
                cmd_parts += ["--duration", self.adxl_duration.get().strip()]
            if self.adxl_addr.get().strip():
                cmd_parts += ["--addr", self.adxl_addr.get().strip()]
            if self.adxl_map.get().strip():
                cmd_parts += ["--map", self.adxl_map.get().strip()]
            if self.adxl_calibrate.get().strip():
                cmd_parts += ["--calibrate", self.adxl_calibrate.get().strip()]
            if self.adxl_lp_cut.get().strip():
                cmd_parts += ["--lp-cut", self.adxl_lp_cut.get().strip()]
            if run_mode in ("Record + live plot", "Live plot only (no-record)"):
                if run_mode == "Live plot only (no-record)":
                    cmd_parts.append("--no-record")
                cmd_parts.append("--stream-stdout")
                cmd_parts += ["--stream-every", str(stream_every)]
                cmd_parts += ["--stream-fields", "x_lp,y_lp"]
            script_name = os.path.basename(remote_adxl_path or "adxl203_ads1115_logger.py")
        else:
            remote_mpu_path = self.mpu_script.get().strip()
            sensors_str = self.mpu_sensors.get().strip()
            channels = self.mpu_channels.get()
            fmt = self.mpu_format.get()
            prefix = self.mpu_prefix.get().strip()
            dlpf = self.mpu_dlpf.get().strip()
            cmd_parts = [
                "python3",
                remote_mpu_path,
                "--rate",
                self.mpu_rate.get().strip(),
                "--sensors",
                sensors_str,
                "--channels",
                channels,
                "--out",
                self.mpu_out.get().strip(),
                "--format",
                fmt,
            ]
            if self.mpu_duration.get().strip():
                cmd_parts += ["--duration", self.mpu_duration.get().strip()]
            if self.mpu_samples.get().strip():
                cmd_parts += ["--samples", self.mpu_samples.get().strip()]
            if prefix:
                cmd_parts += ["--prefix", prefix]
            if dlpf:
                cmd_parts += ["--dlpf", dlpf]
            if self.mpu_temp.get():
                cmd_parts.append("--temp")
            if self.mpu_flush_every.get().strip():
                cmd_parts += ["--flush-every", self.mpu_flush_every.get().strip()]
            if self.mpu_flush_seconds.get().strip():
                cmd_parts += ["--flush-seconds", self.mpu_flush_seconds.get().strip()]
            if self.mpu_fsync_each.get():
                cmd_parts.append("--fsync-each-flush")
            if run_mode in ("Record + live plot", "Live plot only (no-record)"):
                if run_mode == "Live plot only (no-record)":
                    cmd_parts.append("--no-record")
                cmd_parts.append("--stream-stdout")
                cmd_parts += ["--stream-every", str(stream_every)]
                cmd_parts += ["--stream-fields", "ax,ay,gz"]
            script_name = os.path.basename(remote_mpu_path or "mpu6050_multi_logger.py")
        return " ".join(cmd_parts), script_name

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
        self.plot_time.clear()
        self.plot_value.clear()
        self.first_ts_ns = None
        self._drain_plot_queue()
        if hasattr(self, "line"):
            self.line.set_data([], [])
            if hasattr(self, "canvas"):
                self.canvas.draw_idle()

    def _drain_plot_queue(self) -> None:
        try:
            while True:
                self.plot_queue.get_nowait()
        except queue.Empty:
            pass

    def _update_plot(self) -> None:
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
                value = obj.get("x_lp") if sensor_type == "adxl" else obj.get("ax")
                try:
                    value_f = float(value) if value is not None else None
                except (TypeError, ValueError):
                    value_f = None
                if value_f is None:
                    continue
                self.plot_time.append(t_s)
                self.plot_value.append(value_f)
        except queue.Empty:
            pass

        if self.plot_time:
            self.line.set_data(list(self.plot_time), list(self.plot_value))
            self.ax.relim()
            self.ax.autoscale_view()
            self.canvas.draw_idle()

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
