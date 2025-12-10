from __future__ import annotations

import sys
import time
from typing import Tuple

import paramiko


# ====== EDIT THESE IF NEEDED ======
PI_HOST = "192.168.0.6"
PI_USER = "verwalter"
PI_PASSWORD = "!66442200"
PI_BASE_PATH = "~/sensor"  # same as hosts.yaml base_path
LOGGER_SCRIPT = "mpu6050_multi_logger.py"
PI_CONFIG = "pi_config.yaml"
# ==================================


def _run_remote(
    ssh: paramiko.SSHClient,
    command: str,
    *,
    print_output: bool = True,
) -> Tuple[int, str, str]:
    """Run a command on the Pi and return (exit_code, stdout, stderr)."""

    print(f"\n=== Running on Pi: {command}")
    stdin, stdout, stderr = ssh.exec_command(command)

    # Wait explicitly for command to finish
    exit_status = stdout.channel.recv_exit_status()

    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")

    if print_output:
        print("--- stdout ---")
        print(out if out.strip() else "(empty)")
        print("--- stderr ---")
        print(err if err.strip() else "(empty)")
        print(f"--- exit code: {exit_status} ---")

    return exit_status, out, err


def main() -> None:
    print("=== SensePi Pi debug via SSH ===")
    print(f"Host: {PI_HOST}, user: {PI_USER}")
    print(f"Base path on Pi: {PI_BASE_PATH}")
    print()

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print("Connecting via username + password...")
        ssh.connect(
            PI_HOST,
            username=PI_USER,
            password=PI_PASSWORD,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
        )
        print("Connected OK.\n")

        # 1) Where are we and what is in ~/sensor?
        _run_remote(ssh, "pwd")
        _run_remote(ssh, f"ls -ld {PI_BASE_PATH}")
        _run_remote(ssh, f"cd {PI_BASE_PATH} && pwd && ls -l")

        # 2) Check Python & smbus2 import
        print("\n=== Check Python & smbus2 import ===")
        smbus_check = (
            "cd {base} && "
            "python3 - << 'EOF'\n"
            "try:\n"
            "    import smbus2\n"
            "    print('OK: smbus2 import worked')\n"
            "except Exception as e:\n"
            "    print('ERROR: smbus2 import failed:', e)\n"
            "EOF"
        ).format(base=PI_BASE_PATH)
        _run_remote(ssh, smbus_check)

        # 3) Check logger & config presence
        print("\n=== Check logger & pi_config.yaml existence ===")
        _run_remote(
            ssh,
            f"cd {PI_BASE_PATH} && "
            f"ls -l {LOGGER_SCRIPT} || echo '!! {LOGGER_SCRIPT} missing'",
        )
        _run_remote(
            ssh,
            f"cd {PI_BASE_PATH} && "
            f"ls -l {PI_CONFIG} || echo '!! {PI_CONFIG} missing'",
        )

        # 4) I2C device scan via logger --list
        print("\n=== Logger I2C scan: mpu6050_multi_logger.py --list ===")
        _run_remote(
            ssh,
            f"cd {PI_BASE_PATH} && python3 {LOGGER_SCRIPT} --list",
        )

        # 5) Short streaming test (what the GUI basically does)
        print("\n=== Short streaming test (stdout captured) ===")
        stream_cmd = (
            f"cd {PI_BASE_PATH} && "
            f"python3 {LOGGER_SCRIPT} "
            f"--config {PI_CONFIG} "
            f"--stream-stdout "
            f"--no-record "
            f"--stream-every 5 "
            f"--samples 50"
        )
        rc, out, err = _run_remote(ssh, stream_cmd)

        print("\n=== Summary of streaming test ===")
        print(f"Exit code: {rc}")
        # Show just first few lines of stdout for sanity
        out_lines = [ln for ln in out.splitlines() if ln.strip()]
        print(f"Stdout lines: {len(out_lines)}")
        for ln in out_lines[:5]:
            print("OUT:", ln)
        if len(out_lines) > 5:
            print("... (more lines truncated)")

        if err.strip():
            print("\nStderr (first 20 lines):")
            err_lines = err.splitlines()
            for ln in err_lines[:20]:
                print("ERR:", ln)
            if len(err_lines) > 20:
                print("... (more lines truncated)")
        else:
            print("\nStderr: (empty)")

        print("\n=== Debug finished ===")

    except Exception as exc:
        print(f"\nFATAL: SSH debug failed: {exc!r}")
    finally:
        try:
            ssh.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
