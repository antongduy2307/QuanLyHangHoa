from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QPushButton, QTableWidget, QTableWidgetItem

from core.enums import UnitType
from modules.sales.ui.scale import scaled
from shared.widgets.numeric_inputs import SelectAllQuantityInput
from shared.widgets.table_helpers import configure_table_cell_widget, configure_table_widget


class OrderItemsTable(QTableWidget):
    items_changed = pyqtSignal()

    def __init__(self, persistence_key: str = "orders.items") -> None:
        super().__init__(0, 5)
        self.setHorizontalHeaderLabels(["Tên hàng", "Đơn vị", "Số lượng", "Mã hàng", ""])
        self.setProperty("column_minimum_widths", {0: 280, 1: 120, 2: 120, 3: 120, 4: 88})
        configure_table_widget(self, persistence_key)
        self.setColumnHidden(3, True)
        self._items: list[dict[str, object]] = []
        self._syncing = False

    def items_payload(self) -> list[dict[str, object]]:
        return [
            {
                "product_id": item["product_id"],
                "unit_type": item["unit_type"],
                "quantity": item["quantity"],
            }
            for item in self._items
        ]

    def add_or_merge_item(self, item: dict[str, object]) -> None:
        for existing in self._items:
            if existing["product_id"] == item["product_id"] and existing["unit_type"] == item["unit_type"]:
                existing["quantity"] = Decimal(str(existing["quantity"])) + Decimal(str(item["quantity"]))
                self._render()
                return
        new_item = dict(item)
        new_item.setdefault("enabled_units", [new_item["unit_type"]])
        self._items.append(new_item)
        self._render()

    def clear_items(self) -> None:
        self._items.clear()
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
                name_item = QTableWidgetItem(str(item["product_name"]))
                name_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.setItem(row, 0, name_item)

                unit_combo = QComboBox()
                enabled_units = list(item.get("enabled_units", [item["unit_type"]]))
                for unit_type in enabled_units:
                    unit_combo.addItem(unit_type.value if isinstance(unit_type, UnitType) else str(unit_type), unit_type)
                unit_combo.setCurrentIndex(max(0, unit_combo.findData(item["unit_type"])))
                unit_combo.currentIndexChanged.connect(
                    lambda _index, row_index=row, combo=unit_combo: self._handle_unit_type_changed(row_index, combo.currentData())
                )
                configure_table_cell_widget(unit_combo, height=34)
                self.setCellWidget(row, 1, unit_combo)

                quantity_spin = SelectAllQuantityInput()
                quantity_spin.setRange(Decimal("0.001"), Decimal("999999999"))
                quantity_spin.setValue(Decimal(str(item["quantity"])))
                quantity_spin.editingFinished.connect(
                    lambda row_index=row, spin=quantity_spin: self._handle_quantity_finished(row_index, spin.value())
                )
                configure_table_cell_widget(quantity_spin, height=34)
                self.setCellWidget(row, 2, quantity_spin)

                self.setItem(row, 3, QTableWidgetItem(str(item.get("product_code_base", ""))))
                remove_button = QPushButton("Xóa")
                remove_button.clicked.connect(lambda _checked=False, row_index=row: self.remove_row_at(row_index))
                configure_table_cell_widget(remove_button, compact=True, height=34)
                self.setCellWidget(row, 4, remove_button)
        finally:
            self._syncing = False
        self.items_changed.emit()

    def _handle_unit_type_changed(self, row_index: int, unit_type: UnitType | None) -> None:
        if self._syncing or unit_type is None or not (0 <= row_index < len(self._items)):
            return
        self._items[row_index]["unit_type"] = unit_type
        self._render()

    def _handle_quantity_finished(self, row_index: int, value: Decimal) -> None:
        if self._syncing or not (0 <= row_index < len(self._items)):
            return
        self._items[row_index]["quantity"] = Decimal(str(value))
        self._render()

    def apply_ui_scale(self, factor: float) -> None:
        self.verticalHeader().setDefaultSectionSize(scaled(52, factor))
        self.verticalHeader().setMinimumSectionSize(scaled(52, factor))
