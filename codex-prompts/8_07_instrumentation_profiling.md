
# Prompt: Add lightweight instrumentation & profiling hooks for live streaming and plotting

You are editing the SensePi project to **measure** where time is spent in live streaming and plotting, with minimal impact on performance.

Key files:

- `src/sensepi/remote/ssh_client.py` – SSH streaming (`exec_stream`).
- `src/sensepi/gui/tabs/tab_recorder.py` – background worker reading stream and parsing samples.
- `src/sensepi/sensors/mpu6050.py` – `parse_line`.
- `src/sensepi/gui/tabs/tab_signals.py` – live time-domain plots.
- `src/sensepi/gui/tabs/tab_fft.py` – live FFT.

## Goal

Implement a **debug mode** controlled by a simple flag (environment variable or global setting) that:

- Logs summary stats periodically:
  - Stream throughput (lines/s).
  - JSON parse time.
  - Queue ingestion time.
  - Redraw time for Signal plots and FFT.
- Optionally dumps a short `cProfile` run for a few seconds when enabled from CLI.

The goal is to keep it simple and non-invasive, so it can be left in the code but turned on only when needed.

## Tasks for you

1. **Add a small instrumentation config**

   - In a shared module (e.g., new `src/sensepi/tools/debug.py`), define:

     ```python
     import os

     DEBUG_SENSEPI = os.getenv("SENSEPI_DEBUG", "").lower() in {"1", "true", "yes"}

     def debug_enabled() -> bool:
         return DEBUG_SENSEPI
     ```

   - Optionally, add helpers like `time_block(label)` context manager, but keep it minimal.

2. **Measure streaming throughput in RecorderTab**

   In `RecorderTab` worker:

   - Around the `for` loop that consumes `lines` and calls `stream_lines`, track:

     - Total number of samples processed.
     - Time window (e.g. last 5 seconds) using `time.perf_counter()`.

   - Every ~5 seconds, if `debug_enabled()`, print a summary to stdout/stderr:

     ```python
     if debug_enabled() and (now - last_log >= 5.0):
         print(
             f"[DEBUG] stream={sensor_type} samples={total_samples} "
             f"rate≈{total_samples / (now - start_time):.1f} Hz",
             flush=True,
         )
         last_log = now
     ```

   - You can reset counters periodically.

3. **Instrument `parse_line` in mpu6050.py**

   - Add a very lightweight timing path when debug is enabled:

     ```python
     import time
     from ..tools.debug import debug_enabled

     _parse_time_acc = 0.0
     _parse_count = 0

     def parse_line(line: str) -> MpuSample | None:
         global _parse_time_acc, _parse_count
         if debug_enabled():
             t0 = time.perf_counter()
         # existing parsing logic...
         if debug_enabled():
             _parse_time_acc += time.perf_counter() - t0
             _parse_count += 1
             if _parse_count % 1000 == 0:
                 avg_us = (_parse_time_acc / max(1, _parse_count)) * 1e6
                 logger.info("mpu6050.parse_line avg %.1f µs over %d samples", avg_us, _parse_count)
         return sample
     ```

   - Make sure this overhead is negligible when debug is disabled (simple `if` guard).

4. **Measure redraw time in SignalsTab and FftTab**

   - In `SignalsTab` (as in the adaptive prompt), measure redraw time around the call to `_plot.redraw()` and store an EMA.
   - In `FftTab`, wrap `_update_fft`:

     ```python
     def _on_fft_timer(self) -> None:
         if debug_enabled():
             t0 = time.perf_counter()
             self._update_fft()
             dt = (time.perf_counter() - t0) * 1000.0
             # keep EMA or log occasionally
         else:
             self._update_fft()
     ```

   - Every N invocations, log a quick summary when `debug_enabled()`.

5. **Optional: short cProfile entry point**

   - In `main.py`, if an env var `SENSEPI_PROFILE=1` is set, wrap the Qt event loop in `cProfile`:

     ```python
     if __name__ == "__main__":
         if os.getenv("SENSEPI_PROFILE", ""):
             import cProfile, pstats, io
             pr = cProfile.Profile()
             pr.enable()
             try:
                 main()
             finally:
                 pr.disable()
                 s = io.StringIO()
                 ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
                 ps.print_stats(50)
                 print(s.getvalue())
         else:
             main()
     ```

   - Alternatively, you can add a separate script or CLI flag; keep it simple.

## Constraints

- All instrumentation must be **off by default**; enabled via env vars.
- Logging volume should be reasonable: e.g., summaries every 5–10 seconds, not per frame.
- Do not change public APIs or break existing behaviour.

## Deliverables

- New `sensepi.tools.debug` module.
- Instrumentation changes in:
  - `mpu6050.parse_line`.
  - `RecorderTab` worker.
  - `SignalsTab` redraw timer.
  - `FftTab` FFT timer.
- Optional cProfile wrapper in `main.py`.

Produce final code that can be dropped into the existing modules with only needed import adjustments.
