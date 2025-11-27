from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QWidget,
)


DEFAULT_SAMPLE_RATE_HZ = 500
DEFAULT_STREAM_EVERY = 5
DEFAULT_SIGNALS_REFRESH_MS = 50
DEFAULT_FFT_REFRESH_MS = 750


@dataclass
class AcquisitionSettings:
    sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ
    stream_every: int = DEFAULT_STREAM_EVERY
    signals_mode: str = "fixed"  # "fixed" or "adaptive"
    signals_refresh_ms: int = DEFAULT_SIGNALS_REFRESH_MS
    fft_refresh_ms: int = DEFAULT_FFT_REFRESH_MS

    @property
    def effective_stream_rate_hz(self) -> float:
        every = max(1, int(self.stream_every))
        if self.sample_rate_hz <= 0:
            return 0.0
        return float(self.sample_rate_hz) / every

    def as_dict(self) -> dict:
        """Convenience helper for serialization/testing."""
        return {
            "sample_rate_hz": int(self.sample_rate_hz),
            "stream_every": int(self.stream_every),
            "signals_mode": str(self.signals_mode),
            "signals_refresh_ms": int(self.signals_refresh_ms),
            "fft_refresh_ms": int(self.fft_refresh_ms),
        }


class AcquisitionSettingsWidget(QWidget):
    """Small form that lets the user tune sampling/stream and refresh rates."""

    signalsModeChanged = Signal(str)
    signalsRefreshChanged = Signal(int)
    fftRefreshChanged = Signal(int)

    SAMPLE_RATE_CHOICES = (100, 200, 500, 1000)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        form = QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # Sample rate selector (combo with presets + editable field)
        self.sample_rate_combo = QComboBox(self)
        self.sample_rate_combo.setEditable(True)
        validator = QIntValidator(1, 4000, self.sample_rate_combo)
        self.sample_rate_combo.lineEdit().setValidator(validator)
        for rate in self.SAMPLE_RATE_CHOICES:
            self.sample_rate_combo.addItem(f"{rate} Hz", rate)
        self.sample_rate_combo.setCurrentText(str(DEFAULT_SAMPLE_RATE_HZ))
        self.sample_rate_combo.lineEdit().setAlignment(Qt.AlignRight)

        form.addRow("Sample rate (Hz):", self.sample_rate_combo)

        # Stream decimation (every Nth sample)
        self.stream_every_spin = QSpinBox(self)
        self.stream_every_spin.setRange(1, 100)
        self.stream_every_spin.setValue(DEFAULT_STREAM_EVERY)
        form.addRow("Stream every Nth sample:", self.stream_every_spin)

        # Derived stream rate label
        self._stream_rate_label = QLabel(self)
        self._stream_rate_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.addRow("Effective stream rate:", self._stream_rate_label)

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
        self.sample_rate_combo.currentTextChanged.connect(self._update_stream_rate_label)
        self.stream_every_spin.valueChanged.connect(self._update_stream_rate_label)
        self.signals_mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self._update_stream_rate_label()
        self._on_mode_changed()

    # ------------------------------------------------------------------ helpers
    def settings(self) -> AcquisitionSettings:
        sample_rate = self._parse_sample_rate()
        stream_every = int(self.stream_every_spin.value())
        mode = self.signals_mode_combo.currentData() or "fixed"
        return AcquisitionSettings(
            sample_rate_hz=sample_rate,
            stream_every=stream_every,
            signals_mode=str(mode),
            signals_refresh_ms=int(self.signals_refresh_spin.value()),
            fft_refresh_ms=int(self.fft_refresh_spin.value()),
        )

    def set_settings(self, settings: AcquisitionSettings) -> None:
        """Load settings into the widget."""
        self.sample_rate_combo.setCurrentText(str(int(settings.sample_rate_hz)))
        self.stream_every_spin.setValue(max(1, int(settings.stream_every)))
        mode = settings.signals_mode if settings.signals_mode in {"fixed", "adaptive"} else "fixed"
        idx = self.signals_mode_combo.findData(mode)
        if idx >= 0:
            self.signals_mode_combo.setCurrentIndex(idx)
        self.signals_refresh_spin.setValue(int(settings.signals_refresh_ms))
        self.fft_refresh_spin.setValue(int(settings.fft_refresh_ms))
        self._update_stream_rate_label()
        self._on_mode_changed()

    def _parse_sample_rate(self) -> int:
        data = self.sample_rate_combo.currentData()
        if isinstance(data, (int, float)):
            return int(data)
        text = self.sample_rate_combo.currentText().strip()
        try:
            return max(1, int(float(text)))
        except ValueError:
            return DEFAULT_SAMPLE_RATE_HZ

    def _update_stream_rate_label(self) -> None:
        settings = self.settings()
        effective = settings.effective_stream_rate_hz
        self._stream_rate_label.setText(f"{effective:.1f} Hz")

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

    def display_effective_stream_rate(self, rate_hz: float) -> None:
        """Allow external widgets to keep the derived stream-rate label in sync."""
        try:
            value = float(rate_hz)
        except (TypeError, ValueError):
            value = 0.0
        self._stream_rate_label.setText(f"{value:.1f} Hz")
