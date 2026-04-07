from __future__ import annotations

from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from modules.inventory.dto import InventoryProductDTO
from shared.widgets.table_helpers import configure_table_widget


class InventoryTable(QTableWidget):
    def __init__(self) -> None:
        super().__init__(0, 4)
        self.setHorizontalHeaderLabels(["Mã hàng", "Tên hàng", "Tồn kho", "Giá đang bật"])
        configure_table_widget(self)

    def set_items(self, items: list[InventoryProductDTO]) -> None:
        self.setRowCount(len(items))
        for row, item in enumerate(items):
            self.setItem(row, 0, QTableWidgetItem(item.product_code_base))
            self.setItem(row, 1, QTableWidgetItem(item.product_name))
            self.setItem(row, 2, QTableWidgetItem(item.on_hand_display))
            self.setItem(row, 3, QTableWidgetItem(item.enabled_price_summary))
