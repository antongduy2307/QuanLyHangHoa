from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QGridLayout, QLabel, QPushButton, QSizePolicy, QWidget

from core.enums import UnitType
from modules.sales.controller import SellableProductOption
from modules.sales.ui.scale import scaled, scaled_font
from shared.widgets.autocomplete_line_edit import AutocompleteLineEdit
from shared.widgets.numeric_inputs import SelectAllSpinBox


class ProductSearchWidget(QWidget):
    item_added = pyqtSignal(object)

    def __init__(
        self,
        products: list[SellableProductOption],
        parent: QWidget | None = None,
        *,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self._products = products
        self._selected_product: SellableProductOption | None = None
        self._ui_scale = 1.0
        self._compact = compact

        self.search_input = AutocompleteLineEdit()
        self.search_input.setPlaceholderText("Tìm theo tên hàng")
        self.search_input.textEdited.connect(self._handle_search_text_edited)
        if compact:
            self.search_input.suggestion_selected.connect(self._select_product_and_emit_by_id)
        else:
            self.search_input.suggestion_selected.connect(self._select_product_by_id)
        self.search_input.returnPressed.connect(self._select_best_match)

        self.unit_combo = QComboBox()
        self.unit_combo.currentIndexChanged.connect(self._update_price_label)
        self.unit_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.quantity_input = SelectAllSpinBox()
        self.quantity_input.setRange(0, 999999999)
        self.quantity_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.price_label = QLabel("Giá: -")
        self.price_label.setWordWrap(True)
        self.price_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._add_button = QPushButton("Thêm")
        self._add_button.clicked.connect(self._emit_item)
        self._add_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self._controls_layout = QGridLayout()
        self._controls_layout.setContentsMargins(0, 0, 0, 0)
        self._controls_layout.addWidget(self.unit_combo, 0, 0)
        self._controls_layout.addWidget(self.quantity_input, 0, 1)
        self._controls_layout.addWidget(self.price_label, 0, 2)
        self._controls_layout.addWidget(self._add_button, 0, 3)
        self._controls_layout.setColumnStretch(0, 1)
        self._controls_layout.setColumnStretch(1, 1)
        self._controls_layout.setColumnStretch(2, 2)
        self._controls_layout.setColumnStretch(3, 0)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setColumnStretch(0, 1)
        layout.addWidget(self.search_input, 0, 0)
        if not compact:
            layout.addLayout(self._controls_layout, 1, 0)

        self.apply_ui_scale(1.0)
        self._sync_product(None)

    def apply_ui_scale(self, factor: float) -> None:
        self._ui_scale = factor
        self.search_input.setMinimumHeight(scaled(46 if self._compact else 52, factor))
        self.search_input.setStyleSheet(
            f"font-size: {scaled_font(18, factor)}px; padding: {scaled(10, factor)}px {scaled(12, factor)}px;"
        )
        self.search_input.set_popup_minimum_width(scaled(520, factor))
        self.search_input.set_popup_maximum_height(scaled(260, factor))
        self.search_input.set_popup_stylesheet(
            f"QListWidget {{ font-size: {scaled_font(16, factor)}px; padding: {scaled(6, factor)}px; border: 1px solid #cbd5e1; }}"
            f"QListWidget::item {{ min-height: {scaled(40, factor)}px; padding: {scaled(8, factor)}px {scaled(10, factor)}px; }}"
        )
        if self._compact:
            self.layout().setHorizontalSpacing(0)
            self.layout().setVerticalSpacing(0)
            return

        self.unit_combo.setMinimumHeight(scaled(50, factor))
        self.unit_combo.setMinimumWidth(scaled(96, factor))
        self.unit_combo.setStyleSheet(
            f"font-size: {scaled_font(18, factor)}px; padding: {scaled(8, factor)}px {scaled(12, factor)}px;"
        )
        self.quantity_input.setMinimumHeight(scaled(50, factor))
        self.quantity_input.setMinimumWidth(scaled(96, factor))
        self.quantity_input.setStyleSheet(
            f"font-size: {scaled_font(18, factor)}px; padding: {scaled(8, factor)}px {scaled(12, factor)}px;"
        )
        self.price_label.setStyleSheet(
            f"font-size: {scaled_font(20, factor)}px; font-weight: 600; padding: {scaled(6, factor)}px {scaled(8, factor)}px;"
        )
        self._add_button.setMinimumHeight(scaled(52, factor))
        self._add_button.setMinimumWidth(scaled(104, factor))
        self._add_button.setStyleSheet(
            f"font-size: {scaled_font(18, factor)}px; font-weight: 600; padding: {scaled(10, factor)}px {scaled(16, factor)}px;"
        )
        self._controls_layout.setHorizontalSpacing(scaled(12, factor))
        self._controls_layout.setVerticalSpacing(scaled(10, factor))
        self.layout().setHorizontalSpacing(0)
        self.layout().setVerticalSpacing(scaled(12, factor))

    def reload_data(self, products: list[SellableProductOption]) -> None:
        previous_product_id = None if self._selected_product is None else self._selected_product.product_id
        self._products = products
        self._selected_product = next((product for product in products if product.product_id == previous_product_id), None)
        if self._selected_product is not None:
            self.search_input.blockSignals(True)
            self.search_input.setText(self._search_text_for_product(self._selected_product))
            self.search_input.blockSignals(False)
        self._update_suggestions()
        self._sync_product(self._selected_product)

    def reset(self) -> None:
        self.search_input.clear()
        self.search_input.hide_suggestions()
        if not self._compact:
            self.quantity_input.setValue(0)
        self._sync_product(None)

    def _handle_search_text_edited(self, text: str) -> None:
        if self._selected_product is not None and text.strip() != self._search_text_for_product(self._selected_product):
            self._sync_product(None)
        self._update_suggestions(text)

    def _update_suggestions(self, text: str | None = None) -> None:
        query = (self.search_input.text() if text is None else text).strip().lower()
        if not query:
            self.search_input.hide_suggestions()
            return
        matches = [product for product in self._products if query in product.product_name.lower()]
        suggestions = [(self._search_text_for_product(product), product.product_id) for product in matches[:20]]
        self.search_input.set_suggestions(suggestions)

    def _select_best_match(self) -> None:
        query = self.search_input.text().strip().lower()
        if not query:
            return
        product = next((candidate for candidate in self._products if query in candidate.product_name.lower()), None)
        if product is None:
            return
        if self._compact:
            self._emit_compact_product(product)
        else:
            self._sync_product(product)

    def _select_product_by_id(self, product_id: object) -> None:
        if product_id is None:
            return
        product = next((candidate for candidate in self._products if candidate.product_id == int(product_id)), None)
        if product is None:
            return
        self._sync_product(product)

    def _select_product_and_emit_by_id(self, product_id: object) -> None:
        if product_id is None:
            return
        product = next((candidate for candidate in self._products if candidate.product_id == int(product_id)), None)
        if product is None:
            return
        self._emit_compact_product(product)

    def _sync_product(self, product: SellableProductOption | None) -> None:
        self._selected_product = product
        if self._compact:
            return
        self.unit_combo.clear()
        if product is None:
            self.unit_combo.setEnabled(False)
            self.quantity_input.setEnabled(False)
            self.price_label.setText("Giá: -")
            return
        self.search_input.blockSignals(True)
        self.search_input.setText(self._search_text_for_product(product))
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

    def _emit_compact_product(self, product: SellableProductOption) -> None:
        unit_type = next(iter(product.enabled_prices), None)
        if unit_type is None:
            return
        self.item_added.emit(self._build_payload(product, unit_type, Decimal("1")))
        self.search_input.clear()
        self.search_input.hide_suggestions()
        self._selected_product = None

    def _build_payload(
        self,
        product: SellableProductOption,
        unit_type: UnitType,
        quantity: Decimal,
    ) -> dict[str, object]:
        price = product.enabled_prices[unit_type]
        return {
            "product_id": product.product_id,
            "product_code_base": product.product_code_base,
            "product_name": product.product_name,
            "unit_type": unit_type,
            "quantity": quantity,
            "unit_price": price,
            "line_total": quantity * price,
            "stock_available": product.stock_by_unit.get(unit_type, Decimal("0")),
            "enabled_prices": dict(product.enabled_prices),
            "stock_by_unit": dict(product.stock_by_unit),
        }

    @staticmethod
    def _search_text_for_product(product: SellableProductOption) -> str:
        return product.product_name
