# Prompt 0 – Orientation / Guardrails for the dev agent

You are an AI coding agent working on a Python project with this structure:

- Tkinter SSH GUI: `main.py` (Paramiko SSH, presets, live plot).
- Pi loggers: `adxl203_ads1115_logger.py`, `mpu6050_multi_logger.py`.
- PySide6 Qt app (“Digital Twin / recorder / FFT / sonification”):
  - `to_be_integrated/app.py` – launches `ui.main_window.MainWindow`.
  - `to_be_integrated/ui/main_window.py` – tabs: `SignalsTab`, `RecorderTab`, `FFTTab`, `ModelingTab`, etc.
  - `to_be_integrated/ui/tab_signals.py` – live signals from MQTT.
  - `to_be_integrated/ui/tab_fft.py` – live FFT using `one_sided_fft` and `top_n_freqs`.
  - `to_be_integrated/ui/recorder/*` – capture & offline analysis of CSV.
  - `to_be_integrated/util/calibration.py` – `apply_global_and_scale(state, idx, y)`.
  - `to_be_integrated/core/state.py` – `AppState`, `global_cal`, etc.

Your job in the next prompts is **Phase 5 – Polishing** of a Qt‑based SSH GUI / SSH tab:

- Sensor presets (stored via JSON or `QSettings`).
- Live calibration UI using `util/calibration.apply_global_and_scale` and `SignalsTab.do_calibrate_global`.
- “Calibrate ADXL” button that calls `adxl203_ads1115_logger.py`’s `--calibrate` and/or uses a static offset on the Qt side.
- Optionally: hook SSH streaming backend into the existing FFT & sonification tabs.
- Better error handling and UX: visible SSH / Run / Stream indicators.

**Constraints / style:**

- Do **NOT** redesign the architecture. Work with existing classes and patterns.
- Prefer small, surgical edits over large rewrites.
- Keep new code PySide6‑style (Qt signals/slots, widgets, `QSettings`).
- Reuse ideas from `main.py` (Tkinter SSH GUI) but port them cleanly into Qt (no Tkinter imports).
- When adding new files, put them under `to_be_integrated/ui/` or `to_be_integrated/data/` as appropriate.
- When you need calibration, always go through `util.calibration.apply_global_and_scale` and/or existing `SignalsTab.do_calibrate_global`.
- Keep explanations short; focus on concrete code changes (functions, classes, signals, slots).

A later prompt will tell you exactly what to implement. For now, just wait for the next task description.
