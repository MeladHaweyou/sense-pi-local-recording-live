"""
Tkinter + Paramiko GUI for running and retrieving logs from a Raspberry Pi.

How to run:
    pip install paramiko
    python main.py

This is a first working version that favors clarity and resilience:
- All network actions run in background threads.
- Log output from the remote command is streamed into the GUI.
- The "Download newest files" button grabs the newest files (by mtime) from
  the configured remote output directory without deleting anything on the Pi.

Customize the default remote script paths and output folders below to match
your Pi layout. Update the default local download folder to a convenient path
on your Windows machine.
"""

import json
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, scrolledtext, ttk
from typing import Dict, Optional

from collections import deque

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import paramiko


CONFIG_FILE = "config.json"


@dataclass
class RemoteRunContext:
    """Keeps per-run info so we can auto-download new files when the run ends."""

    sensor_type: str
    command: str
    remote_out_dir: str
    local_out_dir: str
    start_snapshot: Dict[str, float]


class SSHClientManager:
    """Wraps paramiko SSH + SFTP with simple helpers."""

    def __init__(self) -> None:
        self.ssh = None
        self.sftp = None
        self._lock = threading.Lock()

    def connect(self, host: str, port: int, username: str, password: str, pkey_path: Optional[str] = None) -> None:
        with self._lock:
            if self.ssh:
                return
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            pkey = None
            if pkey_path:
                pkey = paramiko.RSAKey.from_private_key_file(pkey_path)
            ssh.connect(
                hostname=host,
                port=int(port),
                username=username,
                password=password or None,
                pkey=pkey,
                look_for_keys=not pkey_path,
                allow_agent=False,
                timeout=10,
            )
            self.ssh = ssh
            self.sftp = ssh.open_sftp()

    def disconnect(self) -> None:
        with self._lock:
            if self.sftp:
                try:
                    self.sftp.close()
                except Exception:
                    pass
                self.sftp = None
            if self.ssh:
                try:
                    self.ssh.close()
                except Exception:
                    pass
                self.ssh = None

    def is_connected(self) -> bool:
        return self.ssh is not None

    def exec_command_stream(self, command: str):
        """Execute a command and return channel, stdout, stderr for streaming."""
        if not self.ssh:
            raise RuntimeError("SSH not connected")
        stdin, stdout, stderr = self.ssh.exec_command(command)
        return stdout.channel, stdout, stderr

    def exec_quick(self, command: str) -> tuple[str, str, int]:
        """Run a short command and return stdout, stderr, exit status."""
        if not self.ssh:
            raise RuntimeError("SSH not connected")
        stdin, stdout, stderr = self.ssh.exec_command(command)
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        exit_status = stdout.channel.recv_exit_status()
        return out, err, exit_status

    def list_dir(self, remote_dir: str):
        if not self.sftp:
            raise RuntimeError("SFTP not connected")
        return self.sftp.listdir_attr(remote_dir)

    def listdir_with_mtime(self, remote_dir: str) -> Dict[str, float]:
        """Return a mapping of filename -> mtime for a remote directory."""
        entries = self.list_dir(remote_dir)
        return {entry.filename: entry.st_mtime for entry in entries}

    def download_file(self, remote_path: str, local_path: str) -> None:
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
        self.plot_queue: queue.Queue[dict] = queue.Queue()
        self.presets = self._build_presets()

        self.current_channel = None
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.current_run_context: Optional[RemoteRunContext] = None
        self.plot_time = deque(maxlen=2000)
        self.plot_value = deque(maxlen=2000)
        self.first_ts_ns: Optional[int] = None
        self.current_sensor_type = "adxl"

        self._build_vars()
        self._build_ui()
        self._load_config_if_exists()
        self._update_open_folder_button_state()
        self._update_plot()
        self._poll_queue()

    def _build_presets(self) -> Dict[str, Dict[str, object]]:
        """Define in-memory presets for quick application."""
        return {
            "Quick ADXL test (10 s @ 100 Hz)": {
                "sensor": "adxl",
                "params": {
                    "adxl_rate": "100.0",
                    "adxl_channels": "both",
                    "adxl_duration": "10",
                    "adxl_out": "/home/pi/logs-adxl",
                    "adxl_addr": "0x48",
                    "adxl_map": "x:P0,y:P1",
                    "adxl_calibrate": "300",
                    "adxl_lp_cut": "15.0",
                },
            },
            "3xMPU6050 full sensors (60 s @ 200 Hz)": {
                "sensor": "mpu",
                "params": {
                    "mpu_rate": "200.0",
                    "mpu_sensors": "1,2,3",
                    "mpu_channels": "both",
                    "mpu_duration": "60",
                    "mpu_out": "/home/pi/logs-mpu",
                    "mpu_format": "csv",
                    "mpu_prefix": "mpu",
                    "mpu_dlpf": "3",
                    "mpu_temp": True,
                    "mpu_flush_every": "2000",
                    "mpu_flush_seconds": "2.0",
                    "mpu_fsync_each": False,
                },
            },
        }

    def _set_status_value(self, var: tk.StringVar, text: str) -> None:
        """Thread-safe status updater."""
        self.root.after(0, lambda: var.set(text))

    def _update_run_status(self, text: str) -> None:
        self._set_status_value(self.run_status_var, text)

    def _update_download_status(self, text: str) -> None:
        self._set_status_value(self.download_status_var, text)

    def _sync_remote_download_dir(self) -> None:
        """Keep manual download source aligned with the selected sensor output."""
        if self.sensor_var.get() == "adxl":
            self.remote_download_dir.set(self.adxl_out.get())
        else:
            self.remote_download_dir.set(self.mpu_out.get())

    def _schedule_open_folder_state_refresh(self) -> None:
        self.root.after(0, self._update_open_folder_button_state)

    def _update_open_folder_button_state(self) -> None:
        path = self.local_download_dir.get().strip()
        if not hasattr(self, "open_folder_btn"):
            return
        if path and os.path.isdir(path):
            self.open_folder_btn.state(["!disabled"])
        else:
            self.open_folder_btn.state(["disabled"])

    def apply_selected_preset(self) -> None:
        name = self.preset_var.get()
        preset = self.presets.get(name)
        if not preset:
            messagebox.showerror("Preset", "Select a preset to apply.")
            return
        self.sensor_var.set(preset.get("sensor", self.sensor_var.get()))
        params = preset.get("params", {})
        for key, value in params.items():
            var = self.preset_targets.get(key)
            if not var:
                continue
            if isinstance(var, tk.BooleanVar):
                var.set(bool(value))
            else:
                var.set(str(value))
        self._show_sensor_frame()
        self._sync_remote_download_dir()
        self._update_open_folder_button_state()

    def _build_vars(self) -> None:
        # Connection vars
        self.host_var = tk.StringVar(value="192.168.1.50")  # TODO: adjust to your Pi
        self.port_var = tk.StringVar(value="22")
        self.user_var = tk.StringVar(value="pi")
        self.pass_var = tk.StringVar(value="")
        self.key_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Disconnected")
        self.ssh_status_var = tk.StringVar(value="SSH: Disconnected")
        self.run_status_var = tk.StringVar(value="Run: Idle")
        self.download_status_var = tk.StringVar(value="Last download: n/a")
        self.run_mode_var = tk.StringVar(value="Record only")
        self.stream_every_var = tk.IntVar(value=5)

        # Sensor selection
        self.sensor_var = tk.StringVar(value="adxl")
        self.preset_var = tk.StringVar(value="")

        # ADXL defaults
        self.adxl_script = tk.StringVar(value="/home/pi/adxl203_ads1115_logger.py")  # TODO: adjust path
        self.adxl_rate = tk.StringVar(value="100.0")
        self.adxl_channels = tk.StringVar(value="both")
        self.adxl_duration = tk.StringVar(value="")
        self.adxl_out = tk.StringVar(value="/home/pi/logs-adxl")  # TODO: adjust path
        self.adxl_addr = tk.StringVar(value="0x48")
        self.adxl_map = tk.StringVar(value="x:P0,y:P1")
        self.adxl_calibrate = tk.StringVar(value="300")
        self.adxl_lp_cut = tk.StringVar(value="15.0")

        # MPU defaults
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
        default_local = os.path.expanduser(r"~/Downloads/sense-pi-logs")  # TODO: adjust local folder
        self.remote_download_dir = tk.StringVar(value="/home/pi/logs-adxl")  # updated on sensor change
        self.local_download_dir = tk.StringVar(value=default_local)
        self.local_download_dir.trace_add("write", lambda *_: self._schedule_open_folder_state_refresh())

        # Map parameter names used in presets to the actual Tk variables.
        self.preset_targets: Dict[str, tk.Variable] = {
            "adxl_rate": self.adxl_rate,
            "adxl_channels": self.adxl_channels,
            "adxl_duration": self.adxl_duration,
            "adxl_out": self.adxl_out,
            "adxl_addr": self.adxl_addr,
            "adxl_map": self.adxl_map,
            "adxl_calibrate": self.adxl_calibrate,
            "adxl_lp_cut": self.adxl_lp_cut,
            "mpu_rate": self.mpu_rate,
            "mpu_sensors": self.mpu_sensors,
            "mpu_channels": self.mpu_channels,
            "mpu_duration": self.mpu_duration,
            "mpu_samples": self.mpu_samples,
            "mpu_out": self.mpu_out,
            "mpu_format": self.mpu_format,
            "mpu_prefix": self.mpu_prefix,
            "mpu_dlpf": self.mpu_dlpf,
            "mpu_temp": self.mpu_temp,
            "mpu_flush_every": self.mpu_flush_every,
            "mpu_flush_seconds": self.mpu_flush_seconds,
            "mpu_fsync_each": self.mpu_fsync_each,
        }

    def _build_ui(self) -> None:
        self._build_connection_frame()
        self._build_sensor_frame()
        self._build_controls_frame()
        self._build_plot_frame()
        self._build_log_frame()
        self._build_download_frame()
        self._build_config_buttons()
        self._build_status_bar()

    def _build_connection_frame(self) -> None:
        frm = ttk.LabelFrame(self.root, text="Connection")
        frm.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        frm.columnconfigure(1, weight=1)

        labels = ["Host/IP", "Port", "Username", "Password", "Private key path"]
        vars_ = [self.host_var, self.port_var, self.user_var, self.pass_var, self.key_var]
        show_opts = [None, None, None, "*", None]
        for i, (lbl, var, show) in enumerate(zip(labels, vars_, show_opts)):
            ttk.Label(frm, text=lbl).grid(row=i, column=0, sticky="w", padx=4, pady=2)
            entry = ttk.Entry(frm, textvariable=var, show=show)
            entry.grid(row=i, column=1, sticky="ew", padx=4, pady=2)

        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=0, column=2, rowspan=3, padx=4, pady=2)
        ttk.Button(btn_frame, text="Connect", command=self.connect).grid(row=0, column=0, pady=2, sticky="ew")
        ttk.Button(btn_frame, text="Disconnect", command=self.disconnect).grid(row=1, column=0, pady=2, sticky="ew")

        ttk.Label(frm, textvariable=self.status_var, foreground="blue").grid(
            row=3, column=2, padx=4, pady=2, sticky="e"
        )

    def _build_sensor_frame(self) -> None:
        frm = ttk.LabelFrame(self.root, text="Sensor setup")
        frm.grid(row=1, column=0, sticky="ew", padx=8, pady=6)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Preset").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        preset_combo = ttk.Combobox(frm, textvariable=self.preset_var, values=list(self.presets.keys()), state="readonly", width=40)
        preset_combo.grid(row=0, column=1, padx=4, pady=2, sticky="ew")
        ttk.Button(frm, text="Apply preset", command=self.apply_selected_preset).grid(row=0, column=2, padx=4, pady=2, sticky="w")

        ttk.Label(frm, text="Select sensor").grid(row=1, column=0, padx=4, pady=2, sticky="w")
        ttk.Radiobutton(frm, text="Single ADXL203 (ADS1115)", variable=self.sensor_var, value="adxl", command=self._show_sensor_frame).grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(frm, text="Multi MPU6050 (1–3 sensors)", variable=self.sensor_var, value="mpu", command=self._show_sensor_frame).grid(row=1, column=2, sticky="w")

        self.sensor_container = ttk.Frame(frm)
        self.sensor_container.grid(row=2, column=0, columnspan=3, sticky="ew", padx=4, pady=4)
        self.sensor_container.columnconfigure(1, weight=1)

        self.adxl_frame = self._build_adxl_frame(self.sensor_container)
        self.mpu_frame = self._build_mpu_frame(self.sensor_container)
        self._show_sensor_frame()

    def _build_adxl_frame(self, parent) -> ttk.Frame:
        frm = ttk.Frame(parent)
        fields = [
            ("Script path", self.adxl_script),
            ("Rate (Hz)", self.adxl_rate),
            ("Channels", self.adxl_channels, ["x", "y", "both"]),
            ("Duration (s)", self.adxl_duration),
            ("Output dir", self.adxl_out),
            ("Addr", self.adxl_addr),
            ("Map", self.adxl_map),
            ("Calibrate", self.adxl_calibrate),
            ("LP cut (Hz)", self.adxl_lp_cut),
        ]
        row = 0
        for label, var, *rest in fields:
            ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
            if rest:
                combo = ttk.Combobox(frm, textvariable=var, values=rest[0], state="readonly")
                combo.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            else:
                entry = ttk.Entry(frm, textvariable=var)
                entry.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            row += 1
        return frm

    def _build_mpu_frame(self, parent) -> ttk.Frame:
        frm = ttk.Frame(parent)
        combos = {
            "Channels": (self.mpu_channels, ["acc", "gyro", "both", "default"]),
            "Format": (self.mpu_format, ["csv", "jsonl"]),
        }
        fields = [
            ("Script path", self.mpu_script),
            ("Rate (Hz)", self.mpu_rate),
            ("Sensors", self.mpu_sensors),
            ("Channels", self.mpu_channels),
            ("Duration (s)", self.mpu_duration),
            ("Samples", self.mpu_samples),
            ("Output dir", self.mpu_out),
            ("Format", self.mpu_format),
            ("Prefix", self.mpu_prefix),
            ("DLPF (0-6)", self.mpu_dlpf),
            ("Flush every", self.mpu_flush_every),
            ("Flush seconds", self.mpu_flush_seconds),
        ]
        row = 0
        for label, var in fields:
            ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
            if label in combos:
                combo = ttk.Combobox(frm, textvariable=var, values=combos[label][1], state="readonly")
                combo.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            else:
                entry = ttk.Entry(frm, textvariable=var)
                entry.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            row += 1

        ttk.Checkbutton(frm, text="Temp", variable=self.mpu_temp).grid(row=row, column=0, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(frm, text="Fsync each flush", variable=self.mpu_fsync_each).grid(row=row, column=1, sticky="w", padx=4, pady=2)
        row += 1
        return frm

    def _build_controls_frame(self) -> None:
        frm = ttk.Frame(self.root)
        frm.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        frm.columnconfigure(1, weight=1)
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=0, column=0, sticky="w")
        ttk.Button(btn_frame, text="Start recording", command=self.start_recording).grid(row=0, column=0, padx=4, pady=2, sticky="w")
        ttk.Button(btn_frame, text="Stop recording", command=self.stop_recording).grid(row=0, column=1, padx=4, pady=2, sticky="w")

        run_frame = ttk.LabelFrame(frm, text="Run mode / Live plot")
        run_frame.grid(row=0, column=1, sticky="ew", padx=4)
        run_frame.columnconfigure(1, weight=1)
        ttk.Label(run_frame, text="Run mode").grid(row=0, column=0, padx=4, pady=2, sticky="w")
        modes = ["Record only", "Record + live plot", "Live plot only (no-record)"]
        ttk.Combobox(run_frame, textvariable=self.run_mode_var, values=modes, state="readonly").grid(
            row=0, column=1, padx=4, pady=2, sticky="ew"
        )
        ttk.Label(run_frame, text="Stream every Nth sample").grid(row=1, column=0, padx=4, pady=2, sticky="w")
        try:
            stream_spin = ttk.Spinbox(run_frame, from_=1, to=1000, textvariable=self.stream_every_var, width=8)
        except Exception:
            stream_spin = ttk.Entry(run_frame, textvariable=self.stream_every_var, width=8)
        stream_spin.grid(row=1, column=1, padx=4, pady=2, sticky="w")

    def _build_plot_frame(self) -> None:
        frm = ttk.LabelFrame(self.root, text="Live plot")
        frm.grid(row=3, column=0, sticky="ew", padx=8, pady=6)
        frm.columnconfigure(0, weight=1)
        self.fig = Figure(figsize=(6, 2.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Value")
        self.ax.grid(True)
        (self.line,) = self.ax.plot([], [], lw=1.2)
        self.canvas = FigureCanvasTkAgg(self.fig, master=frm)
        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.grid(row=0, column=0, sticky="ew")

    def _build_log_frame(self) -> None:
        frm = ttk.LabelFrame(self.root, text="Remote log output")
        frm.grid(row=4, column=0, sticky="nsew", padx=8, pady=6)
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(frm, height=18)
        self.log_text.grid(row=0, column=0, sticky="nsew")

    def _build_download_frame(self) -> None:
        frm = ttk.LabelFrame(self.root, text="Download newest files")
        frm.grid(row=5, column=0, sticky="ew", padx=8, pady=6)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Remote output dir").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(frm, textvariable=self.remote_download_dir).grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        ttk.Label(frm, text="Local destination").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(frm, textvariable=self.local_download_dir).grid(row=1, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(frm, text="Download newest files", command=self.download_newest).grid(row=0, column=2, rowspan=2, padx=4, pady=2)
        self.open_folder_btn = ttk.Button(frm, text="Open local folder", command=self.open_local_folder, state="disabled")
        self.open_folder_btn.grid(row=0, column=3, rowspan=2, padx=4, pady=2)
        ttk.Label(frm, text="Newest = latest 5 files by mtime in the folder").grid(row=2, column=0, columnspan=4, sticky="w", padx=4, pady=2)

    def _build_config_buttons(self) -> None:
        frm = ttk.Frame(self.root)
        frm.grid(row=6, column=0, sticky="e", padx=8, pady=4)
        ttk.Button(frm, text="Save config", command=self.save_config).grid(row=0, column=0, padx=4)
        ttk.Button(frm, text="Load config", command=self.load_config).grid(row=0, column=1, padx=4)

    def _build_status_bar(self) -> None:
        frm = ttk.Frame(self.root)
        frm.grid(row=7, column=0, sticky="ew", padx=8, pady=4)
        frm.columnconfigure(2, weight=1)
        ttk.Label(frm, textvariable=self.ssh_status_var).grid(row=0, column=0, sticky="w", padx=4)
        ttk.Label(frm, textvariable=self.run_status_var).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(frm, textvariable=self.download_status_var).grid(row=0, column=2, sticky="e", padx=4)

    def _show_sensor_frame(self) -> None:
        for child in self.sensor_container.winfo_children():
            child.grid_forget()
        if self.sensor_var.get() == "adxl":
            self.adxl_frame.grid(row=0, column=0, sticky="ew")
        else:
            self.mpu_frame.grid(row=0, column=0, sticky="ew")
        self._sync_remote_download_dir()

    def log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {text}\n")
        self.log_text.see(tk.END)

    def connect(self) -> None:
        thread = threading.Thread(target=self._connect_worker, daemon=True)
        thread.start()

    def _connect_worker(self) -> None:
        host = self.host_var.get().strip()
        user = self.user_var.get().strip()
        display_user = user or "user"
        self.status_var.set("Connecting...")
        self._set_status_value(self.ssh_status_var, f"SSH: Connecting to {display_user}@{host}")
        try:
            self.manager.connect(
                host,
                int(self.port_var.get() or 22),
                user,
                self.pass_var.get(),
                self.key_var.get().strip() or None,
            )
            self.status_var.set("Connected")
            self._set_status_value(self.ssh_status_var, f"SSH: Connected to {display_user}@{host}")
            self.log(f"Connected to {display_user}@{host}")
        except Exception as exc:
            self.status_var.set("Error")
            self._set_status_value(self.ssh_status_var, "SSH: Disconnected")
            messagebox.showerror("Connection failed", str(exc))
            self.log(f"Connection error: {exc}")

    def disconnect(self) -> None:
        thread = threading.Thread(target=self._disconnect_worker, daemon=True)
        thread.start()

    def _disconnect_worker(self) -> None:
        try:
            self.manager.disconnect()
            self.status_var.set("Disconnected")
            self._set_status_value(self.ssh_status_var, "SSH: Disconnected")
            self.log("Disconnected")
        except Exception as exc:
            self.status_var.set("Error")
            self.log(f"Disconnect error: {exc}")

    def build_command(self) -> tuple[str, str]:
        run_mode = self.run_mode_var.get()
        try:
            stream_every = max(1, int(self.stream_every_var.get() or 1))
        except Exception:
            stream_every = 1
        if self.sensor_var.get() == "adxl":
            remote_adxl_path = self.adxl_script.get().strip()
            rate = self.adxl_rate.get().strip()
            channels = self.adxl_channels.get()
            remote_out = self.adxl_out.get().strip()
            cmd_parts = [
                "python3",
                remote_adxl_path,
                "--rate",
                rate,
                "--channels",
                channels,
                "--out",
                remote_out,
            ]
            duration = self.adxl_duration.get().strip()
            if duration:
                cmd_parts += ["--duration", duration]
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

            cmd = " ".join(cmd_parts)
            script_name = os.path.basename(remote_adxl_path) or "adxl203_ads1115_logger.py"
        else:
            remote_mpu_path = self.mpu_script.get().strip()
            rate = self.mpu_rate.get().strip()
            sensors_str = self.mpu_sensors.get().strip()
            channels = self.mpu_channels.get()
            remote_out = self.mpu_out.get().strip()
            fmt = self.mpu_format.get()
            prefix = self.mpu_prefix.get().strip()
            dlpf = self.mpu_dlpf.get().strip()
            cmd_parts = [
                "python3",
                remote_mpu_path,
                "--rate",
                rate,
                "--sensors",
                sensors_str,
                "--channels",
                channels,
                "--out",
                remote_out,
                "--format",
                fmt,
            ]
            if prefix:
                cmd_parts += ["--prefix", prefix]
            if dlpf:
                cmd_parts += ["--dlpf", dlpf]
            duration = self.mpu_duration.get().strip()
            if duration:
                cmd_parts += ["--duration", duration]
            samples = self.mpu_samples.get().strip()
            if samples:
                cmd_parts += ["--samples", samples]
            flush_every = self.mpu_flush_every.get().strip()
            if flush_every:
                cmd_parts += ["--flush-every", flush_every]
            flush_seconds = self.mpu_flush_seconds.get().strip()
            if flush_seconds:
                cmd_parts += ["--flush-seconds", flush_seconds]
            if self.mpu_temp.get():
                cmd_parts.append("--temp")
            if self.mpu_fsync_each.get():
                cmd_parts.append("--fsync-each-flush")

            if run_mode in ("Record + live plot", "Live plot only (no-record)"):
                if run_mode == "Live plot only (no-record)":
                    cmd_parts.append("--no-record")
                cmd_parts.append("--stream-stdout")
                cmd_parts += ["--stream-every", str(stream_every)]
                cmd_parts += ["--stream-fields", "ax,ay,gz"]

            cmd = " ".join(cmd_parts)
            script_name = os.path.basename(remote_mpu_path) or "mpu6050_multi_logger.py"
        return cmd, script_name

    def _get_current_remote_out_dir(self) -> str:
        """Return the remote --out dir for the currently selected sensor."""
        return self.adxl_out.get().strip() if self.sensor_var.get() == "adxl" else self.mpu_out.get().strip()

    def _validate_params(self) -> bool:
        """Basic validation before launching a run."""
        sensor = self.sensor_var.get()
        rate_var = self.adxl_rate if sensor == "adxl" else self.mpu_rate
        out_dir = self._get_current_remote_out_dir()
        try:
            rate_val = float(rate_var.get().strip())
            if rate_val <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid rate", "Rate must be a positive number.")
            return False
        if not out_dir:
            messagebox.showerror("Missing output folder", "Remote output folder (--out) is required.")
            return False
        if sensor == "mpu":
            sensors_raw = self.mpu_sensors.get().strip()
            if not sensors_raw:
                messagebox.showerror("Invalid sensors", "Sensors must be a comma-separated list of 1, 2, or 3.")
                return False
            try:
                sensors = [int(item.strip()) for item in sensors_raw.split(",") if item.strip()]
            except ValueError:
                messagebox.showerror("Invalid sensors", "Sensors must be a comma-separated list of 1, 2, or 3.")
                return False
            sensors_set = set(sensors)
            if not sensors_set or not sensors_set.issubset({1, 2, 3}):
                messagebox.showerror("Invalid sensors", "Sensors must be a subset of {1,2,3}, e.g. 1,2 or 2,3.")
                return False
        return True

    def start_recording(self) -> None:
        if not self.manager.is_connected():
            messagebox.showerror("Not connected", "Connect to the Pi first.")
            return
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Already running", "A recording is already running.")
            return
        if not self._validate_params():
            return
        command, script_name = self.build_command()
        self.current_sensor_type = self.sensor_var.get()
        self.first_ts_ns = None
        self.plot_time.clear()
        self.plot_value.clear()
        while not self.plot_queue.empty():
            try:
                self.plot_queue.get_nowait()
            except queue.Empty:
                break
        remote_out = self._get_current_remote_out_dir()
        local_out = self.local_download_dir.get().strip()
        # Stash per-run info so the background thread can snapshot and later auto-download.
        self.current_run_context = RemoteRunContext(
            sensor_type=self.sensor_var.get(),
            command=command,
            remote_out_dir=remote_out,
            local_out_dir=local_out,
            start_snapshot={},
        )
        self.stop_event.clear()
        self.log(f"Starting: {command}")
        sensor_label = "ADXL" if self.sensor_var.get() == "adxl" else "MPU6050"
        self._update_run_status(f"Run: Running {sensor_label}")
        self.worker_thread = threading.Thread(
            target=self._run_remote_command, args=(command, script_name, self.current_run_context), daemon=True
        )
        self.worker_thread.start()

    def _stdout_reader_thread(self, stream) -> None:
        while True:
            raw_line = stream.readline()
            if not raw_line:
                break
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode(errors="ignore")
            line = raw_line.rstrip("\n")
            self.log_queue.put(line)
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "timestamp_ns" in obj:
                    self.plot_queue.put(obj)
            except json.JSONDecodeError:
                continue

    def _stderr_reader_thread(self, stream) -> None:
        while True:
            raw_line = stream.readline()
            if not raw_line:
                break
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode(errors="ignore")
            line = raw_line.rstrip("\n")
            if line:
                self.log_queue.put(f"ERR: {line}")

    def _run_remote_command(self, command: str, script_name: str, ctx: RemoteRunContext) -> None:
        """
        Background thread workflow:
        start button -> snapshot remote dir -> stream command output -> when process ends,
        diff folders and pull down the new files -> log messages through the queue.
        """
        try:
            # Capture snapshot of remote output dir before launching the run.
            ctx.start_snapshot = self._snapshot_remote_dir(ctx.remote_out_dir)
            self.log_queue.put(
                f"Snapshot captured: {len(ctx.start_snapshot)} item(s) in {ctx.remote_out_dir}"
            )
            channel, stdout, stderr = self.manager.exec_command_stream(command)
            self.current_channel = channel
            out_thread = threading.Thread(target=self._stdout_reader_thread, args=(stdout,), daemon=True)
            err_thread = threading.Thread(target=self._stderr_reader_thread, args=(stderr,), daemon=True)
            out_thread.start()
            err_thread.start()
            while not channel.exit_status_ready():
                if self.stop_event.is_set():
                    break
                time.sleep(0.1)
            if channel.exit_status_ready():
                try:
                    exit_status = channel.recv_exit_status()
                except Exception:
                    exit_status = -1
            else:
                exit_status = -1
            out_thread.join(timeout=1.0)
            err_thread.join(timeout=1.0)
            self.log_queue.put(f"Command finished with status {exit_status}")
            self._handle_run_finished(exit_status, ctx)
        except Exception as exc:
            self.log_queue.put(f"Run error: {exc}")
        finally:
            self.current_channel = None
            self.stop_event.set()
            self._update_run_status("Run: Idle")

    def _snapshot_remote_dir(self, remote_dir: str) -> Dict[str, float]:
        """List the remote dir and return filename->mtime, swallowing errors."""
        if not remote_dir:
            self.log_queue.put("No remote output dir configured; snapshot skipped.")
            return {}
        try:
            return self.manager.listdir_with_mtime(remote_dir)
        except Exception as exc:
            self.log_queue.put(f"Snapshot error: {exc}")
            return {}

    def _list_remote_dir_with_mtime(self, remote_dir: str) -> Dict[str, float]:
        if not self.manager.is_connected():
            raise RuntimeError("Not connected")
        return self.manager.listdir_with_mtime(remote_dir)

    def _handle_run_finished(self, exit_status: int, ctx: Optional[RemoteRunContext]) -> None:
        # Runs inside the background worker thread once the remote process ends.
        if not ctx:
            self.log_queue.put("Run finished but context missing; skipping auto-download.")
            return
        self._download_new_files_for_run(ctx)

    def stop_recording(self) -> None:
        if not self.manager.is_connected():
            return
        self._update_run_status("Run: Stopping...")
        self.stop_event.set()
        if self.current_channel:
            try:
                self.current_channel.close()
            except Exception:
                pass
        thread = threading.Thread(target=self._pkill_worker, daemon=True)
        thread.start()

    def _pkill_worker(self) -> None:
        _, script_name = self.build_command()
        pattern = script_name
        try:
            out, err, status = self.manager.exec_quick(f"pkill -f {pattern}")
            self.log(f"Stop command issued (status {status}).")
            if err:
                self.log(f"pkill stderr: {err.strip()}")
        except Exception as exc:
            self.log(f"Stop error: {exc}")

    def _download_new_files_for_run(self, ctx: RemoteRunContext) -> None:
        """
        After a run ends, diff the remote folder against the start snapshot and pull new files.
        Runs inside the background thread so the Tk mainloop never blocks.
        """
        if not ctx.remote_out_dir:
            self.log_queue.put("Remote output dir empty; skipping auto-download.")
            self._update_download_status("Last download: skipped (no remote dir)")
            return
        self._update_download_status("Last download: in progress...")
        try:
            latest = self._list_remote_dir_with_mtime(ctx.remote_out_dir)
        except Exception as exc:
            self._queue_error_message(f"Auto-download listing failed: {exc}")
            self._update_download_status("Last download: error – see log")
            return

        new_files = []
        for name, mtime in latest.items():
            prev_mtime = ctx.start_snapshot.get(name)
            if prev_mtime is None or mtime > prev_mtime:
                new_files.append((name, mtime))

        if not new_files:
            self.log_queue.put("No new files to download after run.")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self._update_download_status(f"Last download: no new files at {timestamp}")
            return

        new_files.sort(key=lambda item: item[1])  # download oldest-to-newest from this run
        self.log_queue.put(f"Run finished, downloading {len(new_files)} new file(s)...")
        downloaded = 0
        for name, _ in new_files:
            remote_path = f"{ctx.remote_out_dir.rstrip('/')}/{name}"
            local_path = os.path.join(ctx.local_out_dir, name)
            try:
                self.manager.download_file(remote_path, local_path)
                self.log_queue.put(f"Downloaded {name} to {local_path}")
                downloaded += 1
            except Exception as exc:
                self._queue_error_message(f"Auto-download failed for {name}: {exc}")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        if downloaded == len(new_files):
            self._update_download_status(f"Last download: {downloaded} file(s) at {timestamp}")
        else:
            self._update_download_status("Last download: error – see log")
        self._schedule_open_folder_state_refresh()

    def _queue_error_message(self, text: str) -> None:
        """Log an error and surface it in the UI without touching Tk from worker threads."""
        self.log_queue.put(f"Error: {text}")
        self.root.after(0, lambda: messagebox.showerror("Error", text))

    def download_newest(self) -> None:
        if not self.manager.is_connected():
            messagebox.showerror("Not connected", "Connect before downloading.")
            self._update_download_status("Last download: not connected")
            return
        thread = threading.Thread(target=self._download_worker, daemon=True)
        thread.start()

    def _download_worker(self) -> None:
        remote_dir = self.remote_download_dir.get().strip()
        local_dir = self.local_download_dir.get().strip()
        self._update_download_status("Last download: in progress...")
        try:
            entries = self.manager.list_dir(remote_dir)
            # Heuristic: sort by modification time and pick the latest 5 files.
            entries = sorted(entries, key=lambda e: e.st_mtime, reverse=True)[:5]
            if not entries:
                self.log_queue.put("No files found to download.")
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                self._update_download_status(f"Last download: no files at {timestamp}")
                return
            for entry in entries:
                remote_path = f"{remote_dir.rstrip('/')}/{entry.filename}"
                local_path = os.path.join(local_dir, entry.filename)
                self.manager.download_file(remote_path, local_path)
                self.log_queue.put(f"Downloaded {entry.filename} to {local_path}")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self._update_download_status(f"Last download: {len(entries)} file(s) at {timestamp}")
            self._schedule_open_folder_state_refresh()
        except Exception as exc:
            self.log_queue.put(f"Download error: {exc}")
            self._update_download_status("Last download: error – see log")

    def open_local_folder(self) -> None:
        folder = self.local_download_dir.get().strip()
        if not folder:
            messagebox.showerror("Open folder", "Local download folder is not set.")
            return
        if not os.path.isdir(folder):
            messagebox.showerror("Open folder", "Local download folder does not exist yet.")
            self.log(f"Cannot open folder; path not found: {folder}")
            self._update_open_folder_button_state()
            return
        try:
            subprocess.Popen(["explorer", folder])
        except Exception as exc:
            messagebox.showerror("Open folder", f"Could not open folder: {exc}")
            self.log(f"Failed to open folder {folder}: {exc}")

    def save_config(self) -> None:
        cfg = {
            "host": self.host_var.get(),
            "port": self.port_var.get(),
            "user": self.user_var.get(),
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
            self.log("Config saved.")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def load_config(self) -> None:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.host_var.set(cfg.get("host", self.host_var.get()))
            self.port_var.set(cfg.get("port", self.port_var.get()))
            self.user_var.set(cfg.get("user", self.user_var.get()))
            self.pass_var.set(cfg.get("password", ""))
            self.key_var.set(cfg.get("key", ""))
            self.adxl_script.set(cfg.get("adxl_script", self.adxl_script.get()))
            self.adxl_out.set(cfg.get("adxl_out", self.adxl_out.get()))
            self.mpu_script.set(cfg.get("mpu_script", self.mpu_script.get()))
            self.mpu_out.set(cfg.get("mpu_out", self.mpu_out.get()))
            self.local_download_dir.set(cfg.get("local_download", self.local_download_dir.get()))
            self.log("Config loaded.")
            self._sync_remote_download_dir()
            self._update_open_folder_button_state()
        except FileNotFoundError:
            messagebox.showinfo("No config", "Config file not found.")
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc))

    def _load_config_if_exists(self) -> None:
        if os.path.exists(CONFIG_FILE):
            try:
                self.load_config()
            except Exception:
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
                sensor_type = self.current_sensor_type
                value = obj.get("x_lp") if sensor_type == "adxl" else obj.get("ax")
                if value is None:
                    continue
                self.plot_time.append(t_s)
                self.plot_value.append(value)
        except queue.Empty:
            pass

        if self.plot_time:
            self.line.set_data(list(self.plot_time), list(self.plot_value))
            self.ax.relim()
            self.ax.autoscale_view()
            self.canvas.draw_idle()

        self.root.after(50, self._update_plot)

    def _poll_queue(self) -> None:
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log(line)
        self.root.after(200, self._poll_queue)


def main() -> None:
    root = tk.Tk()
    root.geometry("800x800")
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
