from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import QDate
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QComboBox, QDateEdit, QHBoxLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.db import SessionFactory
from modules.customer.controller import CustomerController
from modules.customer.ui.debt_payment_detail_popup import DebtPaymentDetailPopup
from modules.returns.controller import ReturnController
from modules.returns.ui.return_detail_popup import ReturnDetailPopup
from modules.sales.controller import SalesController, TransactionHistoryRow
from modules.sales.ui.invoice_detail_popup import InvoiceDetailPopup
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.autocomplete_line_edit import AutocompleteLineEdit
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class TransactionHistoryView(QWidget):
    def __init__(self, controller: SalesController) -> None:
        super().__init__()
        self._controller = controller
        self._rows: list[TransactionHistoryRow] = []

        self._search_input = AutocompleteLineEdit()
        self._search_input.setPlaceholderText("Tìm theo tên khách hoặc mã giao dịch")
        self._search_input.textChanged.connect(self._reload)
        self._search_input.suggestion_selected.connect(self._handle_search_suggestion_selected)

        self._type_combo = QComboBox()
        self._type_combo.addItem("Tất cả", "ALL")
        self._type_combo.addItem("Hóa đơn", "INVOICE")
        self._type_combo.addItem("Trả hàng", "RETURN")
        self._type_combo.addItem("Trả nợ", "DEBT_PAYMENT")
        self._type_combo.currentIndexChanged.connect(self._reload)

        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Mới nhất trước", "newest")
        self._sort_combo.addItem("Cũ nhất trước", "oldest")
        self._sort_combo.currentIndexChanged.connect(self._reload)

        today = QDate.currentDate()
        self._start_date = QDateEdit(today.addDays(-30))
        self._start_date.setCalendarPopup(True)
        self._end_date = QDateEdit(today)
        self._end_date.setCalendarPopup(True)
        self._start_date.dateChanged.connect(self._reload)
        self._end_date.dateChanged.connect(self._reload)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Thời gian giao dịch", "Loại giao dịch", "Mã giao dịch", "Tên khách", "Số tiền giao dịch"])
        configure_table_widget(self._table, "sales.transaction_history")
        self._table.itemDoubleClicked.connect(self._open_detail)

        controls = QHBoxLayout()
        controls.addWidget(self._search_input, 1)
        controls.addWidget(self._type_combo)
        controls.addWidget(self._start_date)
        controls.addWidget(self._end_date)
        controls.addWidget(self._sort_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self._table)

        self._reload()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._reload()

    def _reload(self) -> None:
        try:
            start = datetime.combine(self._start_date.date().toPyDate(), datetime.min.time())
            end = datetime.combine(self._end_date.date().toPyDate(), datetime.max.time())
            self._rows = list(
                self._controller.list_transaction_history(
                    query=self._search_input.text(),
                    transaction_type=str(self._type_combo.currentData()),
                    start_datetime=start,
                    end_datetime=end,
                    sort_option=str(self._sort_combo.currentData()),
                )
            )
            self._render_rows()
            self._update_search_suggestions(self._search_input.text().strip(), self._rows)
        except Exception as exc:
            MessageBox.error(self, "Không tải được lịch sử giao dịch", str(exc))

    def _update_search_suggestions(self, query: str, rows: list[TransactionHistoryRow]) -> None:
        if not query:
            self._search_input.hide_suggestions()
            return
        suggestions = [(f"{row.transaction_code} | {row.customer_name}", (row.transaction_type, row.transaction_id)) for row in rows[:20]]
        self._search_input.set_suggestions(suggestions)

    def _handle_search_suggestion_selected(self, payload: object) -> None:
        if not isinstance(payload, tuple):
            return
        transaction_type, transaction_id = payload
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(256) == (transaction_type, transaction_id):
                self._table.setCurrentCell(row_index, 0)
                break

    def _render_rows(self) -> None:
        self._table.setRowCount(len(self._rows))
        type_map = {"INVOICE": "Hóa đơn", "RETURN": "Trả hàng", "DEBT_PAYMENT": "Trả nợ"}
        for row_index, row in enumerate(self._rows):
            self._table.setItem(row_index, 0, QTableWidgetItem(format_datetime(row.transaction_datetime)))
            self._table.setItem(row_index, 1, QTableWidgetItem(type_map.get(row.transaction_type, row.transaction_type)))
            self._table.setItem(row_index, 2, QTableWidgetItem(row.transaction_code))
            self._table.setItem(row_index, 3, QTableWidgetItem(row.customer_name))
            self._table.setItem(row_index, 4, QTableWidgetItem(format_money(row.amount)))
            self._table.item(row_index, 0).setData(256, (row.transaction_type, row.transaction_id))

    def _open_detail(self, *_args: object) -> None:
        row_index = self._table.currentRow()
        if row_index < 0:
            return
        payload = self._table.item(row_index, 0).data(256)
        if payload is None:
            return
        transaction_type, transaction_id = payload
        try:
            if transaction_type == "INVOICE":
                invoice = self._controller.get_invoice_detail(transaction_id)
                InvoiceDetailPopup(invoice, self).exec()
            elif transaction_type == "RETURN":
                return_controller = ReturnController(SessionFactory)
                return_invoice = return_controller.get_return_invoice_detail(transaction_id)
                ReturnDetailPopup(return_invoice, self, controller=return_controller, on_updated=self._reload).exec()
            elif transaction_type == "DEBT_PAYMENT":
                customer_controller = CustomerController(SessionFactory)
                ledger = customer_controller.get_debt_payment_detail(transaction_id)
                DebtPaymentDetailPopup(ledger, self, controller=customer_controller, on_updated=self._reload).exec()
        except Exception as exc:
            MessageBox.error(self, "Không tải được chi tiết giao dịch", str(exc))

