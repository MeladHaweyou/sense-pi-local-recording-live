# Prompt: Refactor `SignalsTab` into smaller components (behaviour unchanged)

You are working in the SensePi repository. Your task is to **refactor the live signals tab implementation** to make it easier for students to understand, while keeping behaviour identical.

Focus file:

- `src/sensepi/gui/tabs/tab_signals.py`

This file currently mixes:

- Layout construction (widgets, layouts, collapsible sections)
- Plotting setup (pyqtgraph / Matplotlib wrapper)
- Wiring to the recorder / ingest worker (queues, signals)
- Performance/decimation logic (timers, “adaptive mode”, perf HUD, etc.)

You must split this into **smaller, well-named helper classes**, but **keep the public `SignalsTab` API the same** so `MainWindow` and other code does not break.

---

## High-level plan

1. **Keep** `class SignalsTab(QWidget)` in `tab_signals.py` with the **same public signals and methods** (e.g. `start_stream_requested`, `stop_stream_requested`, `set_perf_hud_visible`, `get_time_series_window`, etc.).
2. Extract three internal helper classes inside the same file:

   - `_SignalsTabUI` – builds the widgets/layout and exposes *UI-level* signals.
   - `_SignalDataController` – pulls samples from the recorder queue and feeds the plot.
   - `_RefreshRateManager` – manages refresh timers, adaptive mode, and the performance HUD.

3. Move existing code into these helpers without rewriting logic from scratch.
4. Once the refactor works, **optionally** move the helpers into separate modules under `src/sensepi/gui/tabs/` (e.g. `signals_tab_ui.py`), but only if that’s straightforward. Behaviour must remain unchanged.

---

## Step 1 – Introduce helper classes inside `tab_signals.py`

Open `src/sensepi/gui/tabs/tab_signals.py`.

Near the top of the file (but after imports), introduce skeleton helpers:

```python
class _SignalsTabUI:
    """Builds the Live Signals tab widgets and handles basic UI wiring.

    This class is responsible for:
    - Creating and arranging Qt widgets (buttons, checkboxes, plot widget, etc.).
    - Emitting high-level UI signals when the user clicks start/stop, toggles channels, etc.
    - It does *not* know about background threads or sample queues.
    """

    # Example of UI-level signals (you can use QtCore.Signal if convenient)
    # start_clicked = Signal()
    # stop_clicked = Signal()

    def __init__(self, parent: QWidget) -> None:
        self.parent = parent

        # Create the layout in parent
        # self._root_layout = QVBoxLayout(parent)
        # ...
        # self.plot_widget = SignalPlotWidget(parent)

        # Example: connect button clicks to UI-level callbacks
        # self._btn_start.clicked.connect(self._on_start_clicked)

    # def _on_start_clicked(self) -> None:
    #     self.start_clicked.emit()
```

```python
class _SignalDataController(QObject):
    """Timer-driven bridge from the recorder sample queue to the plot widget.

    Responsibilities:
    - Own a QTimer that periodically drains the sample queue.
    - For each sample, update the plot widget and any rate counters.
    - Provide helper methods to access recent time windows for FFT/etc.
    """

    def __init__(
        self,
        plot_widget: "SignalPlotWidget",
        sample_queue,
        rate_controller,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._plot = plot_widget
        self._queue = sample_queue
        self._rate = rate_controller

        self._ingest_timer = QTimer(self)
        self._ingest_timer.timeout.connect(self._drain_samples)

    def _drain_samples(self) -> None:
        """Fetch all available samples from the queue and add them to the plot."""
        drained = []
        try:
            while True:
                drained.append(self._queue.get_nowait())
        except Exception:
            # queue.Empty or similar – nothing more to drain
            pass

        if not drained:
            return

        for sample in drained:
            # This mirrors the existing behaviour in SignalsTab._drain_samples
            self._plot.add_sample(sample)
            # Update rate counters / other side-effects as the original code did
            # (move that logic here rather than duplicating it)
            self._rate.on_sample(sample)

    # Add a method that wraps the old get_time_series_window logic:
    # def get_time_series_window(...): ...
```

```python
class _RefreshRateManager(QObject):
    """Manages plot refresh timing and the performance HUD for SignalsTab.

    Responsibilities:
    - Keep track of the configured refresh interval and mode (fixed vs adaptive).
    - Own any timers related to GUI refresh/adaptive mode.
    - Update the performance HUD label with FPS / lag information.
    """

    def __init__(
        self,
        ui: _SignalsTabUI,
        data_controller: _SignalDataController,
        rate_controller,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._ui = ui
        self._data = data_controller
        self._rate = rate_controller

        # Example: a timer that periodically recomputes HUD text
        self._hud_timer = QTimer(self)
        self._hud_timer.timeout.connect(self._update_hud)

    def _update_hud(self) -> None:
        """Update the performance HUD label based on the latest metrics."""
        # Move the logic that was previously in SignalsTab._update_perf_hud here,
        # and set the label text via `self._ui.set_perf_hud_text(...)`.
```

These are **sketches** – you must replace them with the real widgets, queues, and logic from the existing `SignalsTab`.

---

## Step 2 – Rewrite `SignalsTab.__init__` to delegate to helpers

Still in `tab_signals.py`, find `class SignalsTab(QWidget)`. Replace its constructor body with one that:

1. Stores config (as before).
2. Instantiates the helper classes.
3. Wires helper signals to the existing public SignalsTab signals.

Example:

```python
class SignalsTab(QWidget):
    start_stream_requested = Signal(bool)   # or whatever it was before
    stop_stream_requested = Signal()
    # ... any other public signals you already have

    def __init__(self, app_config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_config = app_config

        # 1) Build UI into this widget
        self._ui = _SignalsTabUI(parent=self)

        # 2) Data controller (queue + plot)
        self._data_controller = _SignalDataController(
            plot_widget=self._ui.plot_widget,
            sample_queue=self._sample_queue,
            rate_controller=self._rate_controller,
            parent=self,
        )

        # 3) Refresh manager (timers & HUD)
        self._refresh = _RefreshRateManager(
            ui=self._ui,
            data_controller=self._data_controller,
            rate_controller=self._rate_controller,
            parent=self,
        )

        # Wire UI events to the existing public SignalsTab signals
        # (Keep the same public API so MainWindow doesn't have to change.)
        self._ui.start_clicked.connect(self._on_start_clicked)
        self._ui.stop_clicked.connect(self._on_stop_clicked)

        # Any remaining initialisation (e.g. connecting to RecorderTab signals)
        # should now call small methods on _data_controller or _refresh rather than
        # manipulating timers/queues directly.
```

Then:

- Move the body of the old `_drain_samples` method into `_SignalDataController._drain_samples`.
- Move the body of any “performance HUD” update method into `_RefreshRateManager._update_hud`.
- Replace direct plot/queue operations in `SignalsTab` with calls to `self._data_controller` and `self._refresh`.

Do **not** change the public methods that other modules call (e.g. `set_perf_hud_visible`, `set_acquisition_settings`, `get_time_series_window`). Instead:

- Keep the method signatures the same.
- Delegate work to the appropriate helper.

Example:

```python
def get_time_series_window(...):
    return self._data_controller.get_time_series_window(...)
```

---

## Step 3 – Preserve external API and signals

Verify that **everything outside `tab_signals.py` still compiles and runs without modification**, e.g.:

- `MainWindow` should still connect to `signals_tab.start_stream_requested` and `signals_tab.stop_stream_requested` in the same way.
- FFT tab should still be able to call `signals_tab.get_time_series_window(...)` to get a window of data.
- Any menus or actions that call `signals_tab.set_perf_hud_visible(...)` should continue to work.

If needed, add thin wrapper methods on `SignalsTab` that forward to `_SignalsTabUI`, `_SignalDataController`, or `_RefreshRateManager`.

---

## Step 4 – Optional: Move helpers to separate modules

Once everything works and the tests pass, you **may** move the helpers into their own files for clarity:

- `src/sensepi/gui/tabs/signals_tab_ui.py`
- `src/sensepi/gui/tabs/signal_data_controller.py`
- `src/sensepi/gui/tabs/signal_refresh_manager.py`

In that case:

1. Copy the helper classes into the new files.
2. Import them in `tab_signals.py`:

   ```python
   from .signals_tab_ui import _SignalsTabUI
   from .signal_data_controller import _SignalDataController
   from .signal_refresh_manager import _RefreshRateManager
   ```

3. Ensure the public API of `SignalsTab` stays the same.

If moving files is too disruptive, keeping helpers in `tab_signals.py` is acceptable for now.

---

## Step 5 – Sanity checks

After the refactor:

1. Run the GUI and connect to a Pi (or synthetic source if available).
2. Verify that:
   - Live plots still update.
   - FFT/Spectrum tab still gets data.
   - Start/Stop/Recording controls behave the same.
   - Performance HUD (if present) still toggles and shows stats.
3. Run the test suite or lint tools if available.

The key constraint: **identical behaviour**, just a clearer internal structure.
