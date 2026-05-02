from __future__ import annotations

from decimal import Decimal
from typing import Callable

from PyQt6.QtCore import QDateTime, pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QDateTimeEdit,
    QFormLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from core.config import MAX_MONEY_INPUT
from core.exceptions import ValidationError
from modules.customer.dto import CustomerDTO
from modules.sales.controller import SalesController
from modules.sales.controller import SellableProductOption
from modules.sales.models import Invoice
from modules.sales.ui.customer_picker_widget import CustomerPickerWidget
from modules.sales.ui.invoice_items_table import InvoiceItemsTable
from modules.sales.ui.scale import scaled, scaled_font
from modules.settings.service import get_ui_scale_factor, get_ui_scale_preset
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox
from shared.widgets.numeric_inputs import SelectAllSpinBox


class SalesPage(QWidget):
    transaction_changed = pyqtSignal()

    def __init__(
        self,
        controller: SalesController,
        *,
        invoice: Invoice | None = None,
        on_edit_completed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._ui_scale = 1.0
        self._search_products: list[SellableProductOption] = list(controller.list_sellable_products())
        self._editing_invoice_id: int | None = None
        self._editing_customer: CustomerDTO | None = None
        self._editing_walk_in = False
        self._on_edit_completed = on_edit_completed

        self._items_table = InvoiceItemsTable()
        self._items_table.setMinimumHeight(420)
        self._items_table.setColumnHidden(0, True)
        self._items_table.horizontalHeaderItem(1).setText("Tên hàng")
        self._items_table.horizontalHeaderItem(2).setText("Đơn vị")
        self._items_table.horizontalHeaderItem(3).setText("Số lượng")
        self._items_table.horizontalHeaderItem(4).setText("Đơn giá")
        self._items_table.horizontalHeaderItem(5).setText("Thành tiền")
        self._items_table.totals_changed.connect(self._refresh_amounts)

        self._note_input = QTextEdit()
        self._note_input.setPlaceholderText("Ghi chú đơn hàng")
        self._note_input.setMaximumHeight(92)

        self._customer_picker = CustomerPickerWidget(list(controller.list_customers()), self, compact=True)
        self._customer_picker.customer_changed.connect(self._refresh_amounts)

        self._invoice_datetime_input = QDateTimeEdit(QDateTime.currentDateTime())
        self._invoice_datetime_input.setCalendarPopup(True)
        self._invoice_datetime_input.setDisplayFormat("dd/MM/yyyy HH:mm")

        self._total_label = QLabel(format_money(Decimal("0")))
        self._amount_due_label = QLabel(format_money(Decimal("0")))
        self._paid_amount_input = SelectAllSpinBox()
        self._paid_amount_input.setRange(0, MAX_MONEY_INPUT)
        self._paid_amount_input.valueChanged.connect(self._refresh_amounts)
        self._change_label = QLabel("")
        self._create_button = QPushButton("Thanh toán")
        self._create_button.clicked.connect(self._submit_invoice)

        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        left_layout.addWidget(self._items_table, 1)
        left_layout.addWidget(self._note_input, 0)

        summary_form = QFormLayout()
        summary_form.setContentsMargins(0, 0, 0, 0)
        summary_form.setSpacing(10)
        summary_form.addRow("Tổng tiền hàng", self._total_label)
        summary_form.addRow("Khách cần trả", self._amount_due_label)
        summary_form.addRow("Khách thanh toán", self._paid_amount_input)
        summary_form.addRow("Tiền thừa", self._change_label)

        self._right_top_panel = QWidget()
        right_top_layout = QVBoxLayout(self._right_top_panel)
        right_top_layout.setContentsMargins(0, 0, 0, 0)
        right_top_layout.setSpacing(12)

        datetime_row = QHBoxLayout()
        datetime_row.setContentsMargins(0, 0, 0, 0)
        datetime_row.addStretch()
        datetime_row.addWidget(self._invoice_datetime_input)

        right_top_layout.addLayout(datetime_row)
        right_top_layout.addWidget(self._customer_picker)
        right_top_layout.addLayout(summary_form)

        self._right_footer = QWidget()
        right_footer_layout = QVBoxLayout(self._right_footer)
        right_footer_layout.setContentsMargins(0, 0, 0, 0)
        right_footer_layout.addWidget(self._create_button)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        right_layout.addWidget(self._right_top_panel, 0)
        right_layout.addStretch(1)
        right_layout.addWidget(self._right_footer, 0)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(14)
        self._left_container = QWidget()
        self._left_container.setLayout(left_layout)
        self._right_container = QWidget()
        self._right_container.setLayout(right_layout)
        self._right_container.setMaximumWidth(430)
        main_layout.addWidget(self._left_container, 5)
        main_layout.addWidget(self._right_container, 2)

        self.apply_ui_scale_preset(get_ui_scale_preset())
        self._refresh_amounts()
        if invoice is not None:
            self._load_invoice_for_edit(invoice)

    def apply_ui_scale_preset(self, preset: str) -> None:
        self._ui_scale = get_ui_scale_factor(preset)
        factor = self._ui_scale
        self.layout().setSpacing(scaled(14, factor))
        self._customer_picker.apply_ui_scale(factor)
        self._items_table.verticalHeader().setDefaultSectionSize(scaled(56, factor))
        self._items_table.verticalHeader().setMinimumSectionSize(scaled(56, factor))
        self._right_container.setMaximumWidth(scaled(430, factor))
        self._note_input.setMaximumHeight(scaled(92, factor))
        self._note_input.setStyleSheet(
            f"font-size: {scaled_font(15, factor)}px; padding: {scaled(8, factor)}px;"
        )
        self._invoice_datetime_input.setMinimumHeight(scaled(42, factor))
        self._invoice_datetime_input.setStyleSheet(
            f"font-size: {scaled_font(16, factor)}px; padding: {scaled(6, factor)}px {scaled(10, factor)}px;"
        )
        self._total_label.setStyleSheet(f"font-size: {scaled_font(24, factor)}px; font-weight: 700;")
        self._amount_due_label.setStyleSheet(f"font-size: {scaled_font(20, factor)}px; font-weight: 600;")
        self._paid_amount_input.setMinimumHeight(scaled(44, factor))
        self._paid_amount_input.setStyleSheet(
            f"font-size: {scaled_font(18, factor)}px; padding: {scaled(8, factor)}px {scaled(12, factor)}px;"
        )
        self._change_label.setStyleSheet(f"font-size: {scaled_font(18, factor)}px;")
        self._create_button.setMinimumHeight(scaled(52, factor))
        self._create_button.setStyleSheet(
            f"font-size: {scaled_font(20, factor)}px; font-weight: 700; padding: {scaled(8, factor)}px {scaled(16, factor)}px;"
        )
        right_layout = self.layout().itemAt(1).widget().layout()
        summary_layout = self._right_top_panel.layout().itemAt(2).layout()
        if right_layout is not None:
            right_layout.setSpacing(scaled(12, factor))
        if summary_layout is not None:
            summary_layout.setSpacing(scaled(8, factor))
            for row in range(summary_layout.rowCount()):
                label_item = summary_layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if label_item is not None and label_item.widget() is not None:
                    label_item.widget().setStyleSheet(
                        f"font-size: {scaled_font(15, factor)}px; font-weight: 600;"
                    )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.reload_data()

    def reload_data(self) -> None:
        self._search_products = list(self._controller.list_sellable_products())
        customers = list(self._controller.list_customers())
        self._customer_picker.reload_data(customers)
        if self._editing_invoice_id is not None:
            if self._editing_customer is not None:
                self._editing_customer = next((customer for customer in customers if customer.id == self._editing_customer.id), self._editing_customer)
            self._customer_picker.lock_customer(None if self._editing_walk_in else self._editing_customer)
        self._refresh_amounts()

    def add_product_payload(self, item: dict[str, object]) -> None:
        self._items_table.add_or_merge_item(dict(item))

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
        if product is None:
            return
        self.add_product_payload(self._build_shared_search_payload(product))

    def activate_shared_search_best_match(self, query: str) -> None:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return
        product = next((product for product in self._search_products if normalized_query in product.product_name.lower()), None)
        if product is not None:
            self.add_product_payload(self._build_shared_search_payload(product))

    @staticmethod
    def _build_shared_search_payload(product: SellableProductOption) -> dict[str, object]:
        unit_type = next(iter(product.enabled_prices), None)
        if unit_type is None:
            return {}
        unit_price = product.enabled_prices[unit_type]
        quantity = Decimal("1")
        return {
            "product_id": product.product_id,
            "product_code_base": product.product_code_base,
            "product_name": product.product_name,
            "unit_type": unit_type,
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": quantity * unit_price,
            "stock_available": product.stock_by_unit.get(unit_type, Decimal("0")),
            "enabled_prices": dict(product.enabled_prices),
            "stock_by_unit": dict(product.stock_by_unit),
        }

    def _refresh_amounts(self) -> None:
        total_amount = self._items_table.total_amount()
        self._total_label.setText(format_money(total_amount))
        self._amount_due_label.setText(format_money(total_amount))
        paid_amount = Decimal(self._paid_amount_input.value())
        overpayment = max(paid_amount - total_amount, Decimal("0"))
        self._change_label.setText(format_money(overpayment) if overpayment > Decimal("0") else "-")
        self._create_button.setVisible(True)

    def _submit_invoice(self) -> None:
        if self._editing_invoice_id is not None:
            self._update_invoice()
            return
        self._create_invoice()

    def _create_invoice(self) -> None:
        try:
            items = self._items_table.items_payload()
            if not items:
                raise ValidationError("Phải có ít nhất 1 dòng hàng hóa.")
            customer_id = self._customer_picker.selected_customer_id()
            paid_amount = Decimal(self._paid_amount_input.value())
            total_amount = self._items_table.total_amount()
            if customer_id is None and paid_amount < total_amount:
                raise ValidationError("Khách lẻ phải trả đủ tiền hóa đơn.")

            invoice = self._controller.create_invoice(
                customer_id=customer_id,
                customer_snapshot_name=self._customer_picker.snapshot_name(),
                invoice_datetime=self._invoice_datetime_input.dateTime().toPyDateTime(),
                items=items,
                paid_amount=paid_amount,
                payment_method=None,
                note=self._note_input.toPlainText().strip() or None,
            )
            MessageBox.info(self, "Thành công", f"Đã tạo hóa đơn {invoice.invoice_code}")
            self.transaction_changed.emit()
            self.reload_data()
            self._reset_form()
        except Exception as exc:
            MessageBox.error(self, "Không tạo được hóa đơn", str(exc))

    def _update_invoice(self) -> None:
        try:
            if self._editing_invoice_id is None:
                raise ValidationError("Không có hóa đơn đang sửa.")
            items = self._items_table.items_payload()
            if not items:
                raise ValidationError("Phải có ít nhất 1 dòng hàng hóa.")
            paid_amount = Decimal(self._paid_amount_input.value())
            total_amount = self._items_table.total_amount()
            if self._editing_walk_in and paid_amount < total_amount:
                raise ValidationError("Khách lẻ phải trả đủ tiền hóa đơn.")

            invoice = self._controller.update_invoice(
                self._editing_invoice_id,
                items=items,
                invoice_datetime=self._invoice_datetime_input.dateTime().toPyDateTime(),
                paid_amount=paid_amount,
                note=self._note_input.toPlainText().strip(),
            )
            MessageBox.info(self, "Thành công", f"Đã cập nhật hóa đơn {invoice.invoice_code}")
            self.transaction_changed.emit()
            self.reload_data()
            if self._on_edit_completed is not None:
                self._on_edit_completed()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được hóa đơn", str(exc))

    def _reset_form(self) -> None:
        self._customer_picker.reset()
        self._items_table.clear_items()
        self._note_input.clear()
        self._paid_amount_input.setValue(0)
        self._invoice_datetime_input.setDateTime(QDateTime.currentDateTime())
        self._refresh_amounts()

    def _load_invoice_for_edit(self, invoice: Invoice) -> None:
        self._editing_invoice_id = invoice.id
        self._editing_walk_in = invoice.customer_id is None
        self._items_table.clear_items()
        for item in invoice.items:
            self._items_table.add_or_merge_item(
                {
                    "product_id": item.product_id,
                    "product_code_base": item.product_code_snapshot,
                    "product_name": item.product_name_snapshot,
                    "unit_type": item.unit_type,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "line_total": item.line_total,
                }
            )
        self._note_input.setText(invoice.note or "")
        self._invoice_datetime_input.setDateTime(QDateTime(invoice.invoice_datetime))
        self._paid_amount_input.setValue(int(invoice.paid_amount or Decimal("0")))
        self._create_button.setText("Cập nhật")
        self._editing_customer = next(
            (customer for customer in self._controller.list_customers() if customer.id == invoice.customer_id),
            None,
        )
        self._customer_picker.lock_customer(None if self._editing_walk_in else self._editing_customer)
        self._refresh_amounts()
