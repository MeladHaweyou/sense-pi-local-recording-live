# 01-update-defaults.md

# Task: Update defaults for my Sense Pi GUI (IP, user, password, paths, multi‑MPU)

You are editing a Tkinter + Paramiko GUI in `main.py`.  
It controls a Raspberry Pi sensor logger.

I want you to:

1. Set my **real SSH defaults** (IP, username, password).
2. Make the **multi‑MPU6050** setup the default sensor.
3. Point the **remote** paths at `/home/verwalter/sensor`.
4. Point the **local** download folder at  
   `C:\Projects\sense-pi-local-recording-live\logs`.

Below are concrete code edits you should apply.

---

## 1. Update `_build_vars` connection defaults

In `class App`, find the method:

```python
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
    ...
```

Replace that **connection section** with:

```python
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
    ...
```

It’s OK (for my use) that this stores the password in plain text.

---

## 2. Make multi‑MPU6050 the default sensor mode

Still inside `_build_vars`, find the **sensor choice** block:

```python
    # Sensor choice
    self.sensor_var = tk.StringVar(value="adxl")
    self.run_mode_var = tk.StringVar(value="Record only")
    self.stream_every_var = tk.IntVar(value=5)
```

Change it to:

```python
    # Sensor choice
    # Default to multi‑MPU6050 (1–3 sensors)
    self.sensor_var = tk.StringVar(value="mpu")
    self.run_mode_var = tk.StringVar(value="Record only")
    self.stream_every_var = tk.IntVar(value=5)
```

Later in `__init__`, after `_build_ui()` is called, we already call `_switch_sensor()` via callbacks, so no extra changes are needed there for now.  
(If you see `_switch_sensor()` being called somewhere else, leave that logic intact.)

---

## 3. Point remote script + logs to `/home/verwalter/sensor`

Still in `_build_vars`, there are MPU and ADXL defaults:

```python
    # ADXL203 / ADS1115 defaults
    self.adxl_script = tk.StringVar(value="/home/pi/adxl203_ads1115_logger.py")  # TODO: adjust path
    ...
    self.adxl_out = tk.StringVar(value="/home/pi/logs-adxl")  # TODO: adjust path
    ...

    # MPU6050 defaults
    self.mpu_script = tk.StringVar(value="/home/pi/mpu6050_multi_logger.py")  # TODO: adjust path
    ...
    self.mpu_out = tk.StringVar(value="/home/pi/logs-mpu")  # TODO: adjust path
```

Change them to:

```python
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
```

---

## 4. Set local download folder to my Windows project path

Currently `_build_vars` has:

```python
    # Download vars
    default_local = os.path.expanduser(r"~/Downloads/sense-pi-logs")  # TODO: adjust Windows folder
    self.remote_download_dir = tk.StringVar(value=self.adxl_out.get())
    self.local_download_dir = tk.StringVar(value=default_local)
```

Replace that block with:

```python
    # Download vars
    # Remote logs live under /home/verwalter/sensor/logs
    self.remote_download_dir = tk.StringVar(value=self.mpu_out.get())

    # Local default on my Windows machine
    default_local = r"C:\Projects\sense-pi-local-recording-live\logs"
    self.local_download_dir = tk.StringVar(value=default_local)
```

Also make sure `_sync_remote_download_dir()` still works as:

```python
def _sync_remote_download_dir(self) -> None:
    if self.sensor_var.get() == "adxl":
        self.remote_download_dir.set(self.adxl_out.get())
    else:
        self.remote_download_dir.set(self.mpu_out.get())
```

So when the default sensor is `"mpu"`, the initial remote dir is `/home/verwalter/sensor/logs`.

---

## 5. No changes needed in `save_config` / `load_config`

Leave `save_config` and `load_config` as they are, so my edits become the **initial defaults**, but I can still override them via config.

---

## Acceptance check

After your changes, when I run `python main.py`:

- **SSH fields** show:
  - Host/IP: `192.168.0.6`
  - Port: `22`
  - Username: `verwalter`
  - Password: `!66442200`
- **Sensor selector** defaults to the “Multi MPU6050 (1–3 sensors)” radio button.
- Remote output directory (for MPU) is `/home/verwalter/sensor/logs`.
- Local download folder defaults to  
  `C:\Projects\sense-pi-local-recording-live\logs`.
- Manual “Download newest files” and the auto‑download after a run both use `/home/verwalter/sensor/logs` (remote) and my Windows logs folder (local) without errors.

Please apply these edits and return the updated `main.py` (or at least the full updated `App._build_vars` method) so I can drop it in.
