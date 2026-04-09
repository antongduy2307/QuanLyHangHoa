from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from modules.reporting.controller import ReportingController
from modules.reporting.service import ReportingService
from modules.reporting.ui.report_page import ReportPage as ReportPageView
from shared.widgets.ui_scale import apply_large_ui


class ReportingPage(QWidget):
    def __init__(self, service: ReportingService) -> None:
        super().__init__()
        controller = ReportingController(service._repository)
        layout = QVBoxLayout(self)
        layout.addWidget(ReportPageView(controller))
        apply_large_ui(self)
