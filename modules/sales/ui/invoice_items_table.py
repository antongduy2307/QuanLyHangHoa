from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
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
from core.enums import InvoiceLineType, UnitType
from shared.widgets.numeric_inputs import SelectAllDecimalInput, SelectAllQuantityInput
from shared.widgets.table_helpers import configure_table_cell_widget, configure_table_widget


SALE_ROW_BACKGROUND = "#E8F5E9"
RETURN_ROW_BACKGROUND = "#FDECEA"
SALE_ACCENT = "#2E7D32"
RETURN_ACCENT = "#C62828"

LINE_TYPE_LABELS = {
    InvoiceLineType.SALE: "BÁN",
    InvoiceLineType.RETURN: "TRẢ",
}

UNIT_TYPE_LABELS = {
    UnitType.BAO: "Bao",
    UnitType.KG: "Kg",
    UnitType.BICH: "Bịch",
}

# Logical column indexes. LINE_TYPE_COLUMN only exists when show_line_type=True.
CODE_COLUMN = 0
NAME_COLUMN = 1
UNIT_COLUMN = 2
QUANTITY_COLUMN = 3
UNIT_PRICE_COLUMN = 4
LINE_TOTAL_COLUMN = 5
REMOVE_COLUMN = 6
LINE_TYPE_COLUMN = 7


def unit_type_label(unit_type: object) -> str:
    try:
        return UNIT_TYPE_LABELS[UnitType(str(unit_type.value if hasattr(unit_type, "value") else unit_type))]
    except (ValueError, KeyError):
        return str(unit_type)


class InvoiceItemsTable(QTableWidget):
    totals_changed = pyqtSignal()

    def __init__(self, persistence_key: str = "sales.invoice_items", *, show_line_type: bool = False) -> None:
        self._show_line_type = show_line_type
        super().__init__(0, 8 if show_line_type else 7)
        headers = ["Mã hàng", "Tên hàng", "Đơn vị", "Số lượng", "Đơn giá", "Thành tiền", ""]
        minimum_widths = {0: 120, 1: 260, 2: 120, 3: 120, 4: 140, 5: 150, 6: 96}
        if show_line_type:
            headers.append("Loại")
            minimum_widths[LINE_TYPE_COLUMN] = 96
        self.setHorizontalHeaderLabels(headers)
        self.setProperty("column_minimum_widths", minimum_widths)
        configure_table_widget(self, persistence_key)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.horizontalHeader().setSectionResizeMode(REMOVE_COLUMN, QHeaderView.ResizeMode.Interactive)
        if show_line_type:
            # Show the "Loại" column first visually while keeping legacy logical indexes stable.
            self.horizontalHeader().moveSection(LINE_TYPE_COLUMN, 0)
            # Row colours carry the SALE/RETURN meaning, so alternating colours would hide it.
            self.setAlternatingRowColors(False)
        self.verticalHeader().setDefaultSectionSize(max(self.verticalHeader().defaultSectionSize(), 56))
        self.verticalHeader().setMinimumSectionSize(max(self.verticalHeader().minimumSectionSize(), 56))

        self._items: list[dict[str, object]] = []
        self._syncing = False

    # ----- data API -----

    def items_payload(self) -> list[dict[str, object]]:
        return [
            {
                "product_id": item["product_id"],
                "unit_type": item["unit_type"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "line_total": item["line_total"],
                "line_type": item["line_type"],
            }
            for item in self._items
        ]

    def sale_total(self) -> Decimal:
        return self._sum_line_totals(InvoiceLineType.SALE)

    def return_total(self) -> Decimal:
        return self._sum_line_totals(InvoiceLineType.RETURN)

    def total_amount(self) -> Decimal:
        """Net amount: SALE lines minus RETURN lines."""
        return self.sale_total() - self.return_total()

    def line_types(self) -> list[InvoiceLineType]:
        return [InvoiceLineType(item["line_type"]) for item in self._items]

    def clear_items(self) -> None:
        self._items.clear()
        self._render()

    def add_or_merge_item(self, item: dict[str, object]) -> None:
        new_item = dict(item)
        new_item["line_type"] = self._normalize_line_type(new_item.get("line_type"))
        for existing in self._items:
            if self._merge_key(existing) == self._merge_key(new_item):
                existing_quantity = Decimal(str(existing["quantity"])) + Decimal(str(new_item["quantity"]))
                existing["quantity"] = existing_quantity
                existing["line_total"] = existing_quantity * Decimal(str(existing["unit_price"]))
                existing["stock_available"] = new_item.get("stock_available", existing.get("stock_available", Decimal("0")))
                existing["enabled_prices"] = new_item.get("enabled_prices", existing.get("enabled_prices", {}))
                existing["stock_by_unit"] = new_item.get("stock_by_unit", existing.get("stock_by_unit", {}))
                self._render()
                return
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

    def toggle_line_type_at(self, row_index: int) -> None:
        if not (0 <= row_index < len(self._items)):
            return
        item = self._items[row_index]
        current = self._normalize_line_type(item.get("line_type"))
        item["line_type"] = InvoiceLineType.RETURN if current == InvoiceLineType.SALE else InvoiceLineType.SALE
        # Merge into an existing line of the same product/unit/type, if any.
        for index, other in enumerate(self._items):
            if index != row_index and self._merge_key(other) == self._merge_key(item):
                merged_quantity = Decimal(str(other["quantity"])) + Decimal(str(item["quantity"]))
                other["quantity"] = merged_quantity
                other["line_total"] = merged_quantity * Decimal(str(other["unit_price"]))
                del self._items[row_index]
                break
        self._render()

    # ----- helpers -----

    def _sum_line_totals(self, line_type: InvoiceLineType) -> Decimal:
        return sum(
            (Decimal(str(item["line_total"])) for item in self._items if item["line_type"] == line_type),
            start=Decimal("0"),
        )

    @staticmethod
    def _normalize_line_type(value: object) -> InvoiceLineType:
        if value is None or value == "":
            return InvoiceLineType.SALE
        return InvoiceLineType(str(value.value if hasattr(value, "value") else value))

    @staticmethod
    def _merge_key(item: dict[str, object]) -> tuple[object, object, object]:
        return (item["product_id"], item["unit_type"], item["line_type"])

    def _render(self) -> None:
        self._syncing = True
        try:
            self.setRowCount(len(self._items))
            for row, item in enumerate(self._items):
                line_type = self._normalize_line_type(item.get("line_type"))
                is_return = line_type == InvoiceLineType.RETURN
                background = QColor(RETURN_ROW_BACKGROUND if is_return else SALE_ROW_BACKGROUND)

                code_item = QTableWidgetItem(str(item["product_code_base"]))
                code_font = QFont(code_item.font())
                code_font.setBold(True)
                code_font.setPointSize(code_font.pointSize() + 1)
                code_item.setFont(code_font)
                code_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.setItem(row, CODE_COLUMN, code_item)
                self.setItem(row, NAME_COLUMN, QTableWidgetItem(str(item["product_name"])))
                # Placeholder items so the row background shows behind the transparent cell widgets.
                for column in range(UNIT_COLUMN, self.columnCount()):
                    self.setItem(row, column, QTableWidgetItem(""))
                if self._show_line_type:
                    for column in range(self.columnCount()):
                        cell = self.item(row, column)
                        if cell is not None:
                            cell.setBackground(background)

                unit_combo = QComboBox()
                enabled_prices = dict(item.get("enabled_prices", {}))
                current_unit = item["unit_type"]
                if enabled_prices:
                    for unit_type in enabled_prices:
                        unit_combo.addItem(unit_type_label(unit_type), unit_type)
                    unit_combo.setCurrentIndex(max(0, unit_combo.findData(current_unit)))
                else:
                    unit_combo.addItem(unit_type_label(current_unit), current_unit)
                unit_combo.currentIndexChanged.connect(
                    lambda _index, row_index=row, combo=unit_combo: self._handle_unit_type_changed(row_index, combo.currentData())
                )
                configure_table_cell_widget(unit_combo, height=34)
                self.setCellWidget(row, UNIT_COLUMN, unit_combo)

                quantity_spin = SelectAllQuantityInput()
                quantity_spin.setRange(Decimal("0.001"), Decimal("999999999"))
                quantity_spin.setValue(Decimal(str(item["quantity"])))
                quantity_spin.editingFinished.connect(
                    lambda row_index=row, spin=quantity_spin: self._handle_quantity_finished(row_index, spin.value())
                )
                quantity_spin.setToolTip(self._quantity_tooltip(item))
                configure_table_cell_widget(quantity_spin, height=34)
                self.setCellWidget(row, QUANTITY_COLUMN, quantity_spin)

                unit_price_spin = SelectAllDecimalInput()
                unit_price_spin.setRange(Decimal("0"), Decimal(str(MAX_MONEY_INPUT)))
                unit_price_spin.setValue(Decimal(str(item["unit_price"])))
                unit_price_spin.editingFinished.connect(
                    lambda row_index=row, spin=unit_price_spin: self._handle_unit_price_finished(row_index, spin.value())
                )
                configure_table_cell_widget(unit_price_spin, height=34)
                self.setCellWidget(row, UNIT_PRICE_COLUMN, unit_price_spin)

                line_total_spin = SelectAllDecimalInput()
                line_total_spin.setRange(Decimal("0"), Decimal(str(MAX_MONEY_INPUT)))
                line_total_spin.setValue(Decimal(str(item["line_total"])))
                line_total_spin.editingFinished.connect(
                    lambda row_index=row, spin=line_total_spin: self._handle_line_total_finished(row_index, spin.value())
                )
                configure_table_cell_widget(line_total_spin, height=34)
                if self._show_line_type and is_return:
                    line_total_spin.setStyleSheet(line_total_spin.styleSheet() + f"color: {RETURN_ACCENT}; font-weight: 600;")
                    line_total_spin.setToolTip("Tiền hàng trả, được trừ vào hóa đơn")
                self.setCellWidget(row, LINE_TOTAL_COLUMN, line_total_spin)

                remove_button = QPushButton("Xóa")
                remove_button.clicked.connect(lambda _checked=False, row_index=row: self.remove_row_at(row_index))
                configure_table_cell_widget(remove_button, compact=True, height=34)
                self.setCellWidget(row, REMOVE_COLUMN, remove_button)

                if self._show_line_type:
                    type_button = QPushButton(LINE_TYPE_LABELS[line_type])
                    type_button.setObjectName("invoiceLineTypeButton")
                    type_button.setToolTip("Bấm để đổi giữa Bán và Trả")
                    type_button.setProperty("line_type", line_type.value)
                    type_button.clicked.connect(lambda _checked=False, row_index=row: self.toggle_line_type_at(row_index))
                    configure_table_cell_widget(type_button, compact=True, height=34)
                    accent = RETURN_ACCENT if is_return else SALE_ACCENT
                    type_button.setStyleSheet(
                        type_button.styleSheet() + f"color: {accent}; font-weight: 700;"
                    )
                    self.setCellWidget(row, LINE_TYPE_COLUMN, type_button)
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
