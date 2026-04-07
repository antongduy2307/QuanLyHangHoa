from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from core.enums import ReturnHandlingMode
from core.exceptions import ValidationError
from modules.returns.controller import ReturnController, SourceInvoiceDetail
from modules.returns.ui.return_summary_widget import ReturnSummaryWidget
from modules.returns.ui.source_invoice_items_table import SourceInvoiceItemsTable
from modules.returns.ui.source_invoice_search_widget import SourceInvoiceSearchWidget
from shared.widgets.message_box import MessageBox


class ReturnPage(QWidget):
    def __init__(self, controller: ReturnController) -> None:
        super().__init__()
        self._controller = controller
        self._current_detail: SourceInvoiceDetail | None = None

        self._search_widget = SourceInvoiceSearchWidget(self)
        self._search_widget.search_button.clicked.connect(self._search_invoices)
        self._search_widget.invoice_selected.connect(self._load_invoice_detail)

        self._source_header = QLabel("Chưa chọn hóa đơn nguồn")
        self._source_header.setWordWrap(True)
        self._source_header.setProperty("class", "muted")

        self._items_table = SourceInvoiceItemsTable()
        self._items_table.totals_changed.connect(self._refresh_total)

        self._summary_widget = ReturnSummaryWidget(self)
        create_button = QPushButton("Tạo phiếu trả hàng")
        create_button.clicked.connect(self._create_return_invoice)

        layout = QVBoxLayout(self)
        title = QLabel("Trả hàng")
        subtitle = QLabel("Tìm hóa đơn nguồn, nhập số lượng trả và tạo phiếu trả hàng qua ReturnService.")
        subtitle.setProperty("class", "muted")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._search_widget)
        layout.addWidget(self._source_header)
        layout.addWidget(self._items_table)
        layout.addWidget(self._summary_widget)
        layout.addWidget(create_button)
        layout.addStretch()

    def _search_invoices(self) -> None:
        try:
            rows = list(self._controller.search_source_invoices(self._search_widget.search_input.text()))
            self._search_widget.set_results(rows)
        except Exception as exc:
            MessageBox.error(self, "Không tìm được hóa đơn", str(exc))

    def _load_invoice_detail(self, invoice_id: int) -> None:
        try:
            detail = self._controller.load_source_invoice_details(invoice_id)
            self._current_detail = detail
            customer_label = "Khách lẻ" if detail.customer_id is None else detail.customer_name
            balance_label = "" if detail.current_balance is None else f" | Công nợ hiện tại: {detail.current_balance:,.0f}"
            self._source_header.setText(
                f"Hóa đơn: {detail.invoice_code} | Thời điểm: {detail.invoice_datetime:%d/%m/%Y %H:%M} | {customer_label}{balance_label}"
            )
            self._items_table.load_items(list(detail.items))
            self._summary_widget.set_walk_in_mode(detail.customer_id is None)
            self._refresh_total()
        except Exception as exc:
            MessageBox.error(self, "Không tải được hóa đơn nguồn", str(exc))

    def _refresh_total(self) -> None:
        self._summary_widget.set_total(self._items_table.total_amount())

    def _create_return_invoice(self) -> None:
        try:
            if self._current_detail is None:
                raise ValidationError("Chưa chọn hóa đơn nguồn.")
            items = self._items_table.selected_return_items()
            if not items:
                raise ValidationError("Phải nhập ít nhất 1 dòng trả hàng > 0.")
            for row, payload in zip(self._current_detail.items, items, strict=False):
                quantity = Decimal(str(payload["quantity"]))
                if quantity < Decimal("0"):
                    raise ValidationError("Số lượng trả phải >= 0.")
                if quantity > row.remaining_returnable_quantity:
                    raise ValidationError("Số lượng trả không được vượt quá số lượng còn lại.")
            if self._current_detail.customer_id is None and self._summary_widget.selected_mode() != ReturnHandlingMode.REFUND_NOW:
                raise ValidationError("Khách lẻ chỉ được phép hoàn tiền ngay.")

            return_invoice = self._controller.create_return_invoice(
                source_invoice_id=self._current_detail.invoice_id,
                return_datetime=datetime.now(),
                items=items,
                handling_mode=self._summary_widget.selected_mode().value,
                note=self._summary_widget.note_input.text() or None,
            )
            MessageBox.info(self, "Thành công", f"Đã tạo phiếu trả hàng {return_invoice.return_code}")
            self._reset_form()
        except Exception as exc:
            MessageBox.error(self, "Không tạo được phiếu trả hàng", str(exc))

    def _reset_form(self) -> None:
        self._current_detail = None
        self._search_widget.search_input.clear()
        self._search_widget.set_results([])
        self._source_header.setText("Chưa chọn hóa đơn nguồn")
        self._items_table.reset()
        self._summary_widget.reset()

