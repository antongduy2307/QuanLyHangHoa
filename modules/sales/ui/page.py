from __future__ import annotations

from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from modules.returns.controller import ReturnController
from modules.returns.ui.return_page import ReturnPage as ReturnPageView
from modules.sales.controller import SalesController
from modules.sales.service import SalesService
from modules.sales.ui.sales_page import SalesPage as SalesPageView


class SalesPage(QWidget):
    def __init__(self, service: SalesService) -> None:
        super().__init__()
        controller = SalesController(service._repository._session_factory)
        return_controller = ReturnController(service._repository._session_factory)

        tabs = QTabWidget()
        tabs.addTab(SalesPageView(controller), "Bán hàng")
        tabs.addTab(ReturnPageView(return_controller), "Trả hàng")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
