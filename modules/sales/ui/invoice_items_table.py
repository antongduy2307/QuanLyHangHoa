from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
)

from core.config import MAX_MONEY_INPUT
from core.enums import UnitType
from shared.widgets.numeric_inputs import SelectAllDecimalInput, SelectAllQuantityInput
from shared.widgets.table_helpers import configure_table_cell_widget, configure_table_widget


class InvoiceItemsTable(QTableWidget):
    totals_changed = pyqtSignal()

    def __init__(self, persistence_key: str = "sales.invoice_items") -> None:
        super().__init__(0, 7)
        self.setHorizontalHeaderLabels(["Mã hàng", "Tên hàng", "Đơn vị", "Số lượng", "Đơn giá", "Thành tiền", ""])
        self.setProperty(
            "column_minimum_widths",
            {
                0: 120,
                1: 260,
                2: 120,
                3: 120,
                4: 140,
                5: 150,
                6: 96,
            },
        )
        configure_table_widget(self, persistence_key)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.verticalHeader().setDefaultSectionSize(max(self.verticalHeader().defaultSectionSize(), 56))
        self.verticalHeader().setMinimumSectionSize(max(self.verticalHeader().minimumSectionSize(), 56))

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
                existing["stock_available"] = item.get("stock_available", existing.get("stock_available", Decimal("0")))
                existing["enabled_prices"] = item.get("enabled_prices", existing.get("enabled_prices", {}))
                existing["stock_by_unit"] = item.get("stock_by_unit", existing.get("stock_by_unit", {}))
                self._render()
                return
        new_item = dict(item)
        quantity = Decimal(str(new_item["quantity"]))
        unit_price = Decimal(str(new_item["unit_price"]))
        new_item["line_total"] = Decimal(str(new_item.get("line_total", quantity * unit_price)))
        new_item.setdefault("enabled_prices", {})
        new_item.setdefault("stock_by_unit", {})
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

                unit_combo = QComboBox()
                enabled_prices = dict(item.get("enabled_prices", {}))
                current_unit = item["unit_type"]
                if enabled_prices:
                    for unit_type in enabled_prices:
                        unit_combo.addItem(unit_type.value, unit_type)
                    unit_combo.setCurrentIndex(max(0, unit_combo.findData(current_unit)))
                else:
                    unit_combo.addItem(current_unit.value if hasattr(current_unit, "value") else str(current_unit), current_unit)
                unit_combo.currentIndexChanged.connect(
                    lambda _index, row_index=row, combo=unit_combo: self._handle_unit_type_changed(row_index, combo.currentData())
                )
                configure_table_cell_widget(unit_combo, height=34)
                self.setCellWidget(row, 2, unit_combo)

                quantity_spin = SelectAllQuantityInput()
                quantity_spin.setRange(Decimal("0.001"), Decimal("999999999"))
                quantity_spin.setValue(Decimal(str(item["quantity"])))
                quantity_spin.editingFinished.connect(
                    lambda row_index=row, spin=quantity_spin: self._handle_quantity_finished(row_index, spin.value())
                )
                quantity_spin.setToolTip(self._quantity_tooltip(item))
                configure_table_cell_widget(quantity_spin, height=34)
                self.setCellWidget(row, 3, quantity_spin)

                unit_price_spin = SelectAllDecimalInput()
                unit_price_spin.setRange(Decimal("0"), Decimal(str(MAX_MONEY_INPUT)))
                unit_price_spin.setValue(Decimal(str(item["unit_price"])))
                unit_price_spin.editingFinished.connect(
                    lambda row_index=row, spin=unit_price_spin: self._handle_unit_price_finished(row_index, spin.value())
                )
                configure_table_cell_widget(unit_price_spin, height=34)
                self.setCellWidget(row, 4, unit_price_spin)

                line_total_spin = SelectAllDecimalInput()
                line_total_spin.setRange(Decimal("0"), Decimal(str(MAX_MONEY_INPUT)))
                line_total_spin.setValue(Decimal(str(item["line_total"])))
                line_total_spin.editingFinished.connect(
                    lambda row_index=row, spin=line_total_spin: self._handle_line_total_finished(row_index, spin.value())
                )
                configure_table_cell_widget(line_total_spin, height=34)
                self.setCellWidget(row, 5, line_total_spin)

                remove_button = QPushButton("Xóa")
                remove_button.clicked.connect(lambda _checked=False, row_index=row: self.remove_row_at(row_index))
                configure_table_cell_widget(remove_button, compact=True, height=34)
                self.setCellWidget(row, 6, remove_button)
        finally:
            self._syncing = False
        self.totals_changed.emit()

    def _handle_unit_type_changed(self, row_index: int, unit_type: UnitType | None) -> None:
        if self._syncing or unit_type is None or not (0 <= row_index < len(self._items)):
            return
        item = self._items[row_index]
        enabled_prices = dict(item.get("enabled_prices", {}))
        stock_by_unit = dict(item.get("stock_by_unit", {}))
        if unit_type not in enabled_prices:
            return
        item["unit_type"] = unit_type
        item["unit_price"] = Decimal(str(enabled_prices[unit_type]))
        item["stock_available"] = Decimal(str(stock_by_unit.get(unit_type, Decimal("0"))))
        item["line_total"] = Decimal(str(item["quantity"])) * Decimal(str(item["unit_price"]))
        self._render()

    def _handle_quantity_finished(self, row_index: int, value: Decimal) -> None:
        if self._syncing or not (0 <= row_index < len(self._items)):
            return
        item = self._items[row_index]
        quantity = Decimal(str(value))
        item["quantity"] = quantity
        item["line_total"] = quantity * Decimal(str(item["unit_price"]))
        self._render()

    def _handle_unit_price_finished(self, row_index: int, value: Decimal) -> None:
        if self._syncing or not (0 <= row_index < len(self._items)):
            return
        item = self._items[row_index]
        unit_price = Decimal(str(value))
        item["unit_price"] = unit_price
        item["line_total"] = Decimal(str(item["quantity"])) * unit_price
        self._render()

    def _handle_line_total_finished(self, row_index: int, value: Decimal) -> None:
        if self._syncing or not (0 <= row_index < len(self._items)):
            return
        item = self._items[row_index]
        line_total = Decimal(str(value))
        quantity = Decimal(str(item["quantity"]))
        item["line_total"] = line_total
        item["unit_price"] = (line_total / quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self._render()

    @staticmethod
    def _quantity_tooltip(item: dict[str, object]) -> str:
        available = Decimal(str(item.get("stock_available", Decimal("0"))))
        quantity = Decimal(str(item["quantity"]))
        return f"Tồn: {available}\nĐặt: {quantity}"
