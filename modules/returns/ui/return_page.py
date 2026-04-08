from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QComboBox, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget

from core.enums import ReturnHandlingMode
from core.exceptions import ValidationError
from modules.returns.controller import ReturnController, SourceInvoiceDetail
from modules.returns.ui.product_search_widget import QuickReturnProductSearchWidget
from modules.returns.ui.return_summary_widget import ReturnSummaryWidget
from modules.returns.ui.source_invoice_items_table import SourceInvoiceItemsTable
from modules.returns.ui.source_invoice_search_widget import SourceInvoiceSearchWidget
from modules.sales.ui.invoice_items_table import InvoiceItemsTable
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox


class ReturnPage(QWidget):
    def __init__(self, controller: ReturnController) -> None:
        super().__init__()
        self._controller = controller
        self._current_detail: SourceInvoiceDetail | None = None
        self._quick_customers = []

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_invoice_mode_tab(), "Trả theo hóa đơn")
        self._tabs.addTab(self._build_quick_mode_tab(), "Trả hàng nhanh")

        layout = QVBoxLayout(self)
        title = QLabel("Trả hàng")
        subtitle = QLabel("Chọn trả theo hóa đơn hoặc trả hàng nhanh để tạo phiếu trả hàng qua ReturnService.")
        subtitle.setProperty("class", "muted")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._tabs)

        self._reload_quick_mode_data()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._reload_quick_mode_data()

    def _build_invoice_mode_tab(self) -> QWidget:
        container = QWidget(self)
        self._search_widget = SourceInvoiceSearchWidget(container)
        self._search_widget.search_button.clicked.connect(self._search_invoices)
        self._search_widget.invoice_selected.connect(self._load_invoice_detail)

        self._source_header = QLabel("Chưa chọn hóa đơn nguồn")
        self._source_header.setWordWrap(True)
        self._source_header.setProperty("class", "muted")

        self._items_table = SourceInvoiceItemsTable()
        self._items_table.totals_changed.connect(self._refresh_invoice_total)

        self._summary_widget = ReturnSummaryWidget(container)
        create_button = QPushButton("Tạo phiếu trả hàng")
        create_button.clicked.connect(self._create_return_invoice)

        layout = QVBoxLayout(container)
        layout.addWidget(self._search_widget)
        layout.addWidget(self._source_header)
        layout.addWidget(self._items_table)
        layout.addWidget(self._summary_widget)
        layout.addWidget(create_button)
        layout.addStretch()
        return container

    def _build_quick_mode_tab(self) -> QWidget:
        container = QWidget(self)

        self._quick_customer_combo = QComboBox()
        self._quick_customer_combo.currentIndexChanged.connect(self._refresh_quick_customer_state)
        self._quick_customer_balance_label = QLabel("")
        self._quick_customer_balance_label.setProperty("class", "muted")

        self._quick_product_search = QuickReturnProductSearchWidget([], container)
        self._quick_product_search.item_added.connect(self._handle_quick_item_added)

        self._quick_items_table = InvoiceItemsTable()
        self._quick_remove_row_at = self._quick_items_table.remove_row_at
        self._quick_items_table.remove_row_at = self._remove_quick_row_and_refresh  # type: ignore[method-assign]

        self._quick_summary_widget = ReturnSummaryWidget(container)
        create_button = QPushButton("Tạo phiếu trả hàng nhanh")
        create_button.clicked.connect(self._create_quick_return_invoice)

        layout = QVBoxLayout(container)
        layout.addWidget(QLabel("Khách"))
        layout.addWidget(self._quick_customer_combo)
        layout.addWidget(self._quick_customer_balance_label)
        layout.addWidget(self._quick_product_search)
        layout.addWidget(self._quick_items_table)
        layout.addWidget(self._quick_summary_widget)
        layout.addWidget(create_button)
        layout.addStretch()
        return container

    def _reload_quick_mode_data(self) -> None:
        current_customer_id = self._quick_customer_combo.currentData() if hasattr(self, "_quick_customer_combo") else None
        self._quick_customers = list(self._controller.list_quick_return_customers()) if hasattr(self, "_quick_customer_combo") else []
        if hasattr(self, "_quick_customer_combo"):
            self._quick_customer_combo.blockSignals(True)
            self._quick_customer_combo.clear()
            self._quick_customer_combo.addItem("Khách lẻ", None)
            selected_index = 0
            for customer in self._quick_customers:
                self._quick_customer_combo.addItem(f"{customer.customer_name} - {customer.phone or '-'}", customer.id)
                if customer.id == current_customer_id:
                    selected_index = self._quick_customer_combo.count() - 1
            self._quick_customer_combo.setCurrentIndex(selected_index)
            self._quick_customer_combo.blockSignals(False)
            self._refresh_quick_customer_state()
        if hasattr(self, "_quick_product_search"):
            self._quick_product_search.reload_data(self._controller.list_quick_return_products())

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
            customer_label = "Khách lẻ" if detail.customer_id is None else detail.customer_name
            balance_label = "" if detail.current_balance is None else f" | Công nợ hiện tại: {detail.current_balance:,.0f}"
            self._source_header.setText(
                f"Hóa đơn: {detail.invoice_code} | Thời điểm: {detail.invoice_datetime:%d/%m/%Y %H:%M} | {customer_label}{balance_label}"
            )
            self._items_table.load_items(list(detail.items))
            self._summary_widget.set_walk_in_mode(detail.customer_id is None)
            self._refresh_invoice_total()
        except Exception as exc:
            MessageBox.error(self, "Không tải được hóa đơn nguồn", str(exc))

    def _refresh_invoice_total(self) -> None:
        self._summary_widget.set_total(self._items_table.total_amount())

    def _refresh_quick_total(self) -> None:
        self._quick_summary_widget.set_total(self._quick_items_table.total_amount())

    def _selected_quick_customer(self):
        customer_id = self._quick_customer_combo.currentData()
        if customer_id is None:
            return None
        return next((customer for customer in self._quick_customers if customer.id == customer_id), None)

    def _refresh_quick_customer_state(self) -> None:
        customer = self._selected_quick_customer()
        if customer is None:
            self._quick_customer_balance_label.setText("Khách lẻ - chỉ hỗ trợ hoàn tiền ngay")
            self._quick_summary_widget.set_walk_in_mode(True)
        else:
            self._quick_customer_balance_label.setText(f"Công nợ hiện tại: {format_money(customer.current_balance)}")
            self._quick_summary_widget.set_walk_in_mode(False)
        self._refresh_quick_total()

    def _handle_quick_item_added(self, item: object) -> None:
        self._quick_items_table.add_or_merge_item(dict(item))
        self._refresh_quick_total()

    def _remove_quick_row_and_refresh(self, row_index: int) -> None:
        self._quick_remove_row_at(row_index)
        self._refresh_quick_total()

    def _create_return_invoice(self) -> None:
        try:
            if self._current_detail is None:
                raise ValidationError("Chưa chọn hóa đơn nguồn.")
            items = self._items_table.selected_return_items()
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
            self._reset_invoice_form()
        except Exception as exc:
            MessageBox.error(self, "Không tạo được phiếu trả hàng", str(exc))

    def _create_quick_return_invoice(self) -> None:
        try:
            items = self._quick_items_table.items_payload()
            if not items:
                raise ValidationError("Phải có ít nhất 1 dòng trả hàng nhanh.")
            customer = self._selected_quick_customer()
            customer_id = None if customer is None else customer.id
            if customer_id is None and self._quick_summary_widget.selected_mode() != ReturnHandlingMode.REFUND_NOW:
                raise ValidationError("Khách lẻ chỉ được phép hoàn tiền ngay.")
            return_invoice = self._controller.create_quick_return_invoice(
                customer_id=customer_id,
                customer_snapshot_name="Khách lẻ" if customer is None else customer.customer_name,
                return_datetime=datetime.now(),
                items=items,
                handling_mode=self._quick_summary_widget.selected_mode().value,
                note=self._quick_summary_widget.note_input.text() or None,
            )
            MessageBox.info(self, "Thành công", f"Đã tạo phiếu trả hàng {return_invoice.return_code}")
            self._reset_quick_form()
            self._reload_quick_mode_data()
        except Exception as exc:
            MessageBox.error(self, "Không tạo được phiếu trả hàng nhanh", str(exc))

    def _reset_invoice_form(self) -> None:
        self._current_detail = None
        self._search_widget.search_input.clear()
        self._search_widget.set_results([])
        self._source_header.setText("Chưa chọn hóa đơn nguồn")
        self._items_table.reset()
        self._summary_widget.reset()

    def _reset_quick_form(self) -> None:
        self._quick_product_search.reset()
        self._quick_items_table.clear_items()
        self._quick_summary_widget.reset()
        self._quick_customer_combo.setCurrentIndex(0)
        self._refresh_quick_customer_state()
