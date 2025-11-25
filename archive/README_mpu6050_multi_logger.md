# mpu6050_multi_logger — Raspberry Pi Zero Multi‑MPU6050 Data Logger (no MQTT)

**Single‑file logger for up to three MPU‑6050 sensors.** Runs headless, logs locally to CSV or JSONL, and uses a drift‑corrected loop for stable sampling.

---

## Features at a glance

- Up to **three** MPU‑6050 sensors (default mapping below).
- Select sensors: `--sensors 1,2,3`
- Select channels: `--channels default|both|acc|gyro`
  - **`default` (the default):** `AX`, `AY`, and `GZ` (x/y acceleration + yaw rate)
  - `both`: all 6 axes (`AX, AY, AZ, GX, GY, GZ`)
  - `acc`: accelerometer only (`AX, AY, AZ`)
  - `gyro`: gyroscope only (`GX, GY, GZ`)
- **Time vector `t_s`** (seconds since start) in every row + `timestamp_ns`.
- Hardware rate via **SMPLRT_DIV** (DLPF on), printed and saved to metadata.
- **DLPF** selectable via `--dlpf` (0..6). Script prints approximate accel/gyro BW.
- **Optional on‑die temperature** via `--temp` (`temp_c` column).
- **Local logging only** (CSV or JSONL) with a metadata sidecar for each sensor.
- **Resilient I²C** reads + clean shutdown with per‑sensor writer thread.
- **Device scan** with `--list` for bus 0 and 1 (looks for 0x68/0x69).

> **Default mapping**
>
> - Sensor **1** → bus **1**, address **0x68**  
> - Sensor **2** → bus **1**, address **0x69**  
> - Sensor **3** → bus **0**, address **0x68**  
> Override with `--map "1:1-0x68,2:1-0x69,3:0-0x68"`

---

## Hardware & prerequisites

- Raspberry Pi (Zero/Zero 2/3/4) with **I²C enabled**.
- MPU‑6050 modules wired to I²C bus(es), with AD0 tied low (`0x68`) or high (`0x69`).  
- Pull‑ups on SDA/SCL as per your hat/board (most breakout boards include these).  
- Keep I²C at **400 kHz** Fast Mode for best performance.

### Enable I²C & install packages

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-smbus i2c-tools
pip3 install smbus2 numpy
sudo raspi-config nonint do_i2c 0    # or enable via GUI
```

### Verify devices on the bus

```bash
# Kernel scan
i2cdetect -y 1
i2cdetect -y 0

# Script scan
python3 mpu6050_multi_logger.py --list
```

You should see `0x68` and/or `0x69` on the bus(es) your sensors use.

---

## Usage

```bash
python3 mpu6050_multi_logger.py --rate HZ [options]
```

**Required**
- `--rate HZ` – target sample rate. With DLPF on, the device runs from a 1 kHz internal clock and applies `SMPLRT_DIV`. The script clamps the rate to a safe **4–1000 Hz** range and prints the actual setting.

**Common options**
- `--channels {default,both,acc,gyro}` – what to record. **Default is `default`** (= AX, AY, GZ).
- `--sensors 1,2,3` – subset of logical sensors to enable (default `1,2,3`).
- `--map "1:1-0x68,2:1-0x69,3:0-0x68"` – override default bus/address per sensor.
- `--duration SEC` or `--samples N` – stop condition (optional; otherwise Ctrl‑C).
- `--out PATH` – output folder (default `./logs`).
- `--format {csv,jsonl}` – output format (default `csv`).
- `--prefix STR` – filename prefix (default `mpu`).
- `--dlpf N` – DLPF config `0..6` (default `3`). See **DLPF** below.
- `--temp` – also log on‑die temperature (`temp_c`). Off by default.
- `--list` – scan bus 0 and 1 for 0x68/0x69 and exit.

### Channel modes & CSV headers

| Mode     | Columns (CSV header order)                                   |
|----------|---------------------------------------------------------------|
| default  | `timestamp_ns, t_s, sensor_id, ax, ay, gz`                    |
| both     | `timestamp_ns, t_s, sensor_id, ax, ay, az, gx, gy, gz`        |
| acc      | `timestamp_ns, t_s, sensor_id, ax, ay, az`                    |
| gyro     | `timestamp_ns, t_s, sensor_id, gx, gy, gz`                    |
| + `--temp` | appends `temp_c` to the selected mode                       |

For **JSONL**, each line is a JSON object with the same field names.

### File naming

One file **per sensor**:  
`{prefix}_S{sensorId}_YYYY-mm-dd_HH-MM-SS.csv` (or `.jsonl`) plus a sidecar metadata JSON: `{same}.meta.json`.

### Metadata sidecar (per sensor)

Contains (not exhaustive):  
`start_utc`, `hostname`, `sensor_id`, `bus`, `address_hex`, `who_am_i_hex`,  
`requested_rate_hz`, `clamped_rate_hz`, `dlpf_cfg`, `dlpf_accel_bw_hz`, `dlpf_gyro_bw_hz`,  
`fs_accel`, `fs_gyro`, `smplrt_div`, `device_rate_hz`, `channels`, `format`, `header`, `start_monotonic_ns`, `version`.

---

## Examples

```bash
# 1) Typical: 100 Hz, default channels (AX, AY, GZ) for sensors 1 & 2, 10 seconds
python3 mpu6050_multi_logger.py --rate 100 --sensors 1,2 --duration 10 --out ./logs

# 2) Explicit "default" channels at 200 Hz, run until Ctrl‑C
python3 mpu6050_multi_logger.py --rate 200 --channels default --out ./logs

# 3) Original full set: both acc+gyro, sensors 1 & 2, 10 seconds
python3 mpu6050_multi_logger.py --rate 100 --channels both --sensors 1,2 --duration 10 --out ./logs

# 4) Gyro‑only from sensor 3 at 200 Hz
python3 mpu6050_multi_logger.py --rate 200 --sensors 3 --channels gyro --out ./logs

# 5) Log JSONL instead of CSV
python3 mpu6050_multi_logger.py --rate 100 --channels default --format jsonl

# 6) Override bus/address map
python3 mpu6050_multi_logger.py --rate 100 --map "1:1-0x68,2:1-0x69,3:0-0x68"

# 7) Include temperature column
python3 mpu6050_multi_logger.py --rate 50 --channels default --temp --duration 5
```

---

## Timing model & the `t_s` time vector

- The logger uses a **drift‑corrected scheduler** based on `time.monotonic_ns()` and a fixed period from the **last scheduled tick** (not “now + period”), which minimizes accumulated drift.
- **`timestamp_ns`** is the capture time per‑sensor read.  
- **`t_s`** is a **continuous time vector**: `(timestamp_ns − start_monotonic_ns) / 1e9` seconds, shared across all sensors to simplify plotting and correlation.

If loop overruns occur (e.g., CPU stalls), the script logs periodic `[WARN] Overrun` messages but **does not drop data**.

---

## DLPF quick reference

DLPF reduces noise and sets group delay. `--dlpf` values map approximately to these bandwidths:

| DLPF | Gyro BW (Hz) | Accel BW (Hz) |
|------|---------------|---------------|
| 0    | 256           | 260           |
| 1    | 188           | 184           |
| 2    | 98            | 94            |
| 3    | 42–44         | 42–44         |
| 4    | 20            | 21            |
| 5    | 10            | 10            |
| 6    | 5             | 5             |

With DLPF on (`0..6`), the internal sample clock is **1 kHz** and the logger sets **`SMPLRT_DIV = (1000/Fs) − 1`** (clamped to 0..255).

---

## Data formats

### CSV (recommended for spreadsheets)

- Column order depends on `--channels` (see table above).
- Uses **SI units** by default (accel: m/s², gyro: deg/s, temperature: °C).  
  - Accel scaling: `g = raw/16384`, then `m/s² = g * 9.80665` (±2 g).  
  - Gyro scaling: `deg/s = raw/131` (±250 °/s).

### JSONL

- One JSON object per line with the same fields as CSV headers.
- Easier to stream/parse in Python and log‑processing pipelines.

---

## Troubleshooting

- **`Bus X not available`**: Bus 0 is often disabled on some Pi models. Enable it in `/boot` overlays or simply omit sensor 3, or remap with `--map` to bus 1.
- **No devices found**: Check wiring, power (2.375–3.46 V), and AD0 strap (address). Use `i2cdetect` and `--list`.
- **`OSError: [Errno 121] Remote I/O`**: Intermittent I²C glitch. The logger will continue; check pull‑ups and cable length.
- **Overruns**: Reduce `--rate`, use lower `--dlpf` BW (which allows larger `SMPLRT_DIV`), or disable other processes. Pi Zero can comfortably handle ~100–200 Hz across 2 sensors with CSV I/O.
- **CSV not growing**: Ensure the `--out` directory is writable and not on a read‑only mount. The writer thread flushes periodically; give it a second to flush or stop the logger cleanly (Ctrl‑C).

---

## Run as a `systemd` service (optional)

Create `/etc/systemd/system/mpu6050-logger.service`:

```ini
[Unit]
Description=MPU6050 multi-sensor logger
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/your_project_dir
ExecStart=/usr/bin/python3 mpu6050_multi_logger.py --rate 100 --channels default --sensors 1,2 --out /home/pi/logs
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable & start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable mpu6050-logger
sudo systemctl start mpu6050-logger
journalctl -u mpu6050-logger -f
```

---

## Quick Python analysis snippet

```python
import csv, pathlib
p = pathlib.Path("./logs")
csv_path = sorted(p.glob("mpu_S1_*.csv"))[-1]
rows = []
with open(csv_path) as f:
    r = csv.DictReader(f)
    for row in r:
        rows.append({k: float(v) if k not in ("sensor_id",) else int(v) for k, v in row.items()})
print("Loaded", len(rows), "rows. First row:", rows[0])
```

---

## Design notes / why it works well

- Uses **PLL clock = X‑gyro** for better timing stability (per datasheet) and keeps **DLPF on**.
- Schedules reads with a **monotonic, drift‑corrected** controller.
- **Per‑sensor writer thread** decouples I/O from sampling.
- Logs **actual register settings** (SMPLRT_DIV, DLPF, full‑scale ranges) in metadata for reproducibility.

---

## Changelog

- **v1.1** – Added `--channels default` (AX, AY, GZ), made it the default; added `t_s` time vector; metadata expanded; optional `--temp` logging.
- **v1.0** – Initial public version with multi‑sensor logging, CSV/JSONL output, and device scan.

---

## License

MIT (or your project’s license).

---

**Need help?** Open an issue or share a short snippet of your command, wiring, and the console output. We’ll sort it out quickly.
