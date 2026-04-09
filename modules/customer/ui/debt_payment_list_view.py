from __future__ import annotations

from decimal import Decimal

from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

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
    def __init__(self, controller: CustomerController) -> None:
        super().__init__()
        self._controller = controller
        self._payments: list[CustomerBalanceLedger] = []

        self._search_input = AutocompleteLineEdit()
        self._search_input.setPlaceholderText("Tìm theo tên khách hàng")
        self._search_input.textChanged.connect(self._apply_filter)
        self._search_input.suggestion_selected.connect(self._handle_search_suggestion_selected)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Thời gian", "Mã giao dịch", "Tên khách", "Điện thoại", "Số tiền trả nợ"])
        configure_table_widget(self._table, "customer.debt_payment_list")
        self._table.itemDoubleClicked.connect(self._open_detail)

        view_button = QPushButton("Xem")
        view_button.clicked.connect(self._open_detail)
        edit_button = QPushButton("Sửa")
        edit_button.clicked.connect(self._open_edit)
        refresh_button = QPushButton("Làm mới")
        refresh_button.clicked.connect(self.reload)

        controls = QHBoxLayout()
        controls.addWidget(self._search_input, 1)
        controls.addWidget(view_button)
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
        suggestions = []
        for entry in rows[:20]:
            customer_name = entry.customer.customer_name if entry.customer else "-"
            suggestions.append((customer_name, entry.id))
        self._search_input.set_suggestions(suggestions)

    def _handle_search_suggestion_selected(self, ledger_id: object) -> None:
        if ledger_id is None:
            return
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(256) == int(ledger_id):
                self._table.setCurrentCell(row_index, 0)
                break

    def _render_rows(self, rows: list[CustomerBalanceLedger]) -> None:
        self._table.setRowCount(len(rows))
        for row_index, entry in enumerate(rows):
            self._table.setItem(row_index, 0, QTableWidgetItem(format_datetime(entry.created_at)))
            self._table.setItem(row_index, 1, QTableWidgetItem(str(entry.ref_id)))
            self._table.setItem(row_index, 2, QTableWidgetItem(entry.customer.customer_name if entry.customer else '-'))
            self._table.setItem(row_index, 3, QTableWidgetItem(entry.customer.phone if entry.customer and entry.customer.phone else '-'))
            self._table.setItem(row_index, 4, QTableWidgetItem(format_money(abs(entry.amount_delta))))
            self._table.item(row_index, 0).setData(256, entry.id)

    def _selected_ledger_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return None if item is None else item.data(256)

    def _open_detail(self, *_args: object) -> None:
        ledger_id = self._selected_ledger_id()
        if ledger_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một giao dịch trả nợ để xem.")
            return
        try:
            ledger = self._controller.get_debt_payment_detail(ledger_id)
            DebtPaymentDetailPopup(ledger, controller=self._controller, on_updated=self.reload, parent=self).exec()
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
            )
            if dialog.exec():
                payload = dialog.payload()
                self._controller.update_debt_payment(ledger.id, Decimal(payload["amount"]), note=payload["note"])
                MessageBox.info(self, "Thành công", "Đã cập nhật giao dịch trả nợ.")
                self.reload()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được giao dịch trả nợ", str(exc))
