# SensePi (GUI) — Raspberry Pi MPU6050 recording + live view

SensePi is a desktop GUI (PySide6) that connects to a Raspberry Pi over SSH, starts the MPU6050 logger, shows live plots, and (optionally) records logs on the Pi and downloads them to your PC.

This README is for **operators/users** who just want to run the GUI.

---

## What you need

### On your PC
- Windows 10/11 (or Linux/macOS) with **Python 3.9+**
- Network access to the Raspberry Pi (same LAN)
- The SensePi project folder (clone or unzip)

### On the Raspberry Pi
- Raspberry Pi OS
- MPU6050 wired and **I2C enabled**
- SSH access (username + password)

> If the Pi already has the SensePi scripts in place, you can skip the “Deploy to Pi” section.

---

## Install on the PC (GUI)

From the project root:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Run the GUI:

```bat
python -m sensepi.gui.application
```

Optional: install as an editable package (lets you run `sensepi-gui`):

```bat
pip install -e .
sensepi-gui
```

---

## Configure your Raspberry Pi in the GUI

1. Start the GUI
2. Go to **Settings**
3. Add / edit your Pi in the **Raspberry Pi hosts** list
4. Save

The host list is stored in:

- `src/sensepi/config/hosts.yaml`

Typical fields:
- `name`: friendly name (shown in the GUI)
- `host`: IP/hostname
- `user` / `password`
- `base_path`: where the Pi scripts live (example: `/home/pi/sensor`)
- `data_dir`: where logs should be written (example: `/home/pi/logs`)
- `pi_config_path`: where the GUI uploads `pi_config.yaml` (usually `<base_path>/pi_config.yaml`)

---

## Deploy to the Pi (only if needed)

If your Pi does **not** already have the scripts, use the provided Windows deploy script:

### 1) Prerequisites
- Install **PuTTY** (you need `plink.exe` + `pscp.exe`)

### 2) Edit `deploy_pi.bat`
Open `deploy_pi.bat` and update:
- `PUTTY_DIR` (where plink/pscp live)
- `LOCAL_ROOT` (your repo path)
- `PI_USER`, `PI_HOST`, `PI_PASS`
- `REMOTE_DIR` (where files will be copied)

⚠️ **Important:** the script **wipes** the remote directory before copying. Read it before running.

### 3) Run it
Double-click `deploy_pi.bat` (or run it from a terminal).

### 4) Install Pi Python dependencies
On the Pi (SSH):

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv python3-smbus i2c-tools
# If requirements-pi.txt is not on the Pi yet, copy it from the repo root (or install the packages manually).
# Option A: use the requirements file
pip3 install --user -r requirements-pi.txt
# Option B (manual): pip3 install --user numpy smbus2 PyYAML RPi.GPIO
mkdir -p ~/logs/mpu
```

### 5) Enable I2C (if you haven’t already)
On the Pi:

```bash
sudo raspi-config
# Interface Options -> I2C -> Enable
```

---

## Using the GUI (basic workflow)

1. Go to **Live Signals**
2. Pick your Pi host
3. Click **Sync config to Pi** (in Settings) after you change sensors/rates
4. Click **Start** to begin live streaming
5. Enable **Recording** (if you want the Pi to write `.csv`/`.jsonl` files)
6. Click **Stop** when done
7. Click **Sync logs** to download new logs to your PC

---

## Where your data goes

- **On the Pi:** `<data_dir>/mpu/...`
- **On the PC (after Sync):** `data/raw/...`

(You can override the PC folders using environment variables: `SENSEPI_DATA_ROOT` and `SENSEPI_LOG_DIR`.)

---

## Troubleshooting

**SSH connection fails**
- Check the IP/hostname in Settings
- Make sure SSH is enabled on the Pi
- Confirm username/password

**No sensor data**
- Confirm I2C is enabled
- Check wiring and address (`i2cdetect -y 1`)
- Try running the logger directly on the Pi:
  ```bash
  cd <base_path>
  python3 mpu6050_multi_logger.py --list
  ```

**Plots are laggy**
- Reduce the sample rate in Settings
- Reduce the number of sensors/channels being streamed
