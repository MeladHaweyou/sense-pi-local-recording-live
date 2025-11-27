# AI Prompt 01 – Pi Sampling & Decimation Layer

You are an AI coding assistant working on the **Sensors recording and plotting** project.
Implement and integrate the **sampling + decimation layer** on the Raspberry Pi for **3× MPU6050** sensors.

## Goals

- Support sensor sampling rates from **50–1000 Hz**.
- Read **3 MPU6050** devices, timestamp each sample, and:
  - Log **full‑rate data** to disk.
  - Stream **decimated data** to STDOUT based on `--stream-every`.
- Keep CPU usage on the Pi reasonable.

## Constraints & Design

- Script: extend / modify `mpu6050_multi_logger.py`.
- Each sample must contain:
  - `sensor_id` (or similar) to identify which MPU.
  - `t_s` – nanosecond timestamp (from `time.time_ns()`).
  - Raw accelerometer + gyroscope components (e.g. `ax, ay, az, gx, gy, gz`).
- **Decimation**: stream only every N‑th sample per sensor, but still log every sample.
- Use the MPU6050’s **DLPF** (digital low‑pass filter) configuration to avoid aliasing when decimating.

## Tasks

1. Add CLI arguments:
   - `--sample-rate-hz` (50–1000).
   - `--stream-every` (int ≥ 1).
   - `--log-file` path for JSONL logging.
2. Configure each MPU6050:
   - Set sample rate and DLPF according to `--sample-rate-hz`.
3. Implement a sampling loop that:
   - Polls **all 3 sensors** each iteration.
   - Uses `time.time_ns()` to timestamp each sensor read.
   - Increments a per‑sensor sample counter.
4. For each sensor sample:
   - **Always** append to the log file.
   - **Only** print to STDOUT when `sample_count % stream_every == 0`.
   - Flush STDOUT immediately (`flush=True`).
5. Make sure the loop timing approximates the requested sample rate (simple sleep‑based loop is acceptable).

## Important Code Skeleton (Python)

Integrate / adapt this pattern into `mpu6050_multi_logger.py`:

```python
import time
import json
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-rate-hz", type=int, default=500)
    parser.add_argument("--stream-every", type=int, default=5)
    parser.add_argument("--log-file", type=str, required=True)
    args = parser.parse_args()

    sample_period_s = 1.0 / args.sample_rate_hz

    # TODO: init 3× MPU6050 devices (i2c addresses, bus, etc.)
    sensors = init_all_mpu6050()

    # Per-sensor sample counters for decimation
    sample_counters = {s.sensor_id: 0 for s in sensors}

    with open(args.log_file, "a", buffering=1) as f_log:
        next_t = time.time()
        while True:
            loop_start = time.time()
            for s in sensors:
                # ---- READ SENSOR ----
                data = s.read()  # returns dict: ax, ay, az, gx, gy, gz
                t_ns = time.time_ns()
                sid = s.sensor_id

                sample_counters[sid] += 1

                record = {
                    "sensor_id": sid,
                    "t_s": t_ns,
                    **data,
                }

                # ---- LOG FULL RATE ----
                f_log.write(json.dumps(record) + "\n")

                # ---- STREAM EVERY N-TH SAMPLE ----
                if sample_counters[sid] % args.stream_every == 0:
                    print(json.dumps(record), flush=True)

            # ---- SIMPLE TIMING CONTROL ----
            next_t += sample_period_s
            sleep_s = next_t - time.time()
            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                # We're behind schedule; reset schedule anchor
                next_t = time.time() + sample_period_s

if __name__ == "__main__":
    main()
```

## Notes for the AI

- Assume an `init_all_mpu6050()` helper exists or implement one that returns sensor objects
  with `.sensor_id` and `.read()` methods.
- Keep the implementation **simple and robust**; prioritize correctness and decimation behavior
  over micro‑optimizations.
