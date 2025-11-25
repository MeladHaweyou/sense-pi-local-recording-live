from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

from .recorder.capture_tab import CaptureTab
from .recorder.view_csv_tab import ViewCSVTab
from .recorder.split_csv_tab import SplitCSVTab
from .recorder.fft_tab import FFTTab

from ..core.state import AppState  # existing


class RecorderTab(QWidget):
    """
    Wrapper tab that hosts four sub-tabs:
      - Capture (auto sampling; 3 sensors × 3 signals)
      - View CSV (static plotting with per-plot axis control)
      - Split CSV (preview any column; split full CSV by time)
      - FFT (load CSV, choose channel, view FFT)
    """

    def __init__(self, state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state

        tabs = QTabWidget(self)
        tabs.addTab(CaptureTab(self.state, parent=self), "Capture")
        tabs.addTab(ViewCSVTab(self.state, parent=self), "View CSV")
        tabs.addTab(SplitCSVTab(self.state, parent=self), "Split CSV")
        tabs.addTab(FFTTab(self.state, parent=self), "FFT")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        self.setLayout(layout)
