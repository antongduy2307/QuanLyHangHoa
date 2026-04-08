from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget

from core.enums import UnitType
from modules.sales.controller import SellableProductOption


class ProductSearchWidget(QWidget):
    item_added = pyqtSignal(object)

    def __init__(self, products: list[SellableProductOption], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._products = products
        self._selected_product: SellableProductOption | None = None

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tìm theo mã hoặc tên hàng")
        self.search_input.textChanged.connect(self._update_suggestions)

        self.suggestion_list = QListWidget()
        self.suggestion_list.setMaximumHeight(120)
        self.suggestion_list.itemClicked.connect(self._select_product)

        self.unit_combo = QComboBox()
        self.unit_combo.currentIndexChanged.connect(self._update_price_label)
        self.quantity_input = QDoubleSpinBox()
        self.quantity_input.setDecimals(3)
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
        layout.addWidget(self.search_input)
        layout.addWidget(self.suggestion_list)
        layout.addLayout(controls)

        self._sync_product(None)

    def reload_data(self, products: list[SellableProductOption]) -> None:
        previous_product_id = None if self._selected_product is None else self._selected_product.product_id
        self._products = products
        self._selected_product = next((product for product in products if product.product_id == previous_product_id), None)
        self._update_suggestions()
        self._sync_product(self._selected_product)

    def reset(self) -> None:
        self.search_input.clear()
        self.suggestion_list.clear()
        self.quantity_input.setValue(0)
        self._sync_product(None)

    def _update_suggestions(self) -> None:
        query = self.search_input.text().strip().lower()
        self.suggestion_list.clear()
        if not query:
            return
        code_matches = [product for product in self._products if query in product.product_code_base.lower()]
        matches = code_matches if code_matches else [product for product in self._products if query in product.product_name.lower()]
        for product in matches[:20]:
            self.suggestion_list.addItem(f"{product.product_code_base} - {product.product_name}")
            self.suggestion_list.item(self.suggestion_list.count() - 1).setData(256, product.product_id)

    def _select_product(self, *_args: object) -> None:
        item = self.suggestion_list.currentItem()
        if item is None:
            return
        product_id = item.data(256)
        product = next((candidate for candidate in self._products if candidate.product_id == product_id), None)
        self._sync_product(product)

    def _sync_product(self, product: SellableProductOption | None) -> None:
        self._selected_product = product
        self.unit_combo.clear()
        if product is None:
            self.unit_combo.setEnabled(False)
            self.quantity_input.setEnabled(False)
            self.price_label.setText("Giá: -")
            return
        for unit_type in product.enabled_prices:
            self.unit_combo.addItem(unit_type.value, unit_type)
        self.unit_combo.setEnabled(True)
        self.quantity_input.setEnabled(True)
        self._update_price_label()

    def _update_price_label(self) -> None:
        if self._selected_product is None:
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
        quantity = Decimal(str(self.quantity_input.value()))
        if unit_type is None or quantity <= Decimal("0"):
            return
        price = self._selected_product.enabled_prices[unit_type]
        self.item_added.emit(
            {
                "product_id": self._selected_product.product_id,
                "product_code_base": self._selected_product.product_code_base,
                "product_name": self._selected_product.product_name,
                "unit_type": unit_type,
                "quantity": quantity,
                "unit_price": price,
            }
        )
        self.quantity_input.setValue(0)
