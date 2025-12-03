from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QWidget,
)

from ...config.sampling import GuiSamplingDisplay, RECORDING_MODES, SamplingConfig


DEFAULT_DEVICE_RATE_HZ = 200.0
DEFAULT_SIGNALS_REFRESH_MS = 50
DEFAULT_FFT_REFRESH_MS = 750
DEFAULT_MODE_KEY = "high_fidelity"


@dataclass
class AcquisitionSettings:
    """Container for live acquisition knobs shared across tabs.

    This keeps the SamplingConfig (device/record/stream rates) paired with GUI
    refresh hints so :class:`SignalsTab` and :class:`FftTab` can stay in sync
    without modifying the underlying logger behaviour during the design phase.
    """
    sampling: SamplingConfig = field(
        default_factory=lambda: SamplingConfig(
            device_rate_hz=DEFAULT_DEVICE_RATE_HZ,
            mode_key=DEFAULT_MODE_KEY,
        )
    )
    signals_mode: str = "fixed"  # "fixed" or "adaptive"
    signals_refresh_ms: int = DEFAULT_SIGNALS_REFRESH_MS
    fft_refresh_ms: int = DEFAULT_FFT_REFRESH_MS

    @property
    def effective_stream_rate_hz(self) -> float:
        display = GuiSamplingDisplay.from_sampling(self.sampling)
        return float(display.stream_rate_hz)

    def as_dict(self) -> dict:
        """Convenience helper for serialization/testing."""
        return {
            "sampling": self.sampling.to_mapping()["sampling"],
            "signals_mode": str(self.signals_mode),
            "signals_refresh_ms": int(self.signals_refresh_ms),
            "fft_refresh_ms": int(self.fft_refresh_ms),
        }


class AcquisitionSettingsWidget(QWidget):
    """Small form that lets the user tune sampling/stream and refresh rates."""

    signalsModeChanged = Signal(str)
    signalsRefreshChanged = Signal(int)
    fftRefreshChanged = Signal(int)
    samplingChanged = Signal(object)  # emits SamplingConfig

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

        # Wiring
        self.device_rate_spin.valueChanged.connect(self._on_sampling_control_changed)
        self.mode_combo.currentIndexChanged.connect(self._on_sampling_control_changed)
        self.signals_mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self._update_sampling_labels()
        self._on_mode_changed()

    # ------------------------------------------------------------------ helpers
    def settings(self) -> AcquisitionSettings:
        sampling = self._build_sampling_config()
        self._sampling_config = sampling
        mode = self.signals_mode_combo.currentData() or "fixed"
        return AcquisitionSettings(
            sampling=sampling,
            signals_mode=str(mode),
            signals_refresh_ms=int(self.signals_refresh_spin.value()),
            fft_refresh_ms=int(self.fft_refresh_spin.value()),
        )

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
        self._on_mode_changed()

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

    def _on_signals_refresh_value_changed(self, value: int) -> None:
        self.signalsRefreshChanged.emit(int(value))

    def _on_fft_refresh_value_changed(self, value: int) -> None:
        self.fftRefreshChanged.emit(int(value))

    def set_signals_refresh_interval(self, interval_ms: int) -> None:
        """Update the signals refresh spin box without emitting change signals."""
        blocker = QSignalBlocker(self.signals_refresh_spin)
        self.signals_refresh_spin.setValue(int(interval_ms))

    def set_fft_refresh_interval(self, interval_ms: int) -> None:
        """Update the FFT refresh spin box without emitting change signals."""
        blocker = QSignalBlocker(self.fft_refresh_spin)
        self.fft_refresh_spin.setValue(int(interval_ms))
