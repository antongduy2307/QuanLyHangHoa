from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from modules.returns.controller import SourceInvoiceItemRow
from shared.formatting.money import format_money
from shared.widgets.numeric_inputs import SelectAllQuantityInput
from shared.widgets.table_helpers import configure_table_cell_widget, configure_table_widget


class SourceInvoiceItemsTable(QTableWidget):
    totals_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(0, 9)
        self.setHorizontalHeaderLabels([
            "Mã hàng",
            "Tên hàng",
            "Đơn vị",
            "Đã mua",
            "Đã trả",
            "Còn lại",
            "Trả lần này",
            "Đơn giá",
            "Thành tiền",
        ])
        configure_table_widget(self, "returns.source_invoice_items")
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.verticalHeader().setDefaultSectionSize(max(self.verticalHeader().defaultSectionSize(), 56))
        self.verticalHeader().setMinimumSectionSize(max(self.verticalHeader().minimumSectionSize(), 56))
        self._rows: list[SourceInvoiceItemRow] = []
        self._spinboxes: list[SelectAllQuantityInput] = []

    def load_items(self, rows: list[SourceInvoiceItemRow], initial_quantities: dict[int, Decimal] | None = None) -> None:
        self._rows = rows
        self._spinboxes = []
        initial_quantities = initial_quantities or {}
        self.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.setItem(row_index, 0, QTableWidgetItem(row.product_code_snapshot))
            self.setItem(row_index, 1, QTableWidgetItem(row.product_name_snapshot))
            self.setItem(row_index, 2, QTableWidgetItem(row.unit_type))
            self.setItem(row_index, 3, QTableWidgetItem(str(row.purchased_quantity)))
            self.setItem(row_index, 4, QTableWidgetItem(str(row.already_returned_quantity)))
            self.setItem(row_index, 5, QTableWidgetItem(str(row.remaining_returnable_quantity)))
            quantity_input = SelectAllQuantityInput()
            initial_quantity = initial_quantities.get(row.source_invoice_item_id, Decimal("0"))
            max_quantity = max(Decimal("0"), Decimal(str(row.remaining_returnable_quantity)))
            quantity_input.setRange(Decimal("0"), max_quantity)
            quantity_input.setValue(initial_quantity)
            quantity_input.valueChanged.connect(lambda _value, index=row_index: self._update_projected_total(index))
            self._spinboxes.append(quantity_input)
            configure_table_cell_widget(quantity_input, height=34)
            self.setCellWidget(row_index, 6, quantity_input)
            self.setItem(row_index, 7, QTableWidgetItem(format_money(row.unit_price)))
            self.setItem(row_index, 8, QTableWidgetItem(format_money(initial_quantity * row.unit_price)))
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


