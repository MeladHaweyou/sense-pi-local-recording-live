# Prompt 3 – Add a Qt‑free `SSHStreamSource` demo script

Use this prompt with your agent after Prompts 1–2 are implemented.

---

Now add a tiny, Qt‑free demo script so I can manually verify that `SSHStreamSource` works before wiring it into the Qt tabs.

## Task – Create `to_be_integrated/ssh_stream_demo.py`

The script should:

1. Connect to the Raspberry Pi using `SSHClientManager`.
2. Create an `SSHStreamSource` bound to that manager.
3. Start an MPU stream using `MPUStreamConfig` with sensible defaults (e.g. 100 Hz, sensors `1–3`, `channels="default"`).
4. Every second, call `source.read(1.0)` and print:
   - how many samples are in `slot_0`
   - the last value of `slot_0`
   - the current `estimated_hz`
5. Stop cleanly on Ctrl+C (KeyboardInterrupt), closing the stream and SSH connection.

Use the following implementation as a starting point (I will edit host/credentials locally):

```python
# to_be_integrated/ssh_stream_demo.py
from __future__ import annotations

import time

import numpy as np

from util.ssh_client import SSHClientManager
from data.ssh_source import SSHStreamSource, MPUStreamConfig


def main() -> None:
    # TODO: adjust these for your environment
    host = "192.168.0.6"
    port = 22
    username = "verwalter"
    password = "!66442200"  # or "" if you use key auth

    ssh = SSHClientManager()
    print(f"Connecting to {username}@{host}:{port} ...")
    ssh.connect(host=host, port=port, username=username, password=password)

    source = SSHStreamSource(ssh_manager=ssh, maxlen=20000)

    cfg = MPUStreamConfig(
        script_path="/home/verwalter/sensor/mpu6050_multi_logger.py",
        rate_hz=100.0,
        sensors="1,2,3",
        channels="default",
        out_dir="/home/verwalter/sensor/logs",
        format="csv",
        stream_every=1,
        no_record=True,
    )

    print("Starting remote MPU stream...")
    source.start_mpu_stream(cfg)

    try:
        while True:
            data = source.read(1.0)  # last 1 second
            y0 = data.get("slot_0", np.empty(0, dtype=float))
            n = int(np.size(y0))
            if n > 0:
                last_val = float(y0[-1])
                print(
                    f"slot_0: n={n}, last={last_val: .3f}, "
                    f"estimated_hz={source.estimated_hz: .1f}"
                )
            else:
                print("slot_0: no samples yet (waiting for stream...)")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping stream (Ctrl+C)...")
    finally:
        source.stop()
        ssh.disconnect()
        print("Done.")


if __name__ == "__main__":
    main()
```

After this script exists, I should be able to run:

```bash
cd /path/to/project
python -m to_be_integrated.ssh_stream_demo
```

…and see live updates for `slot_0` while the remote `mpu6050_multi_logger.py` is streaming.
