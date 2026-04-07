from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from modules.sales.controller import SalesController
from modules.sales.service import SalesService
from modules.sales.ui.sales_page import SalesPage as SalesPageView


class SalesPage(QWidget):
    def __init__(self, service: SalesService) -> None:
        super().__init__()
        controller = SalesController(service._repository._session_factory)

        layout = QVBoxLayout(self)
        layout.addWidget(SalesPageView(controller))
