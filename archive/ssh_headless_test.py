#!/usr/bin/env python3
"""
ssh_headless_test.py

Headless test of ssh_client/ssh_manager.py.

- Connects to the Raspberry Pi via SSH.
- Runs a short mpu6050_multi_logger.py job with --stream-stdout.
- Prints JSON lines from stdout as they arrive.
- Downloads the new CSV/JSONL files created by that run.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from ssh_client import (
    SSHClientManager,
    RemoteRunContext,
    MpuParams,
    RUN_MODE_RECORD_AND_LIVE,
    build_mpu_command,
)


def main() -> int:
    # Connection parameters (override via env if needed)
    host = os.environ.get("SENSE_PI_HOST", "192.168.0.6")
    port = int(os.environ.get("SENSE_PI_PORT", "22"))
    username = os.environ.get("SENSE_PI_USER", "verwalter")
    password = os.environ.get("SENSE_PI_PASSWORD", "")

    # Remote paths consistent with existing loggers
    remote_script = os.environ.get(
        "SENSE_PI_MPU_SCRIPT", "/home/verwalter/sensor/mpu6050_multi_logger.py"
    )
    remote_out_dir = os.environ.get("SENSE_PI_REMOTE_OUT", "/home/verwalter/sensor/logs")
    local_out_dir = Path(os.environ.get("SENSE_PI_LOCAL_OUT", "./logs_from_pi")).resolve()
    local_out_dir.mkdir(parents=True, exist_ok=True)

    mgr = SSHClientManager()
    print(f"Connecting to {username}@{host}:{port} ...")

    try:
        mgr.connect(host, port, username, password=password)

        params = MpuParams(
            script_path=remote_script,
            rate=100.0,
            sensors="1",
            channels="default",
            out_dir=remote_out_dir,
            duration=5.0,  # short run for testing
            fmt="csv",
            prefix="mpu_headless",
            dlpf="3",
            temp=False,
            flush_every=2000,
            flush_seconds=2.0,
            fsync_each_flush=False,
        )

        cmd, script_name = build_mpu_command(
            params,
            run_mode=RUN_MODE_RECORD_AND_LIVE,
            stream_every=10,
        )

        print(f"Command: {cmd}")
        start_snapshot = mgr.listdir_with_mtime(remote_out_dir)
        ctx = RemoteRunContext(
            command=cmd,
            script_name=script_name,
            sensor_type="mpu",
            remote_out_dir=remote_out_dir,
            local_out_dir=str(local_out_dir),
            start_snapshot=start_snapshot,
        )

        channel, stdout, stderr = mgr.exec_command_stream(ctx.command)

        print("Streaming JSON lines from stdout:")
        for raw_line in iter(stdout.readline, ""):
            if not raw_line:
                break
            line = raw_line.strip()
            print(line)
            try:
                _ = json.loads(line)
            except json.JSONDecodeError:
                pass

            if channel.exit_status_ready():
                break

        exit_status = channel.recv_exit_status()
        print(f"Remote command finished with status {exit_status}")

        # Diff remote directory and download new files
        end_snapshot = mgr.listdir_with_mtime(ctx.remote_out_dir)

        new_files = []
        for name, mtime in end_snapshot.items():
            old_mtime = ctx.start_snapshot.get(name)
            if old_mtime is None or mtime > old_mtime + 1e-6:
                new_files.append(name)

        if not new_files:
            print("No new files detected.")
            return exit_status

        print(f"Downloading {len(new_files)} new file(s) to {local_out_dir}...")
        for fname in sorted(new_files):
            remote_path = f"{ctx.remote_out_dir.rstrip('/')}/{fname}"
            local_path = local_out_dir / fname
            print(f"  {remote_path} -> {local_path}")
            mgr.download_file(remote_path, str(local_path))

        return exit_status
    finally:
        try:
            mgr.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
