from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from core.config import MAX_MONEY_INPUT
from core.enums import PaymentMethod
from core.exceptions import ValidationError
from modules.sales.controller import SalesController
from modules.sales.ui.customer_picker_widget import CustomerPickerWidget
from modules.sales.ui.invoice_items_table import InvoiceItemsTable
from modules.sales.ui.product_search_widget import ProductSearchWidget
from modules.sales.ui.scale import scaled
from modules.settings.service import get_ui_scale_factor, get_ui_scale_preset
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox
from shared.widgets.numeric_inputs import SelectAllSpinBox


class SalesPage(QWidget):
    def __init__(self, controller: SalesController) -> None:
        super().__init__()
        self._controller = controller
        self._ui_scale = 1.0

        self._customer_picker = CustomerPickerWidget(list(controller.list_customers()), self)
        self._product_search = ProductSearchWidget(controller.list_sellable_products(), self)
        self._items_table = InvoiceItemsTable()
        self._items_table.setMinimumHeight(320)
        self._items_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

        self._title_label = QLabel("Bán hàng")
        self._total_label = QLabel(format_money(Decimal("0")))
        self._change_label = QLabel(format_money(Decimal("0")))
        self._change_label.setProperty("class", "muted")

        self._paid_amount_input = SelectAllSpinBox()
        self._paid_amount_input.setRange(0, MAX_MONEY_INPUT)
        self._paid_amount_input.valueChanged.connect(self._refresh_amounts)

        self._payment_method_combo = QComboBox()
        self._payment_method_combo.addItem("Để trống", None)
        self._payment_method_combo.addItem("Tiền mặt", PaymentMethod.CASH)
        self._payment_method_combo.addItem("Chuyển khoản", PaymentMethod.BANK_TRANSFER)

        self._product_search.item_added.connect(self._handle_item_added)
        self._customer_picker.customer_changed.connect(self._refresh_amounts)
        self._items_table.totals_changed.connect(self._refresh_amounts)

        self._form_layout = QFormLayout()
        self._form_layout.setSpacing(12)
        self._form_layout.addRow("Tổng tiền", self._total_label)
        self._form_layout.addRow("Khách trả", self._paid_amount_input)
        self._form_layout.addRow("Tiền dư", self._change_label)
        self._form_layout.addRow("Thanh toán", self._payment_method_combo)

        self._create_button = QPushButton("Tạo hóa đơn")
        self._create_button.clicked.connect(self._create_invoice)

        content = QWidget(self)
        self._content_layout = QVBoxLayout(content)
        self._content_layout.addWidget(self._title_label)
        self._content_layout.addWidget(self._customer_picker)
        self._content_layout.addWidget(self._product_search)
        self._content_layout.addWidget(self._items_table)
        self._content_layout.addLayout(self._form_layout)
        self._content_layout.addWidget(self._create_button)
        self._content_layout.addStretch()

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)

        self.apply_ui_scale_preset(get_ui_scale_preset())
        self._refresh_amounts()

    def apply_ui_scale_preset(self, preset: str) -> None:
        self._ui_scale = get_ui_scale_factor(preset)
        factor = self._ui_scale
        self._title_label.setStyleSheet(f"font-size: {scaled(24, factor)}px; font-weight: 700;")
        self._total_label.setStyleSheet(f"font-size: {scaled(32, factor)}px; font-weight: 700;")
        self._change_label.setStyleSheet(f"font-size: {scaled(22, factor)}px;")
        self._paid_amount_input.setMinimumHeight(scaled(54, factor))
        self._paid_amount_input.setStyleSheet(f"font-size: {scaled(20, factor)}px; padding: {scaled(10, factor)}px {scaled(12, factor)}px;")
        self._payment_method_combo.setMinimumHeight(scaled(54, factor))
        self._payment_method_combo.setStyleSheet(f"font-size: {scaled(20, factor)}px; padding: {scaled(8, factor)}px {scaled(12, factor)}px;")
        self._create_button.setMinimumHeight(scaled(58, factor))
        self._create_button.setStyleSheet(f"font-size: {scaled(22, factor)}px; font-weight: 700; padding: {scaled(10, factor)}px {scaled(18, factor)}px;")
        self._items_table.setMinimumHeight(scaled(320, factor))
        self._content_layout.setContentsMargins(scaled(18, factor), scaled(10, factor), scaled(18, factor), scaled(14, factor))
        self._content_layout.setSpacing(scaled(10, factor))

        for index in range(self._form_layout.rowCount()):
            label_item = self._form_layout.itemAt(index, QFormLayout.ItemRole.LabelRole)
            if label_item is not None and label_item.widget() is not None:
                label_item.widget().setStyleSheet(f"font-size: {scaled(20, factor)}px; font-weight: 600;")

        self._customer_picker.apply_ui_scale(factor)
        self._product_search.apply_ui_scale(factor)
        self._items_table.verticalHeader().setDefaultSectionSize(scaled(52, factor))
        self._items_table.verticalHeader().setMinimumSectionSize(scaled(52, factor))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.reload_data()

    def reload_data(self) -> None:
        self._customer_picker.reload_data(list(self._controller.list_customers()))
        self._product_search.reload_data(self._controller.list_sellable_products())
        self._refresh_amounts()

    def _handle_item_added(self, item: object) -> None:
        self._items_table.add_or_merge_item(dict(item))

    def _refresh_amounts(self) -> None:
        total_amount = self._items_table.total_amount()
        self._total_label.setText(format_money(total_amount))
        paid_amount = Decimal(self._paid_amount_input.value())
        overpayment = max(paid_amount - total_amount, Decimal("0"))
        self._change_label.setText(format_money(overpayment))

    def _create_invoice(self) -> None:
        try:
            items = self._items_table.items_payload()
            if not items:
                raise ValidationError("Phải có ít nhất 1 dòng hàng hóa.")
            customer_id = self._customer_picker.selected_customer_id()
            if self._customer_picker.customer_radio.isChecked() and customer_id is None:
                raise ValidationError("Phải chọn khách hàng.")
            paid_amount = Decimal(self._paid_amount_input.value())
            if paid_amount < Decimal("0"):
                raise ValidationError("Số tiền khách trả phải >= 0.")

            total_amount = self._items_table.total_amount()
            if customer_id is None and paid_amount < total_amount:
                raise ValidationError("Khách lẻ phải trả đủ tiền hóa đơn.")

            invoice = self._controller.create_invoice(
                customer_id=customer_id,
                customer_snapshot_name=self._customer_picker.snapshot_name(),
                invoice_datetime=datetime.now(),
                items=items,
                paid_amount=paid_amount,
                payment_method=self._payment_method_combo.currentData(),
            )
            MessageBox.info(self, "Thành công", f"Đã tạo hóa đơn {invoice.invoice_code}")
            self.reload_data()
            self._reset_form()
        except Exception as exc:
            MessageBox.error(self, "Không tạo được hóa đơn", str(exc))

    def _reset_form(self) -> None:
        self._customer_picker.reset()
        self._product_search.reset()
        self._items_table.clear_items()
        self._paid_amount_input.setValue(0)
        self._payment_method_combo.setCurrentIndex(0)
        self._refresh_amounts()
