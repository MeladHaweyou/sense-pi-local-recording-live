# SensePi Raspberry Pi scripts

This folder contains the lightweight logger scripts that should be copied to a Raspberry Pi. They record sensor data locally on the device and can optionally stream lines over stdout for live viewing.

## Files

- `mpu6050_multi_logger.py` – existing multi-sensor MPU6050 logger.
- `adxl203_ads1115_logger.py` – logger for the ADXL203/ADS1115 combination.
- `pi_logger_common.py` – shared helpers and configuration loading.
- `pi_config.yaml` – example configuration file for rates, channels, and paths.
- `install_pi_deps.sh` – installs Python dependencies on the Pi.
- `run_all_sensors.sh` – simple launcher for both loggers.

## Setup

On your workstation:

```bash
scp -r raspberrypi_scripts pi@<host>:/home/pi/
ssh pi@<host> "bash /home/pi/raspberrypi_scripts/install_pi_deps.sh"
```

Adjust `pi_config.yaml` to suit your hardware layout and desired sample rates before running the loggers.
