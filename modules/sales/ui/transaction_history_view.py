from __future__ import annotations

from datetime import datetime
from typing import Callable

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QComboBox, QDateEdit, QHBoxLayout, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

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
    def __init__(
        self,
        controller: SalesController,
        *,
        on_history_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._on_history_changed = on_history_changed
        self._rows: list[TransactionHistoryRow] = []

        self._search_input = AutocompleteLineEdit()
        self._search_input.setPlaceholderText("Tìm theo tên khách hàng")
        self._search_input.textChanged.connect(self.reload)
        self._search_input.suggestion_selected.connect(self._handle_search_suggestion_selected)

        self._type_combo = QComboBox()
        self._type_combo.addItem("Tất cả", "ALL")
        self._type_combo.addItem("Hóa đơn", "INVOICE")
        self._type_combo.addItem("Trả hàng", "RETURN")
        self._type_combo.addItem("Trả nợ", "DEBT_PAYMENT")
        self._type_combo.currentIndexChanged.connect(self.reload)

        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Mới nhất trước", "newest")
        self._sort_combo.addItem("Cũ nhất trước", "oldest")
        self._sort_combo.currentIndexChanged.connect(self.reload)

        today = QDate.currentDate()
        self._start_date = QDateEdit(today.addDays(-30))
        self._start_date.setCalendarPopup(True)
        self._end_date = QDateEdit(today)
        self._end_date.setCalendarPopup(True)
        self._start_date.dateChanged.connect(self.reload)
        self._end_date.dateChanged.connect(self.reload)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Khách hàng", "Loại giao dịch", "Số tiền giao dịch", "Thời gian giao dịch"])
        configure_table_widget(self._table, "sales.transaction_history")
        self._table.itemDoubleClicked.connect(self._open_detail)

        view_button = QPushButton("Xem")
        view_button.clicked.connect(self._open_detail)
        delete_button = QPushButton("Xóa")
        delete_button.clicked.connect(self._delete_transaction)
        self._edit_button = QPushButton("Sửa")
        self._edit_button.clicked.connect(self._open_edit)
        refresh_button = QPushButton("Làm mới")
        refresh_button.clicked.connect(self.reload)

        controls = QHBoxLayout()
        controls.addWidget(self._search_input, 1)
        controls.addWidget(self._type_combo)
        controls.addWidget(self._start_date)
        controls.addWidget(self._end_date)
        controls.addWidget(self._sort_combo)
        controls.addWidget(view_button)
        controls.addWidget(delete_button)
        controls.addWidget(self._edit_button)
        controls.addWidget(refresh_button)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self._table)

        self.reload()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.reload()

    def reload(self) -> None:
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

    def open_transaction_detail(self, transaction_kind: str, transaction_id: int) -> None:
        self._open_transaction_detail(transaction_kind, transaction_id)

    def _update_search_suggestions(self, query: str, rows: list[TransactionHistoryRow]) -> None:
        if not query:
            self._search_input.hide_suggestions()
            return
        seen_names: set[str] = set()
        suggestions: list[tuple[str, object]] = []
        for row in rows:
            customer_name = row.customer_name
            if customer_name in seen_names:
                continue
            seen_names.add(customer_name)
            suggestions.append((customer_name, customer_name))
            if len(suggestions) >= 20:
                break
        self._search_input.set_suggestions(suggestions)

    def _handle_search_suggestion_selected(self, customer_name: object) -> None:
        if not isinstance(customer_name, str):
            return
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.text() == customer_name:
                self._table.setCurrentCell(row_index, 0)
                break

    def _render_rows(self) -> None:
        self._table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            self._table.setItem(row_index, 0, QTableWidgetItem(row.customer_name))
            self._table.setItem(row_index, 1, QTableWidgetItem(self._type_label(row.transaction_type)))
            self._table.setItem(row_index, 2, QTableWidgetItem(format_money(row.amount)))
            self._table.setItem(row_index, 3, QTableWidgetItem(format_datetime(row.transaction_datetime)))
            self._table.item(row_index, 0).setData(Qt.ItemDataRole.UserRole, (row.transaction_type, row.transaction_id))

    def _selected_transaction(self) -> tuple[str, int] | None:
        row_index = self._table.currentRow()
        if row_index < 0:
            return None
        item = self._table.item(row_index, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _open_detail(self, *_args: object) -> None:
        payload = self._selected_transaction()
        if payload is None:
            return
        self._open_transaction_detail(*payload)

    def _open_transaction_detail(self, transaction_type: str, transaction_id: int) -> None:
        try:
            if transaction_type == "INVOICE":
                invoice = self._controller.get_invoice_detail(transaction_id)
                InvoiceDetailPopup(invoice, self, controller=self._controller, on_updated=self._handle_history_changed).exec()
            elif transaction_type == "RETURN":
                return_controller = ReturnController(SessionFactory)
                return_invoice = return_controller.get_return_invoice_detail(transaction_id)
                ReturnDetailPopup(return_invoice, self, controller=return_controller, on_updated=self._handle_history_changed).exec()
            elif transaction_type == "DEBT_PAYMENT":
                customer_controller = CustomerController(SessionFactory)
                ledger = customer_controller.get_debt_payment_detail(transaction_id)
                DebtPaymentDetailPopup(ledger, self, controller=customer_controller, on_updated=self._handle_history_changed).exec()
        except Exception as exc:
            MessageBox.error(self, "Không tải được chi tiết giao dịch", str(exc))

    def _open_edit(self) -> None:
        payload = self._selected_transaction()
        if payload is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một giao dịch để sửa.")
            return
        transaction_type, transaction_id = payload
        app_window = self.window()
        if transaction_type == "INVOICE" and hasattr(app_window, "open_sales_invoice_editor"):
            app_window.open_sales_invoice_editor(transaction_id)
            return
        if transaction_type == "RETURN" and hasattr(app_window, "open_sales_return_editor"):
            app_window.open_sales_return_editor(transaction_id)
            return
        if transaction_type == "DEBT_PAYMENT":
            MessageBox.warning(self, "Chưa hỗ trợ", "Hãy sửa giao dịch trả nợ từ tab Trả nợ.")
            return
        MessageBox.warning(self, "Chưa hỗ trợ", "Không mở được tab sửa từ màn hình hiện tại.")

    def _delete_transaction(self) -> None:
        payload = self._selected_transaction()
        if payload is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một giao dịch để xóa.")
            return

        transaction_type, transaction_id = payload
        confirmed = QMessageBox.question(
            self,
            "Xác nhận xóa",
            f"Xóa {self._type_label(transaction_type).lower()} đã chọn?",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        try:
            if transaction_type == "INVOICE":
                self._controller.delete_invoice(transaction_id)
            elif transaction_type == "RETURN":
                return_controller = ReturnController(SessionFactory)
                return_controller.delete_return_invoice(transaction_id)
            elif transaction_type == "DEBT_PAYMENT":
                customer_controller = CustomerController(SessionFactory)
                customer_controller.delete_debt_payment(transaction_id)
            else:
                raise ValueError("Loại giao dịch không được hỗ trợ.")
            MessageBox.info(self, "Thành công", "Đã xóa giao dịch.")
            self._handle_history_changed()
        except Exception as exc:
            MessageBox.error(self, "Không xóa được giao dịch", str(exc))

    def _handle_history_changed(self) -> None:
        if self._on_history_changed is not None:
            self._on_history_changed()
            return
        self.reload()

    @staticmethod
    def _type_label(transaction_type: str) -> str:
        return {
            "INVOICE": "Hóa đơn",
            "RETURN": "Trả hàng",
            "DEBT_PAYMENT": "Trả nợ",
        }.get(transaction_type, transaction_type)
