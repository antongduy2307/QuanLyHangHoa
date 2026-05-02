from __future__ import annotations

from decimal import Decimal
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from modules.customer.controller import CustomerController
from modules.customer.mappers import to_dto
from modules.customer.models import CustomerBalanceLedger
from modules.customer.ui.debt_payment_detail_popup import DebtPaymentDetailPopup
from modules.customer.ui.debt_payment_dialog import DebtPaymentDialog
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.autocomplete_line_edit import AutocompleteLineEdit
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class DebtPaymentListView(QWidget):
    def __init__(
        self,
        controller: CustomerController,
        *,
        on_history_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._on_history_changed = on_history_changed
        self._payments: list[CustomerBalanceLedger] = []

        self._search_input = AutocompleteLineEdit()
        self._search_input.setPlaceholderText("Tìm theo tên khách hàng")
        self._search_input.textChanged.connect(self._apply_filter)
        self._search_input.suggestion_selected.connect(self._handle_search_suggestion_selected)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Tên khách", "Điện thoại", "Số tiền trả nợ", "Thời gian"])
        configure_table_widget(self._table, "customer.debt_payment_list")
        self._table.itemDoubleClicked.connect(self._open_detail)

        view_button = QPushButton("Xem")
        view_button.clicked.connect(self._open_detail)
        delete_button = QPushButton("Xóa")
        delete_button.clicked.connect(self._delete_payment)
        edit_button = QPushButton("Sửa")
        edit_button.clicked.connect(self._open_edit)
        refresh_button = QPushButton("Làm mới")
        refresh_button.clicked.connect(self.reload)

        controls = QHBoxLayout()
        controls.addWidget(self._search_input, 1)
        controls.addWidget(view_button)
        controls.addWidget(delete_button)
        controls.addWidget(edit_button)
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
            self._payments = list(self._controller.list_debt_payments())
            self._apply_filter()
        except Exception as exc:
            MessageBox.error(self, "Không tải được lịch sử trả nợ", str(exc))

    def _apply_filter(self) -> None:
        query = self._search_input.text().strip()
        filtered = self._controller.search_debt_payments(query) if query else self._payments
        rows = list(filtered)
        self._render_rows(rows)
        self._update_search_suggestions(query, rows)

    def _update_search_suggestions(self, query: str, rows: list[CustomerBalanceLedger]) -> None:
        if not query:
            self._search_input.hide_suggestions()
            return
        seen_names: set[str] = set()
        suggestions: list[tuple[str, object]] = []
        for entry in rows:
            customer_name = entry.customer.customer_name if entry.customer else "-"
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

    def _render_rows(self, rows: list[CustomerBalanceLedger]) -> None:
        self._table.setRowCount(len(rows))
        for row_index, entry in enumerate(rows):
            self._table.setItem(row_index, 0, QTableWidgetItem(entry.customer.customer_name if entry.customer else "-"))
            self._table.setItem(row_index, 1, QTableWidgetItem(entry.customer.phone if entry.customer and entry.customer.phone else "-"))
            self._table.setItem(row_index, 2, QTableWidgetItem(format_money(abs(entry.amount_delta))))
            self._table.setItem(row_index, 3, QTableWidgetItem(format_datetime(entry.effective_transaction_datetime)))
            self._table.item(row_index, 0).setData(Qt.ItemDataRole.UserRole, entry.id)

    def _selected_ledger_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _open_detail(self, *_args: object) -> None:
        ledger_id = self._selected_ledger_id()
        if ledger_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một giao dịch trả nợ để xem.")
            return
        try:
            ledger = self._controller.get_debt_payment_detail(ledger_id)
            DebtPaymentDetailPopup(ledger, controller=self._controller, on_updated=self._handle_history_changed, parent=self).exec()
        except Exception as exc:
            MessageBox.error(self, "Không tải được chi tiết trả nợ", str(exc))

    def _open_edit(self) -> None:
        ledger_id = self._selected_ledger_id()
        if ledger_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một giao dịch trả nợ để sửa.")
            return
        try:
            ledger = self._controller.get_debt_payment_detail(ledger_id)
            if ledger.customer is None:
                raise ValueError("Không tìm thấy khách hàng của giao dịch trả nợ.")
            dialog = DebtPaymentDialog(
                to_dto(ledger.customer),
                self,
                edit_mode=True,
                amount=abs(ledger.amount_delta),
                note=ledger.note,
                payment_datetime=ledger.effective_transaction_datetime,
            )
            if dialog.exec():
                payload = dialog.payload()
                self._controller.update_debt_payment(
                    ledger.id,
                    Decimal(payload["amount"]),
                    note=payload["note"],
                    payment_datetime=payload["payment_datetime"],
                )
                MessageBox.info(self, "Thành công", "Đã cập nhật giao dịch trả nợ.")
                self._handle_history_changed()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được giao dịch trả nợ", str(exc))

    def _delete_payment(self) -> None:
        ledger_id = self._selected_ledger_id()
        if ledger_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một giao dịch trả nợ để xóa.")
            return

        confirmed = QMessageBox.question(self, "Xác nhận xóa", "Xóa giao dịch trả nợ đã chọn?")
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        try:
            self._controller.delete_debt_payment(ledger_id)
            MessageBox.info(self, "Thành công", "Đã xóa giao dịch trả nợ.")
            self._handle_history_changed()
        except Exception as exc:
            MessageBox.error(self, "Không xóa được giao dịch trả nợ", str(exc))

    def _handle_history_changed(self) -> None:
        if self._on_history_changed is not None:
            self._on_history_changed()
            return
        self.reload()
