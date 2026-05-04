from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable

from PyQt6.QtCore import QDateTime, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QDateTimeEdit, QFormLayout, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget

from core.exceptions import ValidationError
from modules.orders.controller import OrderController
from modules.orders.models import OrderRequest
from modules.orders.ui.order_items_table import OrderItemsTable
from modules.sales.controller import SellableProductOption
from modules.sales.ui.customer_picker_widget import CustomerPickerWidget
from modules.sales.ui.scale import scaled, scaled_font
from modules.settings.service import get_ui_scale_factor, get_ui_scale_preset
from shared.widgets.message_box import MessageBox


class OrderDraftPage(QWidget):
    order_changed = pyqtSignal()

    def __init__(
        self,
        controller: OrderController,
        *,
        order: OrderRequest | None = None,
        on_edit_completed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._editing_order_id = None if order is None else order.id
        self._on_edit_completed = on_edit_completed
        self._search_products: list[SellableProductOption] = list(controller.list_sellable_products())

        self._items_table = OrderItemsTable()
        self._items_table.setMinimumHeight(420)
        self._note_input = QTextEdit()
        self._note_input.setPlaceholderText("Ghi chú đơn đặt hàng")
        self._customer_picker = CustomerPickerWidget(list(controller.list_customers()), self, compact=True)
        self._order_datetime_input = QDateTimeEdit(QDateTime.currentDateTime())
        self._order_datetime_input.setCalendarPopup(True)
        self._order_datetime_input.setDisplayFormat("dd/MM/yyyy HH:mm")
        self._delivery_enabled = QCheckBox("Có ngày cần giao")
        self._delivery_datetime_input = QDateTimeEdit(QDateTime.currentDateTime())
        self._delivery_datetime_input.setCalendarPopup(True)
        self._delivery_datetime_input.setDisplayFormat("dd/MM/yyyy HH:mm")
        self._delivery_datetime_input.setEnabled(False)
        self._delivery_enabled.toggled.connect(self._delivery_datetime_input.setEnabled)
        self._submit_button = QPushButton("Lưu đặt hàng")
        self._submit_button.clicked.connect(self._submit)

        form = QFormLayout()
        form.addRow("Thời gian đặt", self._order_datetime_input)
        form.addRow("", self._delivery_enabled)
        form.addRow("Ngày cần giao", self._delivery_datetime_input)

        right_layout = QVBoxLayout()
        right_layout.addLayout(form)
        right_layout.addWidget(self._customer_picker)
        right_layout.addStretch(1)
        right_layout.addWidget(self._submit_button)

        left_layout = QVBoxLayout()
        left_layout.addWidget(self._items_table, 1)
        left_layout.addWidget(self._note_input, 0)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(14)
        main_layout.addLayout(left_layout, 5)
        main_layout.addLayout(right_layout, 2)

        self.apply_ui_scale_preset(get_ui_scale_preset())
        if order is not None:
            self._load_order(order)

    def apply_ui_scale_preset(self, preset: str) -> None:
        factor = get_ui_scale_factor(preset)
        self.layout().setSpacing(scaled(14, factor))
        self._items_table.apply_ui_scale(factor)
        self._note_input.setMaximumHeight(scaled(92, factor))
        self._note_input.setStyleSheet(f"font-size: {scaled_font(15, factor)}px; padding: {scaled(8, factor)}px;")
        for widget in (self._order_datetime_input, self._delivery_datetime_input):
            widget.setMinimumHeight(scaled(42, factor))
            widget.setStyleSheet(f"font-size: {scaled_font(16, factor)}px; padding: {scaled(6, factor)}px {scaled(10, factor)}px;")
        self._customer_picker.apply_ui_scale(factor)
        self._submit_button.setMinimumHeight(scaled(52, factor))
        self._submit_button.setStyleSheet(f"font-size: {scaled_font(20, factor)}px; font-weight: 700; padding: {scaled(8, factor)}px {scaled(16, factor)}px;")

    def reload_data(self) -> None:
        self._search_products = list(self._controller.list_sellable_products())
        self._customer_picker.reload_data(list(self._controller.list_customers()))

    def shared_search_placeholder(self) -> str:
        return "Tìm theo tên hàng"

    def shared_search_suggestions(self, query: str) -> list[tuple[str, object]]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []
        matches = [product for product in self._search_products if normalized_query in product.product_name.lower()]
        return [(product.product_name, product.product_id) for product in matches[:20]]

    def activate_shared_search_selection(self, payload: object) -> None:
        if payload is None:
            return
        product = next((product for product in self._search_products if product.product_id == int(payload)), None)
        if product is not None:
            self._items_table.add_or_merge_item(self._build_product_payload(product))

    def activate_shared_search_best_match(self, query: str) -> None:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return
        product = next((product for product in self._search_products if normalized_query in product.product_name.lower()), None)
        if product is not None:
            self._items_table.add_or_merge_item(self._build_product_payload(product))

    @staticmethod
    def _build_product_payload(product: SellableProductOption) -> dict[str, object]:
        unit_type = next(iter(product.enabled_prices), None)
        if unit_type is None:
            return {}
        return {
            "product_id": product.product_id,
            "product_code_base": product.product_code_base,
            "product_name": product.product_name,
            "unit_type": unit_type,
            "quantity": Decimal("1"),
            "enabled_units": list(product.enabled_prices.keys()),
        }

    def _submit(self) -> None:
        try:
            items = self._items_table.items_payload()
            if not items:
                raise ValidationError("Phải có ít nhất 1 dòng hàng hóa.")
            delivery_datetime = self._delivery_datetime_input.dateTime().toPyDateTime() if self._delivery_enabled.isChecked() else None
            payload = {
                "customer_id": self._customer_picker.selected_customer_id(),
                "customer_name_snapshot": self._customer_picker.snapshot_name(),
                "order_datetime": self._order_datetime_input.dateTime().toPyDateTime(),
                "required_delivery_datetime": delivery_datetime,
                "items": items,
                "note": self._note_input.toPlainText().strip() or None,
            }
            if self._editing_order_id is None:
                order = self._controller.create_order(**payload)
                MessageBox.info(self, "Thành công", f"Đã lưu đơn đặt hàng {order.order_code}")
                self._reset_form()
            else:
                order = self._controller.update_order(self._editing_order_id, **payload)
                MessageBox.info(self, "Thành công", f"Đã cập nhật đơn đặt hàng {order.order_code}")
                if self._on_edit_completed is not None:
                    self._on_edit_completed()
            self.order_changed.emit()
        except Exception as exc:
            MessageBox.error(self, "Không lưu được đơn đặt hàng", str(exc))

    def _reset_form(self) -> None:
        self._customer_picker.reset()
        self._items_table.clear_items()
        self._note_input.clear()
        self._delivery_enabled.setChecked(False)
        self._order_datetime_input.setDateTime(QDateTime.currentDateTime())
        self._delivery_datetime_input.setDateTime(QDateTime.currentDateTime())

    def _load_order(self, order: OrderRequest) -> None:
        self._submit_button.setText("Cập nhật")
        self._items_table.clear_items()
        products = {product.product_id: product for product in self._search_products}
        for item in order.items:
            product = products.get(item.product_id)
            enabled_units = list(product.enabled_prices.keys()) if product is not None else [item.unit_type]
            self._items_table.add_or_merge_item(
                {
                    "product_id": item.product_id,
                    "product_code_base": product.product_code_base if product is not None else "",
                    "product_name": item.product_name_snapshot,
                    "unit_type": item.unit_type,
                    "quantity": item.quantity,
                    "enabled_units": enabled_units,
                }
            )
        self._note_input.setText(order.note or "")
        self._order_datetime_input.setDateTime(QDateTime(order.order_datetime))
        if order.required_delivery_datetime is not None:
            self._delivery_enabled.setChecked(True)
            self._delivery_datetime_input.setDateTime(QDateTime(order.required_delivery_datetime))
        customer = next((customer for customer in self._controller.list_customers(include_inactive=True) if customer.id == order.customer_id), None)
        if customer is not None:
            self._customer_picker.lock_customer(customer)
            self._customer_picker.unlock_customer()
