# AI Prompt 06 – Configuration & Rate Selection UI

You are an AI coding assistant working on the **Sensors recording and plotting** project.
Implement the **configuration UI** and plumbing that lets the user choose:

- Sensor sampling rate (Hz).
- Stream decimation factor (`--stream-every`).
- GUI refresh mode (fixed vs adaptive) and intervals.

## Goals

- Provide a clean UI (e.g. settings dialog or sidebar) for rate selection.
- Ensure selected values are:
  - Applied to the Pi launch command.
  - Propagated to the GUI for plotting & FFT timers.

## Constraints & Design

- GUI: PySide6.
- Pi command may look like:
  - `ssh pi@host "python mpu6050_multi_logger.py --sample-rate-hz X --stream-every N --log-file /path/...jsonl"`
- Use reasonable defaults:
  - `sample_rate_hz = 500`
  - `stream_every = 5`
  - `signals_refresh_ms = 50`
  - `fft_refresh_ms = 750`

## Tasks

1. Add UI widgets (e.g. `QComboBox`, `QSpinBox`) for:
   - Sample rate (e.g. options: 100, 200, 500, 1000 Hz).
   - Stream‑every (1–20, etc.).
   - Signals refresh mode:
     - Fixed (ms spinbox).
     - Adaptive (based on stream rate).
   - FFT refresh (ms spinbox).
2. On “Start”:
   - Read user‑chosen values.
   - Build the Pi command line including `--sample-rate-hz` and `--stream-every`.
   - Launch the Pi process or SSH session.
   - Pass `stream_rate_hz = sample_rate_hz / stream_every` to `SignalsTab` and `FftTab`.
3. Configure timers:
   - For fixed mode:
     - `SignalsTab.fixed_interval_ms = signals_refresh_ms`.
   - For adaptive mode:
     - `SignalsTab.set_refresh_mode("adaptive", stream_rate_hz)`.
   - `FftTab.timer.setInterval(fft_refresh_ms)`.

## Important Code Skeleton (Python)

```python
class SettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # create controls: spin_sample_rate, spin_stream_every,
        # spin_signals_refresh, chk_adaptive, spin_fft_refresh, etc.
        # layout omitted for brevity

    def get_config(self):
        sample_rate = self.spin_sample_rate.value()
        stream_every = self.spin_stream_every.value()
        signals_refresh_ms = self.spin_signals_refresh.value()
        adaptive = self.chk_adaptive.isChecked()
        fft_refresh_ms = self.spin_fft_refresh.value()
        return {
            "sample_rate_hz": sample_rate,
            "stream_every": stream_every,
            "signals_refresh_ms": signals_refresh_ms,
            "adaptive": adaptive,
            "fft_refresh_ms": fft_refresh_ms,
        }

def start_acquisition(settings: dict):
    sample_rate = settings["sample_rate_hz"]
    stream_every = settings["stream_every"]
    effective_stream_rate = sample_rate / stream_every

    # ---- launch Pi logger ----
    cmd = [
        "ssh", "pi@host",
        "python", "mpu6050_multi_logger.py",
        f"--sample-rate-hz={sample_rate}",
        f"--stream-every={stream_every}",
        "--log-file=/tmp/mpu_log.jsonl",
    ]
    # TODO: actually start the process (subprocess.Popen, etc.)

    # ---- configure GUI ----
    if settings["adaptive"]:
        signals_tab.set_refresh_mode("adaptive", effective_stream_rate)
    else:
        signals_tab.fixed_interval_ms = settings["signals_refresh_ms"]
        signals_tab.set_refresh_mode("fixed")

    fft_tab.timer.setInterval(settings["fft_refresh_ms"])
```

## Notes for the AI

- Keep config plumbing modular; it should be easy to persist/reload settings later.
- Validate user input ranges (e.g., `stream_every >= 1`, sample rate within supported range).
