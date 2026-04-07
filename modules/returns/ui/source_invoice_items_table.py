from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDoubleSpinBox, QTableWidget, QTableWidgetItem

from modules.returns.controller import SourceInvoiceItemRow
from shared.formatting.money import format_money
from shared.widgets.table_helpers import configure_table_widget


class SourceInvoiceItemsTable(QTableWidget):
    totals_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(0, 9)
        self.setHorizontalHeaderLabels([
            "Ma hang",
            "Ten hang",
            "Don vi",
            "Da mua",
            "Da tra",
            "Con lai",
            "Tra lan nay",
            "Don gia",
            "Thanh tien",
        ])
        configure_table_widget(self)
        self._rows: list[SourceInvoiceItemRow] = []
        self._spinboxes: list[QDoubleSpinBox] = []

    def load_items(self, rows: list[SourceInvoiceItemRow]) -> None:
        self._rows = rows
        self._spinboxes = []
        self.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.setItem(row_index, 0, QTableWidgetItem(row.product_code_snapshot))
            self.setItem(row_index, 1, QTableWidgetItem(row.product_name_snapshot))
            self.setItem(row_index, 2, QTableWidgetItem(row.unit_type))
            self.setItem(row_index, 3, QTableWidgetItem(str(row.purchased_quantity)))
            self.setItem(row_index, 4, QTableWidgetItem(str(row.already_returned_quantity)))
            self.setItem(row_index, 5, QTableWidgetItem(str(row.remaining_returnable_quantity)))
            quantity_input = QDoubleSpinBox()
            quantity_input.setDecimals(3)
            quantity_input.setRange(0, float(row.remaining_returnable_quantity))
            quantity_input.setValue(0)
            quantity_input.valueChanged.connect(lambda _value, index=row_index: self._update_projected_total(index))
            self._spinboxes.append(quantity_input)
            self.setCellWidget(row_index, 6, quantity_input)
            self.setItem(row_index, 7, QTableWidgetItem(format_money(row.unit_price)))
            self.setItem(row_index, 8, QTableWidgetItem(format_money(Decimal("0"))))
        self.totals_changed.emit()

    def selected_return_items(self) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for row, spinbox in zip(self._rows, self._spinboxes):
            quantity = Decimal(str(spinbox.value()))
            if quantity > Decimal("0"):
                payload.append({"source_invoice_item_id": row.source_invoice_item_id, "quantity": quantity})
        return payload

    def total_amount(self) -> Decimal:
        total = Decimal("0")
        for row, spinbox in zip(self._rows, self._spinboxes):
            total += Decimal(str(spinbox.value())) * row.unit_price
        return total

    def reset(self) -> None:
        self._rows = []
        self._spinboxes = []
        self.setRowCount(0)
        self.totals_changed.emit()

    def _update_projected_total(self, row_index: int) -> None:
        row = self._rows[row_index]
        spinbox = self._spinboxes[row_index]
        quantity = Decimal(str(spinbox.value()))
        line_total = quantity * row.unit_price
        self.setItem(row_index, 8, QTableWidgetItem(format_money(line_total)))
        self.totals_changed.emit()
