from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QPushButton, QTableWidget, QTableWidgetItem

from shared.formatting.money import format_money
from shared.widgets.table_helpers import configure_table_widget


class InvoiceItemsTable(QTableWidget):
    def __init__(self) -> None:
        super().__init__(0, 7)
        self.setHorizontalHeaderLabels(["Ma hang", "Ten hang", "Don vi", "So luong", "Don gia", "Thanh tien", ""])
        configure_table_widget(self)
        self._items: list[dict[str, object]] = []

    def items_payload(self) -> list[dict[str, object]]:
        return [{"product_id": item["product_id"], "unit_type": item["unit_type"], "quantity": item["quantity"]} for item in self._items]

    def total_amount(self) -> Decimal:
        return sum((Decimal(str(item["line_total"])) for item in self._items), start=Decimal("0"))

    def clear_items(self) -> None:
        self._items.clear()
        self._render()

    def add_or_merge_item(self, item: dict[str, object]) -> None:
        for existing in self._items:
            if existing["product_id"] == item["product_id"] and existing["unit_type"] == item["unit_type"]:
                existing_quantity = Decimal(str(existing["quantity"])) + Decimal(str(item["quantity"]))
                existing["quantity"] = existing_quantity
                existing["line_total"] = existing_quantity * Decimal(str(existing["unit_price"]))
                self._render()
                return
        new_item = dict(item)
        new_item["line_total"] = Decimal(str(item["quantity"])) * Decimal(str(item["unit_price"]))
        self._items.append(new_item)
        self._render()

    def remove_row_at(self, row_index: int) -> None:
        if 0 <= row_index < len(self._items):
            del self._items[row_index]
            self._render()

    def _render(self) -> None:
        self.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            self.setItem(row, 0, QTableWidgetItem(str(item["product_code_base"])))
            self.setItem(row, 1, QTableWidgetItem(str(item["product_name"])))
            unit_type = item["unit_type"]
            self.setItem(row, 2, QTableWidgetItem(unit_type.value if hasattr(unit_type, "value") else str(unit_type)))
            self.setItem(row, 3, QTableWidgetItem(str(item["quantity"])))
            self.setItem(row, 4, QTableWidgetItem(format_money(Decimal(str(item["unit_price"])))) )
            self.setItem(row, 5, QTableWidgetItem(format_money(Decimal(str(item["line_total"])))) )
            remove_button = QPushButton("Xoa")
            remove_button.clicked.connect(lambda _checked=False, index=row: self.remove_row_at(index))
            self.setCellWidget(row, 6, remove_button)
