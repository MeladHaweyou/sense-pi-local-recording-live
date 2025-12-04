from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QWidget,
)

from sensepi.config.sampling import (
    GuiSamplingDisplay,
    RECORDING_MODES,
    SamplingConfig,
)

from ..config.acquisition_state import GuiAcquisitionConfig, SensorSelectionConfig


SignalsMode = Literal["fixed", "adaptive"]


DEFAULT_DEVICE_RATE_HZ = 200.0
DEFAULT_SIGNALS_REFRESH_MS = 50
DEFAULT_FFT_REFRESH_MS = 750
DEFAULT_MODE_KEY = "high_fidelity"


@dataclass
class AcquisitionSettings:
    """Bundle of GUI-level sampling and streaming configuration.

    This sits on top of :class:`~sensepi.config.sampling.SamplingConfig` and
    exposes the pieces that are relevant to the GUI + remote worker.
    """

    sampling: SamplingConfig = field(
        default_factory=lambda: SamplingConfig(
            device_rate_hz=DEFAULT_DEVICE_RATE_HZ,
            mode_key=DEFAULT_MODE_KEY,
        )
    )
    # Derived view of sampling for GUI labels; may start as None and is
    # populated in __post_init__.
    gui_sampling: GuiSamplingDisplay | None = None

    signals_mode: SignalsMode = "fixed"  # "fixed" or "adaptive"
    signals_refresh_ms: int = DEFAULT_SIGNALS_REFRESH_MS
    fft_refresh_ms: int = DEFAULT_FFT_REFRESH_MS
    #: When True, we record to disk but do not stream live data to the GUI.
    record_only: bool = False

    def __post_init__(self) -> None:
        # If gui_sampling is not explicitly provided, derive it from sampling.
        if self.gui_sampling is None:
            self.gui_sampling = GuiSamplingDisplay.from_sampling(self.sampling)

    @property
    def stream_rate_hz(self) -> float:
        """
        Effective streaming rate [Hz] as derived from gui_sampling.

        This is what the backend and plotting should use for stream/plot rate.
        """
        if self.gui_sampling is None:
            # Fallback; __post_init__ should normally ensure gui_sampling is set.
            display = GuiSamplingDisplay.from_sampling(self.sampling)
            return float(display.stream_rate_hz)
        return float(self.gui_sampling.stream_rate_hz)

    @property
    def effective_stream_rate_hz(self) -> float:
        return self.stream_rate_hz

    def as_dict(self) -> dict:
        """Convenience helper for serialization/testing."""
        return {
            "sampling": self.sampling.to_mapping()["sampling"],
            "signals_mode": str(self.signals_mode),
            "signals_refresh_ms": int(self.signals_refresh_ms),
            "fft_refresh_ms": int(self.fft_refresh_ms),
            "record_only": bool(self.record_only),
            "stream_rate_hz": float(self.stream_rate_hz),
        }


class AcquisitionSettingsWidget(QWidget):
    """Small form that lets the user tune sampling/stream and refresh rates."""

    signalsModeChanged = Signal(str)  # still emits the normalized mode key
    signalsRefreshChanged = Signal(int)
    fftRefreshChanged = Signal(int)
    samplingChanged = Signal(SamplingConfig)  # more specific than object
    recordOnlyChanged = Signal(bool)
    settingsChanged = Signal(AcquisitionSettings)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._sampling_config = SamplingConfig(
            device_rate_hz=DEFAULT_DEVICE_RATE_HZ,
            mode_key=DEFAULT_MODE_KEY,
        )

        form = QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # Device sampling controls
        self.device_rate_spin = QDoubleSpinBox(self)
        self.device_rate_spin.setRange(1.0, 4000.0)
        self.device_rate_spin.setDecimals(1)
        self.device_rate_spin.setSingleStep(1.0)
        self.device_rate_spin.setValue(float(self._sampling_config.device_rate_hz))
        form.addRow("Device rate [Hz]:", self.device_rate_spin)

        self.mode_combo = QComboBox(self)
        for key, mode in RECORDING_MODES.items():
            self.mode_combo.addItem(mode.label, key)
        idx = self.mode_combo.findData(self._sampling_config.mode_key)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        form.addRow("Mode:", self.mode_combo)

        self._record_rate_label = QLabel("—", self)
        self._record_rate_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.addRow("Recording rate [Hz]:", self._record_rate_label)

        self._stream_rate_label = QLabel("—", self)
        self._stream_rate_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.addRow("GUI stream [Hz]:", self._stream_rate_label)

        # Signals refresh mode + interval
        mode_row = QHBoxLayout()
        self.signals_mode_combo = QComboBox(self)
        self.signals_mode_combo.addItem("Fixed interval", "fixed")
        self.signals_mode_combo.addItem("Adaptive (follow stream rate)", "adaptive")
        mode_row.addWidget(self.signals_mode_combo)

        self.signals_refresh_spin = QSpinBox(self)
        self.signals_refresh_spin.setRange(10, 1000)
        self.signals_refresh_spin.setSingleStep(5)
        self.signals_refresh_spin.setValue(DEFAULT_SIGNALS_REFRESH_MS)
        self.signals_refresh_spin.setSuffix(" ms")
        mode_row.addWidget(self.signals_refresh_spin)
        self.signals_refresh_spin.valueChanged.connect(
            self._on_signals_refresh_value_changed
        )

        form.addRow("Signals refresh:", mode_row)

        # FFT refresh (independent timer)
        self.fft_refresh_spin = QSpinBox(self)
        self.fft_refresh_spin.setRange(100, 5000)
        self.fft_refresh_spin.setSingleStep(50)
        self.fft_refresh_spin.setValue(DEFAULT_FFT_REFRESH_MS)
        self.fft_refresh_spin.setSuffix(" ms")
        form.addRow("FFT refresh interval:", self.fft_refresh_spin)
        self.fft_refresh_spin.valueChanged.connect(
            self._on_fft_refresh_value_changed
        )

        # Record-only mode: record to disk but do not stream live data to the GUI.
        self.record_only_checkbox = QCheckBox(
            self.tr("Record only (no live streaming)"), self
        )
        self.record_only_checkbox.setChecked(False)
        self.record_only_checkbox.toggled.connect(self._on_record_only_toggled)
        form.addRow(self.record_only_checkbox)

        # Wiring
        self.device_rate_spin.valueChanged.connect(self._on_sampling_control_changed)
        self.mode_combo.currentIndexChanged.connect(self._on_sampling_control_changed)
        self.signals_mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self._update_sampling_labels()
        self._on_mode_changed()

    # ------------------------------------------------------------------ helpers
    def current_sampling_config(self) -> SamplingConfig:
        return self._build_sampling_config()

    def _current_gui_sampling_display(self) -> GuiSamplingDisplay:
        return GuiSamplingDisplay.from_sampling(self.current_sampling_config())

    def current_settings(self) -> AcquisitionSettings:
        sampling = self.current_sampling_config()
        self._sampling_config = sampling
        mode = self.signals_mode_combo.currentData() or "fixed"

        settings = AcquisitionSettings(
            sampling=sampling,
            signals_mode=str(mode),
            signals_refresh_ms=int(self.signals_refresh_spin.value()),
            fft_refresh_ms=int(self.fft_refresh_spin.value()),
            record_only=bool(self.record_only_checkbox.isChecked()),
        )
        return settings

    def settings(self) -> AcquisitionSettings:
        """Backward-compatible accessor for the current settings."""

        return self.current_settings()

    def set_settings(self, settings: AcquisitionSettings) -> None:
        """Load settings into the widget."""
        self.set_sampling_config(settings.sampling)
        mode = (
            settings.signals_mode
            if settings.signals_mode in {"fixed", "adaptive"}
            else "fixed"
        )
        idx = self.signals_mode_combo.findData(mode)
        if idx >= 0:
            self.signals_mode_combo.setCurrentIndex(idx)
        self.signals_refresh_spin.setValue(int(settings.signals_refresh_ms))
        self.fft_refresh_spin.setValue(int(settings.fft_refresh_ms))

        with QSignalBlocker(self.record_only_checkbox):
            self.record_only_checkbox.setChecked(bool(settings.record_only))
        self._on_mode_changed()

    def _on_record_only_toggled(self, checked: bool) -> None:
        """
        Update the record_only flag on settings change.

        This should trigger settingsChanged so other parts of the GUI
        can react (e.g. disable live plotting when enabled).
        """

        self.recordOnlyChanged.emit(bool(checked))
        self._emit_settings_changed()

    def set_sampling_config(self, sampling: SamplingConfig) -> None:
        """Update the sampling controls from an external config."""
        sampling = SamplingConfig(
            device_rate_hz=float(sampling.device_rate_hz),
            mode_key=str(sampling.mode_key),
        )
        self._sampling_config = sampling
        with QSignalBlocker(self.device_rate_spin):
            self.device_rate_spin.setValue(float(sampling.device_rate_hz))
        idx = self.mode_combo.findData(sampling.mode_key)
        if idx < 0:
            idx = self.mode_combo.findData(DEFAULT_MODE_KEY)
        if idx < 0:
            idx = 0
        with QSignalBlocker(self.mode_combo):
            self.mode_combo.setCurrentIndex(idx)
        self._update_sampling_labels()

    def _build_sampling_config(self) -> SamplingConfig:
        try:
            rate = float(self.device_rate_spin.value())
        except (TypeError, ValueError):
            rate = DEFAULT_DEVICE_RATE_HZ
        idx = self.mode_combo.currentIndex()
        mode_key = str(self.mode_combo.itemData(idx) or DEFAULT_MODE_KEY)
        if mode_key not in RECORDING_MODES:
            mode_key = DEFAULT_MODE_KEY
        return SamplingConfig(device_rate_hz=rate, mode_key=mode_key)

    def _on_sampling_control_changed(self, *_args) -> None:
        sampling = self._build_sampling_config()
        self._sampling_config = sampling
        self._update_sampling_labels()
        self.samplingChanged.emit(sampling)
        self._emit_settings_changed()

    def _update_sampling_labels(self) -> None:
        display = GuiSamplingDisplay.from_sampling(self._sampling_config)
        self._record_rate_label.setText(f"{display.record_rate_hz:.1f} Hz")
        self._stream_rate_label.setText(f"{display.stream_rate_hz:.1f} Hz")

    def _on_mode_changed(self) -> None:
        mode = self.signals_mode_combo.currentData()
        is_fixed = mode == "fixed"
        self.signals_refresh_spin.setEnabled(is_fixed)
        normalized = str(mode or "fixed")
        self.signalsModeChanged.emit(normalized)
        self._emit_settings_changed()

    # Convenience helper for later phases
    def current_stream_rate_hz(self) -> float:
        """
        Return the effective stream rate [Hz] shown in the GUI.
        """
        settings = self.settings()
        return float(settings.effective_stream_rate_hz)

    def current_gui_acquisition_config(
        self, sensor_selection: SensorSelectionConfig
    ) -> GuiAcquisitionConfig:
        """
        Construct a GuiAcquisitionConfig from the current UI settings
        plus the provided sensor_selection.
        """

        settings = self.current_settings()
        return GuiAcquisitionConfig(
            sampling=settings.sampling,
            stream_rate_hz=settings.stream_rate_hz,
            record_only=settings.record_only,
            sensor_selection=sensor_selection,
        )

    def _on_signals_refresh_value_changed(self, value: int) -> None:
        self.signalsRefreshChanged.emit(int(value))
        self._emit_settings_changed()

    def _on_fft_refresh_value_changed(self, value: int) -> None:
        self.fftRefreshChanged.emit(int(value))
        self._emit_settings_changed()

    def _emit_settings_changed(self) -> None:
        """Emit a fresh snapshot of the current settings."""
        self.settingsChanged.emit(self.current_settings())

    def set_signals_refresh_interval(self, interval_ms: int) -> None:
        """Update the signals refresh spin box without emitting change signals."""
        with QSignalBlocker(self.signals_refresh_spin):
            self.signals_refresh_spin.setValue(int(interval_ms))

    def set_fft_refresh_interval(self, interval_ms: int) -> None:
        """Update the FFT refresh spin box without emitting change signals."""
        with QSignalBlocker(self.fft_refresh_spin):
            self.fft_refresh_spin.setValue(int(interval_ms))
