from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from modules.returns.controller import ReturnController
from modules.returns.service import ReturnsService
from modules.returns.ui.return_page import ReturnPage as ReturnPageView


class ReturnsPage(QWidget):
    def __init__(self, service: ReturnsService) -> None:
        super().__init__()
        controller = ReturnController(service._repository._session_factory)

        layout = QVBoxLayout(self)
        layout.addWidget(ReturnPageView(controller))
