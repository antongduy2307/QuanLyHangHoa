from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHeaderView, QPushButton, QTableWidget, QTableWidgetItem

from core.config import MAX_MONEY_INPUT
from shared.widgets.numeric_inputs import SelectAllSpinBox
from shared.widgets.table_helpers import configure_table_widget


class InvoiceItemsTable(QTableWidget):
    totals_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(0, 7)
        self.setHorizontalHeaderLabels(["Mã hàng", "Tên hàng", "Đơn vị", "Số lượng", "Đơn giá", "Thành tiền", ""])
        configure_table_widget(self, "sales.invoice_items")

        self._items: list[dict[str, object]] = []
        self._syncing = False

    def items_payload(self) -> list[dict[str, object]]:
        return [
            {
                "product_id": item["product_id"],
                "unit_type": item["unit_type"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "line_total": item["line_total"],
            }
            for item in self._items
        ]

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
        quantity = Decimal(str(new_item["quantity"]))
        unit_price = Decimal(str(new_item["unit_price"]))
        new_item["line_total"] = Decimal(str(new_item.get("line_total", quantity * unit_price)))
        self._items.append(new_item)
        self._render()

    def remove_row_at(self, row_index: int) -> None:
        if 0 <= row_index < len(self._items):
            del self._items[row_index]
            self._render()

    def _render(self) -> None:
        self._syncing = True
        try:
            self.setRowCount(len(self._items))
            for row, item in enumerate(self._items):
                code_item = QTableWidgetItem(str(item["product_code_base"]))
                code_font = QFont(code_item.font())
                code_font.setBold(True)
                code_font.setPointSize(code_font.pointSize() + 1)
                code_item.setFont(code_font)
                code_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.setItem(row, 0, code_item)
                self.setItem(row, 1, QTableWidgetItem(str(item["product_name"])))
                unit_type = item["unit_type"]
                self.setItem(row, 2, QTableWidgetItem(unit_type.value if hasattr(unit_type, "value") else str(unit_type)))

                quantity_spin = SelectAllSpinBox()
                quantity_spin.setRange(1, 999999999)
                quantity_spin.setValue(int(Decimal(str(item["quantity"]))))
                quantity_spin.editingFinished.connect(lambda index=row, spin=quantity_spin: self._handle_quantity_finished(index, spin.value()))
                self.setCellWidget(row, 3, quantity_spin)

                unit_price_spin = SelectAllSpinBox()
                unit_price_spin.setRange(0, MAX_MONEY_INPUT)
                unit_price_spin.setValue(int(Decimal(str(item["unit_price"]))))
                unit_price_spin.editingFinished.connect(lambda index=row, spin=unit_price_spin: self._handle_unit_price_finished(index, spin.value()))
                self.setCellWidget(row, 4, unit_price_spin)

                line_total_spin = SelectAllSpinBox()
                line_total_spin.setRange(0, MAX_MONEY_INPUT)
                line_total_spin.setValue(int(Decimal(str(item["line_total"]))))
                line_total_spin.editingFinished.connect(lambda index=row, spin=line_total_spin: self._handle_line_total_finished(index, spin.value()))
                self.setCellWidget(row, 5, line_total_spin)

                remove_button = QPushButton("Xóa")
                remove_button.clicked.connect(lambda _checked=False, index=row: self.remove_row_at(index))
                self.setCellWidget(row, 6, remove_button)
        finally:
            self._syncing = False
        self.totals_changed.emit()

    def _handle_quantity_finished(self, row_index: int, value: int) -> None:
        if self._syncing or not (0 <= row_index < len(self._items)):
            return
        item = self._items[row_index]
        quantity = Decimal(value)
        item["quantity"] = quantity
        item["line_total"] = quantity * Decimal(str(item["unit_price"]))
        self._render()

    def _handle_unit_price_finished(self, row_index: int, value: int) -> None:
        if self._syncing or not (0 <= row_index < len(self._items)):
            return
        item = self._items[row_index]
        unit_price = Decimal(value)
        item["unit_price"] = unit_price
        item["line_total"] = Decimal(str(item["quantity"])) * unit_price
        self._render()

    def _handle_line_total_finished(self, row_index: int, value: int) -> None:
        if self._syncing or not (0 <= row_index < len(self._items)):
            return
        item = self._items[row_index]
        line_total = Decimal(value)
        quantity = Decimal(str(item["quantity"]))
        item["line_total"] = line_total
        item["unit_price"] = (line_total / quantity).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        self._render()


