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
