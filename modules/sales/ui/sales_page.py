from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.enums import PaymentMethod
from core.exceptions import ValidationError
from modules.sales.controller import SalesController
from modules.sales.ui.customer_picker_widget import CustomerPickerWidget
from modules.sales.ui.invoice_items_table import InvoiceItemsTable
from modules.sales.ui.product_search_widget import ProductSearchWidget
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox
from shared.widgets.numeric_inputs import SelectAllSpinBox


class SalesPage(QWidget):
    def __init__(self, controller: SalesController) -> None:
        super().__init__()
        self._controller = controller

        self._customer_picker = CustomerPickerWidget(list(controller.list_customers()), self)
        self._product_search = ProductSearchWidget(controller.list_sellable_products(), self)
        self._items_table = InvoiceItemsTable()

        self._total_label = QLabel(format_money(Decimal("0")))
        self._total_label.setStyleSheet("font-size: 20px; font-weight: 600;")
        self._change_label = QLabel(format_money(Decimal("0")))
        self._change_label.setProperty("class", "muted")

        self._paid_amount_input = SelectAllSpinBox()
        self._paid_amount_input.setRange(0, 999999999)
        self._paid_amount_input.valueChanged.connect(self._refresh_amounts)

        self._payment_method_combo = QComboBox()
        self._payment_method_combo.addItem("Để trống", None)
        self._payment_method_combo.addItem("Tiền mặt", PaymentMethod.CASH)
        self._payment_method_combo.addItem("Chuyển khoản", PaymentMethod.BANK_TRANSFER)

        self._product_search.item_added.connect(self._handle_item_added)
        self._customer_picker.customer_changed.connect(self._refresh_amounts)
        self._items_table.totals_changed.connect(self._refresh_amounts)

        form_layout = QFormLayout()
        form_layout.addRow("Tổng tiền", self._total_label)
        form_layout.addRow("Khách trả", self._paid_amount_input)
        form_layout.addRow("Tiền dư", self._change_label)
        form_layout.addRow("Thanh toán", self._payment_method_combo)

        create_button = QPushButton("Tạo hóa đơn")
        create_button.clicked.connect(self._create_invoice)

        layout = QVBoxLayout(self)
        title = QLabel("Bán hàng")
        subtitle = QLabel("Chọn khách, tìm hàng, thêm item và tạo hóa đơn thông qua SalesService.")
        subtitle.setProperty("class", "muted")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._customer_picker)
        layout.addWidget(self._product_search)
        layout.addWidget(self._items_table)
        layout.addLayout(form_layout)
        layout.addWidget(create_button)
        layout.addStretch()
        self._refresh_amounts()

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
