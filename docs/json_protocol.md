# SensePi JSON streaming protocol

The Raspberry Pi loggers stream one JSON object per line. Each entry includes:

- `timestamp_ns` (int): monotonic timestamp in nanoseconds.
- `t_s` (float): seconds since the run started.
- `sensor_id` (string): identifier for the sensor/logger instance.
- `ax`, `ay`, `az` (float): acceleration axes.
- Optional `gx`, `gy`, `gz` (float): gyroscope axes when present.

Example payload:

```json
{"timestamp_ns": 1712500000000000000,
 "t_s": 0.123,
 "sensor_id": "mpu6050_1",
 "ax": 0.01, "ay": -0.02, "az": 1.02,
 "gx": 0.001, "gy": 0.002, "gz": -0.001}
```

Parsers in :mod:`sensepi.sensors` validate the required fields, log warnings for
missing or malformed data, and drop invalid lines. GUI streaming components only
forward samples that successfully decode.
