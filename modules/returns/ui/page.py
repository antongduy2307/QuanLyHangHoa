from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from modules.returns.controller import ReturnController
from modules.returns.service import ReturnsService
from modules.returns.ui.return_page import ReturnPage as ReturnPageView
from modules.settings.service import get_ui_scale_preset
from shared.widgets.ui_scale import apply_large_ui


class ReturnsPage(QWidget):
    def __init__(self, service: ReturnsService) -> None:
        super().__init__()
        controller = ReturnController(service._repository._session_factory)
        self._return_page_view = ReturnPageView(controller)

        layout = QVBoxLayout(self)
        layout.addWidget(self._return_page_view)
        self.apply_ui_scale_preset(get_ui_scale_preset())

    def apply_ui_scale_preset(self, preset: str) -> None:
        if hasattr(self._return_page_view, "apply_ui_scale_preset"):
            self._return_page_view.apply_ui_scale_preset(preset)
        apply_large_ui(self, preset)
