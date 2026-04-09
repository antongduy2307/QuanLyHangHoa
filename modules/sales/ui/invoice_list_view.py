from __future__ import annotations

from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QMessageBox

from modules.sales.controller import SalesController
from modules.sales.models import Invoice
from modules.sales.ui.invoice_detail_popup import InvoiceDetailPopup
from modules.sales.ui.invoice_edit_dialog import InvoiceEditDialog
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.autocomplete_line_edit import AutocompleteLineEdit
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class InvoiceListView(QWidget):
    def __init__(self, controller: SalesController) -> None:
        super().__init__()
        self._controller = controller
        self._invoices: list[Invoice] = []

        self._search_input = AutocompleteLineEdit()
        self._search_input.setPlaceholderText("Tìm theo tên khách hàng")
        self._search_input.textChanged.connect(self._apply_filter)
        self._search_input.suggestion_selected.connect(self._handle_search_suggestion_selected)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(["Mã hóa đơn", "Thời điểm", "Khách", "Tổng tiền", "Khách trả", "Thanh toán", "Số dòng"])
        configure_table_widget(self._table, "sales.invoice_list")
        self._table.itemDoubleClicked.connect(self._open_detail)

        view_button = QPushButton("Xem")
        view_button.clicked.connect(self._open_detail)
        edit_button = QPushButton("Sửa")
        edit_button.clicked.connect(self._open_edit)
        delete_button = QPushButton("Xóa")
        delete_button.clicked.connect(self._delete_invoice)
        refresh_button = QPushButton("Làm mới")
        refresh_button.clicked.connect(self.reload)

        controls = QHBoxLayout()
        controls.addWidget(self._search_input, 1)
        controls.addWidget(view_button)
        controls.addWidget(edit_button)
        controls.addWidget(delete_button)
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
            self._invoices = list(self._controller.list_invoices())
            self._apply_filter()
        except Exception as exc:
            MessageBox.error(self, "Không tải được hóa đơn", str(exc))

    def _apply_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        if not query:
            filtered = self._invoices
        else:
            filtered = [invoice for invoice in self._invoices if query in invoice.customer_snapshot_name.lower()]
        self._render_rows(filtered)
        self._update_search_suggestions(query, filtered)

    def _update_search_suggestions(self, query: str, invoices: list[Invoice]) -> None:
        if not query:
            self._search_input.hide_suggestions()
            return
        suggestions = [(invoice.customer_snapshot_name, invoice.id) for invoice in invoices[:20]]
        self._search_input.set_suggestions(suggestions)

    def _handle_search_suggestion_selected(self, invoice_id: object) -> None:
        if invoice_id is None:
            return
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(256) == int(invoice_id):
                self._table.setCurrentCell(row_index, 0)
                break

    def _render_rows(self, invoices: list[Invoice]) -> None:
        self._table.setRowCount(len(invoices))
        for row_index, invoice in enumerate(invoices):
            self._table.setItem(row_index, 0, QTableWidgetItem(invoice.invoice_code))
            self._table.setItem(row_index, 1, QTableWidgetItem(format_datetime(invoice.invoice_datetime)))
            self._table.setItem(row_index, 2, QTableWidgetItem(invoice.customer_snapshot_name))
            self._table.setItem(row_index, 3, QTableWidgetItem(format_money(invoice.total_amount)))
            self._table.setItem(row_index, 4, QTableWidgetItem(format_money(invoice.paid_amount or 0)))
            self._table.setItem(row_index, 5, QTableWidgetItem(invoice.payment_method.value if invoice.payment_method else '-'))
            self._table.setItem(row_index, 6, QTableWidgetItem(str(len(invoice.items))))
            self._table.item(row_index, 0).setData(256, invoice.id)

    def _selected_invoice_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return None if item is None else item.data(256)

    def _open_detail(self, *_args: object) -> None:
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            return
        try:
            invoice = self._controller.get_invoice_detail(invoice_id)
            InvoiceDetailPopup(invoice, self).exec()
        except Exception as exc:
            MessageBox.error(self, "Không tải được chi tiết hóa đơn", str(exc))

    def _open_edit(self) -> None:
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một hóa đơn để sửa.")
            return
        try:
            invoice = self._controller.get_invoice_detail(invoice_id)
            dialog = InvoiceEditDialog(self._controller, invoice, self)
            if dialog.exec():
                self.reload()
        except Exception as exc:
            MessageBox.error(self, "Không sửa được hóa đơn", str(exc))

    def _delete_invoice(self) -> None:
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một hóa đơn để xóa.")
            return
        confirmed = QMessageBox.question(self, "Xác nhận xóa", "Bạn có chắc muốn xóa hóa đơn này không?")
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self._controller.delete_invoice(invoice_id)
            self.reload()
        except Exception as exc:
            MessageBox.error(self, "Không xóa được hóa đơn", str(exc))
