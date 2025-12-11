#!/usr/bin/env python
# debug_gui_features.py
"""
Comprehensive GUI debugger / smoke-test for SensePi.

Usage (from project root):

    python debug_gui_features.py
    python debug_gui_features.py --duration 15
    python debug_gui_features.py --static-only
    python debug_gui_features.py --no-static  # just run the Qt smoke test

What it does:

1) Static overview (no Qt, no imports from PySide6):
   - Reads src/sensepi/gui/main_window.py
   - Lists which tab_*.py modules are wired into MainWindow
   - Lists tab_*.py modules that exist but are NOT wired into MainWindow
     (good candidates for "duplicate" / experimental GUI features).

2) Qt smoke test (needs PySide6 and your normal GUI dependencies):
   - Creates the real MainWindow via sensepi.gui.application.create_app(...)
   - Starts a synthetic stream in SignalsTab (no Pi needed).
   - Exercises controls on:
       * Signals (view modes, baseline / calibration)
       * FFT (sampling rate, refresh)
       * Recordings / Offline (refresh list)
       * Settings (read host + sensors config)
       * Logs (refresh log list)
   - Runs for N seconds, prints a perf snapshot from SignalsTab and exits.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path


# --------------------------------------------------------------------------- #
# Options
# --------------------------------------------------------------------------- #


@dataclass
class SmokeOptions:
    duration_s: float = 10.0
    synthetic_rate_hz: float = 200.0
    synthetic_refresh_hz: float = 20.0
    sensor_count: int = 3


# --------------------------------------------------------------------------- #
# Static GUI overview (no Qt imports)
# --------------------------------------------------------------------------- #


def run_static_introspection(root: Path) -> None:
    """
    Print which tab_*.py modules are wired into MainWindow and which are not.

    This is a quick way to spot:
      - "live" tabs (Device/Settings/Signals/Spectrum/Recordings/Logs)
      - extra tab modules that exist in src/sensepi/gui/tabs but are not
        currently connected into MainWindow (experimental / duplicate UI).
    """
    src = root / "src"
    main_path = src / "sensepi" / "gui" / "main_window.py"
    tabs_dir = src / "sensepi" / "gui" / "tabs"

    print("=== GUI static overview ===")

    if not main_path.is_file():
        print(f"[static] main_window.py not found at {main_path}")
        return
    if not tabs_dir.is_dir():
        print(f"[static] tabs directory not found at {tabs_dir}")
        return

    text = main_path.read_text(encoding="utf-8", errors="replace")

    # e.g. from .tabs.tab_signals import SignalsTab
    used_modules = set(
        re.findall(r"from\s+\.tabs\.(tab_[a-zA-Z0-9_]+)\s+import", text)
    )

    all_tab_modules = sorted(p.stem for p in tabs_dir.glob("tab_*.py"))

    wired = [m for m in all_tab_modules if m in used_modules]
    unused = [m for m in all_tab_modules if m not in used_modules]

    print("Tabs wired into MainWindow:")
    if wired:
        for name in wired:
            print(f"  - {name}")
    else:
        print("  (none found)")

    if unused:
        print("\nTab modules present but NOT used by MainWindow")
        print("(candidates for duplicate/experimental features):")
        for name in unused:
            print(f"  - {name}")
    else:
        print("\nAll tab_*.py modules are referenced by MainWindow.")

    print("")


# --------------------------------------------------------------------------- #
# Qt smoke-test driver (imports Qt & sensepi lazily)
# --------------------------------------------------------------------------- #


def run_gui_smoke_test(root: Path, options: SmokeOptions) -> None:
    """
    Launch the real GUI, drive synthetic Signals/FFT, and touch the other tabs.
    """
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    # Import Qt + SensePi GUI only when we actually do the smoke test.
    from PySide6.QtCore import QObject, QTimer, Slot  # type: ignore
    from PySide6.QtWidgets import QApplication  # type: ignore

    from sensepi.gui.application import (  # type: ignore
        configure_matplotlib_for_realtime,
        create_app,
    )
    from sensepi.config.app_config import AppConfig  # type: ignore

    configure_matplotlib_for_realtime()
    app_config = AppConfig()
    app, window = create_app(["debug_gui_features.py"], app_config=app_config)

    class GuiSmokeDriver(QObject):
        """Owns the synthetic stream + tab exercise and shuts the app down."""

        def __init__(
            self,
            app: QApplication,
            window,
            options: SmokeOptions,
        ) -> None:
            super().__init__(window)
            self._app = app
            self._window = window
            self._options = options
            self._started = False

        @Slot()
        def start(self) -> None:
            if self._started:
                return
            self._started = True
            print("=== GUI smoke-test: starting ===")
            self._setup_synthetic_signals()

            # Give the synthetic stream a moment to produce data, then poke tabs.
            QTimer.singleShot(1000, self._exercise_tabs)
            # Stop after the requested duration.
            total_ms = int(max(1.0, self._options.duration_s) * 1000)
            QTimer.singleShot(total_ms, self._finish)

        # ------------------------- synthetic stream -------------------------

        def _setup_synthetic_signals(self) -> None:
            win = self._window
            s_tab = win.signals_tab
            print("[signals] configuring synthetic stream...")

            try:
                win._tabs.setCurrentWidget(s_tab)
            except Exception:
                pass

            # Refresh + view mode (matches how BenchmarkDriver configures it).
            try:
                s_tab.set_refresh_mode("fixed")
            except Exception as exc:
                print("  [signals] set_refresh_mode failed:", exc)

            try:
                # A default 3-of-6 view; if it fails, it's not fatal.
                s_tab.set_view_mode_preset("default3")
            except Exception:
                try:
                    s_tab.set_view_mode_by_channels(["ax", "ay", "gz"])
                except Exception as exc:
                    print("  [signals] view mode setup failed:", exc)

            try:
                s_tab.set_perf_hud_visible(True)
            except Exception:
                pass

            sensor_ids = list(
                range(1, max(1, int(self._options.sensor_count)) + 1)
            )

            # Tell SignalsTab / FftTab a stream is about to start.
            try:
                s_tab.on_stream_started()
            except Exception as exc:
                print("  [signals] on_stream_started failed:", exc)

            try:
                s_tab.start_synthetic_stream(
                    self._options.synthetic_rate_hz,
                    sensor_ids=sensor_ids,
                )
            except Exception as exc:
                print("  [signals] start_synthetic_stream failed:", exc)

            try:
                s_tab.update_stream_rate(
                    "mpu6050", self._options.synthetic_rate_hz
                )
            except Exception as exc:
                print("  [signals] update_stream_rate failed:", exc)

            # FFT expects a sampling rate and stream start.
            fft_tab = win.fft_tab
            print("[fft] informing FFT tab about stream...")
            try:
                fft_tab.set_sampling_rate_hz(self._options.synthetic_rate_hz)
                fft_tab.on_stream_started()
            except Exception as exc:
                print("  [fft] setup failed:", exc)

        # ----------------------------- tab poking -----------------------------

        @Slot()
        def _exercise_tabs(self) -> None:
            print("=== Exercising tabs ===")
            win = self._window
            self._exercise_signals_tab(win)
            self._exercise_fft_tab(win)
            self._exercise_recordings_tab(win)
            self._exercise_settings_tab(win)
            self._exercise_logs_tab(win)
            print("=== Tab exercise complete; letting stream run until finish timer ===")

        def _exercise_signals_tab(self, win) -> None:
            s_tab = win.signals_tab
            print("[signals] exercising controls...")
            try:
                win._tabs.setCurrentWidget(s_tab)
            except Exception:
                pass

            # Baseline correction + calibration
            try:
                # If the checkbox exists, toggle it.
                base_chk = getattr(s_tab, "base_correction_check", None)
                if base_chk is not None:
                    base_chk.setChecked(True)
            except Exception:
                pass

            try:
                # Private but safe to use in a debug harness.
                if hasattr(s_tab, "_on_calibrate_clicked"):
                    s_tab._on_calibrate_clicked()  # type: ignore[attr-defined]
            except Exception as exc:
                print("  [signals] calibrate failed:", exc)

            # Flip view presets to ensure plotting modes switch.
            try:
                if hasattr(s_tab, "set_view_mode_preset"):
                    s_tab.set_view_mode_preset("default3")
                    s_tab.set_view_mode_preset("all6")
            except Exception:
                pass

        def _exercise_fft_tab(self, win) -> None:
            fft_tab = win.fft_tab
            print("[fft] exercising FFT tab...")
            try:
                win._tabs.setCurrentWidget(fft_tab)
            except Exception:
                pass

            try:
                if hasattr(fft_tab, "set_refresh_interval_ms"):
                    fft_tab.set_refresh_interval_ms(250)
                # Force at least one FFT update if the helper exists.
                if hasattr(fft_tab, "_update_fft"):
                    fft_tab._update_fft()  # type: ignore[attr-defined]
            except Exception as exc:
                print("  [fft] update failed:", exc)

        def _exercise_recordings_tab(self, win) -> None:
            rec_tab = getattr(win, "recordings_tab", None)
            offline_tab = getattr(win, "offline_tab", None)
            if rec_tab is None or offline_tab is None:
                return
            print("[recordings] refreshing recordings list...")
            try:
                win._tabs.setCurrentWidget(rec_tab)
            except Exception:
                pass
            try:
                # Safe even if there are no logs; it just rebuilds the list.
                offline_tab.refresh_recordings_list()
            except Exception as exc:
                print("  [recordings] refresh_recordings_list failed:", exc)

        def _exercise_settings_tab(self, win) -> None:
            settings_tab = getattr(win, "settings_tab", None)
            if settings_tab is None:
                return
            print("[settings] reading current config...")
            try:
                win._tabs.setCurrentWidget(settings_tab)
            except Exception:
                pass

            try:
                host_cfg = settings_tab.current_host_config()
                host_name = getattr(host_cfg, "name", None) or getattr(
                    host_cfg, "host", "<?>"
                )
                print(f"  [settings] current_host_config: {host_name}")
            except Exception as exc:
                print("  [settings] current_host_config failed:", exc)

            try:
                sensor_defaults = settings_tab.sensor_defaults()
                if isinstance(sensor_defaults, dict):
                    sensors_block = sensor_defaults.get("sensors") or {}
                    print(
                        f"  [settings] sensors.yaml has {len(sensors_block)} sensor entries"
                    )
                else:
                    print(
                        f"  [settings] sensor_defaults returned {type(sensor_defaults)}"
                    )
            except Exception as exc:
                print("  [settings] sensor_defaults failed:", exc)

        def _exercise_logs_tab(self, win) -> None:
            logs_tab = getattr(win, "logs_tab", None)
            if logs_tab is None:
                return
            print("[logs] refreshing logs list...")
            try:
                win._tabs.setCurrentWidget(logs_tab)
            except Exception:
                pass

            try:
                logs_tab.refresh_log_list()
            except Exception as exc:
                print("  [logs] refresh_log_list failed:", exc)

        # ----------------------------- shutdown ------------------------------

        @Slot()
        def _finish(self) -> None:
            print("=== GUI smoke-test: finishing ===")
            win = self._window
            s_tab = win.signals_tab

            # Stop synthetic stream and notify tabs.
            try:
                s_tab.stop_synthetic_stream()
                s_tab.on_stream_stopped()
            except Exception as exc:
                print("  [signals] stop_synthetic_stream failed:", exc)

            try:
                fft_tab = win.fft_tab
                fft_tab.on_stream_stopped()
            except Exception:
                pass

            # Grab whatever perf info is available.
            try:
                if hasattr(s_tab, "get_perf_snapshot"):
                    snap = s_tab.get_perf_snapshot()
                    print("[signals] perf snapshot:", snap)
            except Exception:
                pass

            self._app.quit()

    driver = GuiSmokeDriver(app, window, options)
    window.show()
    QTimer.singleShot(0, driver.start)
    app.exec()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> None:
    root = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description="SensePi GUI feature/debug harness (static + runtime)."
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="How long to keep the synthetic stream running (seconds).",
    )
    parser.add_argument(
        "--synthetic-rate",
        type=float,
        default=200.0,
        help="Synthetic sample rate in Hz (Signals/FFT).",
    )
    parser.add_argument(
        "--sensors",
        type=int,
        default=3,
        help="Number of synthetic sensors to simulate.",
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Only run the static overview (no Qt / no GUI).",
    )
    parser.add_argument(
        "--no-static",
        action="store_true",
        help="Skip the static overview and only run the Qt smoke-test.",
    )

    args = parser.parse_args(argv)

    # 1) Static view of tabs / possible duplicates
    if not args.no_static:
        run_static_introspection(root)

    if args.static_only:
        return

    # 2) Runtime Qt smoke test
    opts = SmokeOptions(
        duration_s=float(args.duration),
        synthetic_rate_hz=float(args.synthetic_rate),
        synthetic_refresh_hz=20.0,
        sensor_count=int(args.sensors),
    )
    run_gui_smoke_test(root, opts)


if __name__ == "__main__":
    main()
