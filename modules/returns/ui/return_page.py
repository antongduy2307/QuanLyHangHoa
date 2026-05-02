from __future__ import annotations

from decimal import Decimal
from typing import Callable

from PyQt6.QtCore import QDateTime, pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QDateTimeEdit,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from core.enums import ReturnHandlingMode, UnitType
from core.exceptions import ValidationError
from modules.returns.controller import QuickReturnProductOption, ReturnController, ReturnEditDetail, SourceInvoiceDetail, SourceInvoiceSearchRow
from modules.returns.models import ReturnInvoice
from modules.returns.ui.return_summary_widget import ReturnSummaryWidget
from modules.returns.ui.source_invoice_items_table import SourceInvoiceItemsTable
from modules.sales.ui.customer_picker_widget import CustomerPickerWidget
from modules.sales.ui.invoice_items_table import InvoiceItemsTable
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox
from shared.widgets.ui_scale import apply_large_ui


class ReturnPage(QWidget):
    transaction_changed = pyqtSignal()

    def __init__(
        self,
        controller: ReturnController,
        *,
        mode: str = "invoice",
        edit_return: ReturnInvoice | None = None,
        edit_detail: ReturnEditDetail | None = None,
        on_edit_completed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._mode = "quick" if mode == "quick" else "invoice"
        self._current_detail: SourceInvoiceDetail | None = None
        self._quick_products: list[QuickReturnProductOption] = []
        self._source_search_results: list[SourceInvoiceSearchRow] = []
        self._editing_return: ReturnInvoice | None = edit_return
        self._editing_detail = edit_detail
        self._on_edit_completed = on_edit_completed

        self._source_header = QLabel("Chưa chọn hóa đơn nguồn")
        self._source_header.setWordWrap(True)
        self._source_header.setProperty("class", "muted")

        self._customer_picker = CustomerPickerWidget(list(controller.list_quick_return_customers()), self, compact=True)
        self._customer_picker.customer_changed.connect(self._refresh_quick_summary)
        self._context_label = QLabel("")
        self._context_label.setWordWrap(True)
        self._context_label.setProperty("class", "muted")

        self._invoice_items_table = SourceInvoiceItemsTable()
        self._invoice_items_table.setMinimumHeight(360)
        self._invoice_items_table.totals_changed.connect(self._refresh_invoice_summary)

        self._quick_items_table = InvoiceItemsTable("returns.quick_items")
        self._quick_items_table.setMinimumHeight(360)
        self._quick_items_table.setColumnHidden(0, True)
        self._quick_items_table.horizontalHeaderItem(1).setText("Tên hàng")
        self._quick_items_table.horizontalHeaderItem(2).setText("Đơn vị")
        self._quick_items_table.horizontalHeaderItem(3).setText("Số lượng")
        self._quick_items_table.horizontalHeaderItem(4).setText("Đơn giá")
        self._quick_items_table.horizontalHeaderItem(5).setText("Thành tiền")
        self._quick_items_table.totals_changed.connect(self._refresh_quick_summary)

        self._note_input = QTextEdit()
        self._note_input.setPlaceholderText("Ghi chú trả hàng")
        self._note_input.setMaximumHeight(92)

        self._summary_widget = ReturnSummaryWidget(self)
        self._return_datetime_input = QDateTimeEdit(QDateTime.currentDateTime())
        self._return_datetime_input.setCalendarPopup(True)
        self._return_datetime_input.setDisplayFormat("dd/MM/yyyy HH:mm")
        self._create_button = QPushButton("Trả hàng")
        self._create_button.clicked.connect(self._submit_return)

        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        if self._mode == "invoice":
            left_layout.addWidget(self._source_header, 0)
        left_layout.addWidget(self._invoice_items_table if self._mode == "invoice" else self._quick_items_table, 1)
        left_layout.addWidget(self._note_input, 0)

        self._right_top_panel = QWidget()
        right_top_layout = QVBoxLayout(self._right_top_panel)
        right_top_layout.setContentsMargins(0, 0, 0, 0)
        right_top_layout.setSpacing(12)
        right_top_layout.addWidget(self._context_label)
        right_top_layout.addWidget(self._customer_picker)
        right_top_layout.addWidget(self._summary_widget)
        right_top_layout.addWidget(QLabel("Thời gian giao dịch"))
        right_top_layout.addWidget(self._return_datetime_input)

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

        self._sync_mode_context()
        apply_large_ui(self)
        self._reload_mode_data()
        if self._editing_return is not None:
            self._load_return_for_edit(self._editing_return, self._editing_detail)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._reload_mode_data()

    def apply_ui_scale_preset(self, preset: str) -> None:
        apply_large_ui(self, preset)

    def shared_search_placeholder(self) -> str:
        if self._editing_return is not None and self._mode == "invoice":
            return ""
        if self._mode == "invoice":
            return "Nhập mã hóa đơn nguồn"
        return "Tìm theo tên hàng"

    def shared_search_suggestions(self, query: str) -> list[tuple[str, object]]:
        if self._editing_return is not None and self._mode == "invoice":
            return []
        normalized_query = query.strip()
        if not normalized_query:
            return []
        if self._mode == "invoice":
            self._source_search_results = list(self._controller.search_source_invoices(normalized_query))
            return [
                (f"{row.invoice_code} | {row.customer_label}", row.invoice_id)
                for row in self._source_search_results[:20]
            ]

        normalized_lower = normalized_query.lower()
        matches = [product for product in self._quick_products if normalized_lower in product.product_name.lower()]
        return [(product.product_name, product.product_id) for product in matches[:20]]

    def activate_shared_search_selection(self, payload: object) -> None:
        if self._editing_return is not None and self._mode == "invoice":
            return
        if payload is None:
            return
        if self._mode == "invoice":
            self._load_invoice_detail(int(payload))
            return
        product = next((candidate for candidate in self._quick_products if candidate.product_id == int(payload)), None)
        if product is not None:
            self._quick_items_table.add_or_merge_item(self._build_quick_payload(product))

    def activate_shared_search_best_match(self, query: str) -> None:
        if self._editing_return is not None and self._mode == "invoice":
            return
        normalized_query = query.strip()
        if not normalized_query:
            return
        if self._mode == "invoice":
            rows = list(self._controller.search_source_invoices(normalized_query))
            if rows:
                self._load_invoice_detail(rows[0].invoice_id)
            return

        normalized_lower = normalized_query.lower()
        product = next((candidate for candidate in self._quick_products if normalized_lower in candidate.product_name.lower()), None)
        if product is not None:
            self._quick_items_table.add_or_merge_item(self._build_quick_payload(product))

    def _reload_mode_data(self) -> None:
        if self._mode == "quick":
            customers = list(self._controller.list_quick_return_customers())
            self._customer_picker.reload_data(customers)
            self._quick_products = list(self._controller.list_quick_return_products())
            if self._editing_return is not None:
                locked_customer = None
                if self._editing_return.customer_id is not None:
                    locked_customer = next((customer for customer in customers if customer.id == self._editing_return.customer_id), None)
                self._customer_picker.lock_customer(locked_customer)
            self._refresh_quick_summary()
        else:
            self._source_search_results = []
            self._refresh_invoice_summary()

    def _sync_mode_context(self) -> None:
        if self._mode == "invoice":
            self._customer_picker.hide()
            self._context_label.setText("Chọn hóa đơn nguồn để tải danh sách hàng trả")
            self._summary_widget.set_handling_mode(ReturnHandlingMode.REFUND_NOW)
            return

        self._customer_picker.show()
        self._context_label.setText("Chọn khách nếu cần ghi nhận công nợ hoặc lưu có")
        customer_id = self._customer_picker.selected_customer_id()
        handling_mode = ReturnHandlingMode.STORE_CREDIT if customer_id is not None else ReturnHandlingMode.REFUND_NOW
        self._summary_widget.set_handling_mode(handling_mode)

    def _load_invoice_detail(self, invoice_id: int) -> None:
        try:
            detail = self._controller.load_source_invoice_details(invoice_id)
            self._current_detail = detail
            self._source_header.setText(f"Hóa đơn: {detail.invoice_code} | Thời điểm: {detail.invoice_datetime:%d/%m/%Y %H:%M}")
            customer_label = "Khách lẻ" if detail.customer_id is None else detail.customer_name
            if detail.current_balance is None:
                self._context_label.setText(f"Hóa đơn nguồn thuộc: {customer_label}")
            else:
                self._context_label.setText(
                    f"Hóa đơn nguồn thuộc: {customer_label} | Công nợ hiện tại: {format_money(detail.current_balance)}"
                )
            self._invoice_items_table.load_items(list(detail.items))
            handling_mode = ReturnHandlingMode.STORE_CREDIT if detail.customer_id is not None else ReturnHandlingMode.REFUND_NOW
            self._summary_widget.set_handling_mode(handling_mode)
            self._refresh_invoice_summary()
        except Exception as exc:
            MessageBox.error(self, "Không tải được hóa đơn nguồn", str(exc))

    def _refresh_invoice_summary(self) -> None:
        if self._current_detail is None:
            self._summary_widget.set_original_total(Decimal("0"))
            self._summary_widget.set_return_total(Decimal("0"))
            self._summary_widget.set_refund_due(Decimal("0"))
            return
        original_total = sum((row.purchased_quantity * row.unit_price for row in self._current_detail.items), start=Decimal("0"))
        return_total = self._invoice_items_table.total_amount()
        refund_due = return_total if self._summary_widget.selected_mode() == ReturnHandlingMode.REFUND_NOW else Decimal("0")
        self._summary_widget.set_original_total(original_total)
        self._summary_widget.set_return_total(return_total)
        self._summary_widget.set_refund_due(refund_due)

    def _refresh_quick_summary(self) -> None:
        self._sync_mode_context()
        total = self._quick_items_table.total_amount()
        refund_due = total if self._summary_widget.selected_mode() == ReturnHandlingMode.REFUND_NOW else Decimal("0")
        self._summary_widget.set_original_total(total)
        self._summary_widget.set_return_total(total)
        self._summary_widget.set_refund_due(refund_due)

    def _create_return(self) -> None:
        if self._mode == "invoice":
            self._create_return_invoice()
        else:
            self._create_quick_return_invoice()

    def _submit_return(self) -> None:
        if self._editing_return is not None:
            self._update_return()
            return
        self._create_return()

    def _create_return_invoice(self) -> None:
        try:
            if self._current_detail is None:
                raise ValidationError("Chưa chọn hóa đơn nguồn.")
            items = self._invoice_items_table.selected_return_items()
            if not items:
                raise ValidationError("Phải nhập ít nhất 1 dòng trả hàng > 0.")
            row_by_source_item_id = {row.source_invoice_item_id: row for row in self._current_detail.items}
            for payload in items:
                quantity = Decimal(payload["quantity"])
                source_item_id = int(payload["source_invoice_item_id"])
                row = row_by_source_item_id[source_item_id]
                if quantity < Decimal("0"):
                    raise ValidationError("Số lượng trả phải >= 0.")
                if quantity > row.remaining_returnable_quantity:
                    raise ValidationError("Số lượng trả không được vượt quá số lượng còn lại.")

            return_invoice = self._controller.create_return_invoice(
                source_invoice_id=self._current_detail.invoice_id,
                return_datetime=self._return_datetime_input.dateTime().toPyDateTime(),
                items=items,
                handling_mode=self._summary_widget.selected_mode().value,
                note=self._note_input.toPlainText().strip() or None,
            )
            MessageBox.info(self, "Thành công", f"Đã tạo phiếu trả hàng {return_invoice.return_code}")
            self.transaction_changed.emit()
            self._reset_invoice_form()
        except Exception as exc:
            MessageBox.error(self, "Không tạo được phiếu trả hàng", str(exc))

    def _create_quick_return_invoice(self) -> None:
        try:
            items = self._quick_items_table.items_payload()
            if not items:
                raise ValidationError("Phải có ít nhất 1 dòng trả hàng nhanh.")
            customer_id = self._customer_picker.selected_customer_id()
            if customer_id is None and self._customer_picker.search_input.text().strip():
                raise ValidationError("Hãy chọn khách hàng từ danh sách gợi ý hoặc xóa ô tìm kiếm để trả cho khách lẻ.")
            return_invoice = self._controller.create_quick_return_invoice(
                customer_id=customer_id,
                customer_snapshot_name=self._customer_picker.snapshot_name(),
                return_datetime=self._return_datetime_input.dateTime().toPyDateTime(),
                items=items,
                handling_mode=self._summary_widget.selected_mode().value,
                note=self._note_input.toPlainText().strip() or None,
            )
            MessageBox.info(self, "Thành công", f"Đã tạo phiếu trả hàng {return_invoice.return_code}")
            self.transaction_changed.emit()
            self._reset_quick_form()
            self._reload_mode_data()
        except Exception as exc:
            MessageBox.error(self, "Không tạo được phiếu trả hàng", str(exc))

    def _reset_invoice_form(self) -> None:
        self._current_detail = None
        self._source_header.setText("Chưa chọn hóa đơn nguồn")
        self._invoice_items_table.reset()
        self._note_input.clear()
        self._return_datetime_input.setDateTime(QDateTime.currentDateTime())
        self._sync_mode_context()
        self._refresh_invoice_summary()

    def _reset_quick_form(self) -> None:
        self._quick_items_table.clear_items()
        self._customer_picker.reset()
        self._note_input.clear()
        self._return_datetime_input.setDateTime(QDateTime.currentDateTime())
        self._refresh_quick_summary()

    def _update_return(self) -> None:
        try:
            if self._editing_return is None:
                raise ValidationError("Không có phiếu trả hàng đang sửa.")
            if self._mode == "invoice":
                if self._current_detail is None:
                    raise ValidationError("Chưa có dữ liệu phiếu trả hàng để sửa.")
                items = self._invoice_items_table.selected_return_items()
                if not items:
                    raise ValidationError("Phải nhập ít nhất 1 dòng trả hàng > 0.")
            else:
                items = self._quick_items_table.items_payload()
                if not items:
                    raise ValidationError("Phải có ít nhất 1 dòng trả hàng nhanh.")

            updated = self._controller.update_return_invoice(
                self._editing_return.id,
                items=items,
                handling_mode=self._summary_widget.selected_mode().value,
                return_datetime=self._return_datetime_input.dateTime().toPyDateTime(),
                note=self._note_input.toPlainText().strip() or None,
            )
            MessageBox.info(self, "Thành công", f"Đã cập nhật phiếu trả hàng {updated.return_code}")
            self.transaction_changed.emit()
            self._reload_mode_data()
            if self._on_edit_completed is not None:
                self._on_edit_completed()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được phiếu trả hàng", str(exc))

    def _load_return_for_edit(self, return_invoice: ReturnInvoice, detail: ReturnEditDetail | None) -> None:
        self._create_button.setText("Cập nhật")
        self._note_input.setText(return_invoice.note or "")
        self._return_datetime_input.setDateTime(QDateTime(return_invoice.return_datetime))
        if return_invoice.customer_id is None:
            self._customer_picker.lock_customer(None)
        else:
            customers = list(self._controller.list_quick_return_customers())
            self._customer_picker.reload_data(customers)
            self._customer_picker.lock_customer(next((customer for customer in customers if customer.id == return_invoice.customer_id), None))

        if self._mode == "invoice" and detail is not None:
            base_detail = self._controller.load_source_invoice_details(detail.source_invoice_id)
            self._current_detail = SourceInvoiceDetail(
                invoice_id=base_detail.invoice_id,
                invoice_code=base_detail.invoice_code,
                invoice_datetime=base_detail.invoice_datetime,
                customer_name=base_detail.customer_name,
                customer_id=base_detail.customer_id,
                current_balance=base_detail.current_balance,
                items=detail.items,
            )
            self._source_header.setText(f"Hóa đơn: {detail.source_invoice_code} | Thời điểm: {base_detail.invoice_datetime:%d/%m/%Y %H:%M}")
            if detail.current_balance is None:
                self._context_label.setText(f"Hóa đơn nguồn thuộc: {detail.customer_name}")
            else:
                self._context_label.setText(
                    f"Hóa đơn nguồn thuộc: {detail.customer_name} | Công nợ hiện tại: {format_money(detail.current_balance)}"
                )
            self._invoice_items_table.load_items(list(detail.items), initial_quantities=detail.selected_quantities)
            self._summary_widget.set_handling_mode(detail.handling_mode)
            self._refresh_invoice_summary()
        elif self._mode == "quick":
            self._quick_items_table.clear_items()
            for item in return_invoice.items:
                self._quick_items_table.add_or_merge_item(
                    {
                        "product_id": item.product_id,
                        "product_code_base": item.product_code_snapshot,
                        "product_name": item.product_name_snapshot,
                        "unit_type": item.unit_type,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                        "line_total": item.line_total,
                        "enabled_prices": {},
                        "stock_by_unit": {},
                        "stock_available": Decimal("0"),
                    }
                )
            self._summary_widget.set_handling_mode(return_invoice.handling_mode)
            self._refresh_quick_summary()

    @staticmethod
    def _build_quick_payload(product: QuickReturnProductOption) -> dict[str, object]:
        unit_type = next(iter(product.enabled_prices), None)
        if unit_type is None:
            return {}
        price = product.enabled_prices[unit_type]
        quantity = Decimal("1")
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
