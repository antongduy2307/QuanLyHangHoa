from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.enums import UnitType
from modules.returns.controller import QuickReturnProductOption
from shared.widgets.autocomplete_line_edit import AutocompleteLineEdit
from shared.widgets.numeric_inputs import SelectAllSpinBox


class QuickReturnProductSearchWidget(QWidget):
    item_added = pyqtSignal(object)

    def __init__(
        self,
        products: list[QuickReturnProductOption],
        parent: QWidget | None = None,
        *,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self._products = products
        self._selected_product: QuickReturnProductOption | None = None
        self._compact = compact

        self.search_input = AutocompleteLineEdit()
        self.search_input.setPlaceholderText("Tìm theo tên hàng")
        self.search_input.textChanged.connect(self._update_suggestions)
        if compact:
            self.search_input.suggestion_selected.connect(self._select_product_and_emit_by_id)
            self.search_input.returnPressed.connect(self._select_best_match)
        else:
            self.search_input.suggestion_selected.connect(self._select_product_by_id)

        self.unit_combo = QComboBox()
        self.unit_combo.currentIndexChanged.connect(self._update_price_label)
        self.quantity_input = SelectAllSpinBox()
        self.quantity_input.setRange(0, 999999999)
        self.price_label = QLabel("Giá: -")

        add_button = QPushButton("Thêm")
        add_button.clicked.connect(self._emit_item)

        controls = QHBoxLayout()
        controls.addWidget(self.unit_combo)
        controls.addWidget(self.quantity_input)
        controls.addWidget(self.price_label)
        controls.addWidget(add_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search_input)
        if not compact:
            layout.addLayout(controls)

        self._sync_product(None)

    def reload_data(self, products: list[QuickReturnProductOption]) -> None:
        previous_product_id = None if self._selected_product is None else self._selected_product.product_id
        self._products = products
        self._selected_product = next((product for product in products if product.product_id == previous_product_id), None)
        self._update_suggestions()
        self._sync_product(self._selected_product)

    def reset(self) -> None:
        self.search_input.clear()
        if not self._compact:
            self.quantity_input.setValue(0)
        self.search_input.hide_suggestions()
        self._sync_product(None)

    def _update_suggestions(self) -> None:
        query = self.search_input.text().strip().lower()
        if not query:
            self.search_input.hide_suggestions()
            return
        matches = [product for product in self._products if query in product.product_name.lower()]
        suggestions = [(product.product_name, product.product_id) for product in matches[:20]]
        self.search_input.set_suggestions(suggestions)

    def _select_best_match(self) -> None:
        query = self.search_input.text().strip().lower()
        if not query:
            return
        product = next((candidate for candidate in self._products if query in candidate.product_name.lower()), None)
        if product is None:
            return
        self._emit_compact_product(product)

    def _select_product_by_id(self, product_id: object) -> None:
        if product_id is None:
            return
        product = next((candidate for candidate in self._products if candidate.product_id == int(product_id)), None)
        self._sync_product(product)

    def _select_product_and_emit_by_id(self, product_id: object) -> None:
        if product_id is None:
            return
        product = next((candidate for candidate in self._products if candidate.product_id == int(product_id)), None)
        if product is None:
            return
        self._emit_compact_product(product)

    def _sync_product(self, product: QuickReturnProductOption | None) -> None:
        self._selected_product = product
        self.unit_combo.clear()
        if product is None:
            self.unit_combo.setEnabled(False)
            self.quantity_input.setEnabled(False)
            self.price_label.setText("Giá: -")
            return
        self.search_input.blockSignals(True)
        self.search_input.setText(product.product_name)
        self.search_input.blockSignals(False)
        for unit_type in product.enabled_prices:
            self.unit_combo.addItem(unit_type.value, unit_type)
        self.unit_combo.setEnabled(True)
        self.quantity_input.setEnabled(True)
        self._update_price_label()

    def _update_price_label(self) -> None:
        if self._compact or self._selected_product is None:
            self.price_label.setText("Giá: -")
            return
        unit_type = self.unit_combo.currentData()
        if unit_type is None:
            self.price_label.setText("Giá: -")
            return
        price = self._selected_product.enabled_prices[unit_type]
        self.price_label.setText(f"Giá: {price:,.0f}")

    def _emit_item(self) -> None:
        if self._selected_product is None:
            return
        unit_type = self.unit_combo.currentData()
        quantity = Decimal(self.quantity_input.value())
        if unit_type is None or quantity <= Decimal("0"):
            return
        self.item_added.emit(self._build_payload(self._selected_product, unit_type, quantity))
        self.quantity_input.setValue(0)

    def _emit_compact_product(self, product: QuickReturnProductOption) -> None:
        unit_type = next(iter(product.enabled_prices), None)
        if unit_type is None:
            return
        self.item_added.emit(self._build_payload(product, unit_type, Decimal("1")))
        self.search_input.clear()
        self.search_input.hide_suggestions()
        self._selected_product = None

    def _build_payload(self, product: QuickReturnProductOption, unit_type: UnitType, quantity: Decimal) -> dict[str, object]:
        price = product.enabled_prices[unit_type]
        return {
            "product_id": product.product_id,
            "product_code_base": product.product_code_base,
            "product_name": product.product_name,
            "unit_type": unit_type,
            "quantity": quantity,
            "unit_price": price,
            "line_total": quantity * price,
            "enabled_prices": dict(product.enabled_prices),
            "stock_by_unit": {},
            "stock_available": Decimal("0"),
        }
