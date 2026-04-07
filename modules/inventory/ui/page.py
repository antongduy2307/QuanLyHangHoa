from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from modules.inventory.controller import InventoryController
from modules.inventory.service import InventoryService
from modules.inventory.ui.product_list_view import ProductListView


class InventoryPage(QWidget):
    def __init__(self, service: InventoryService) -> None:
        super().__init__()
        controller = InventoryController(service._repository._session_factory)

        layout = QVBoxLayout(self)
        layout.addWidget(ProductListView(controller))
