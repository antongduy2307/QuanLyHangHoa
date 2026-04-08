from __future__ import annotations

from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from modules.returns.controller import ReturnController
from modules.returns.models import ReturnInvoice
from modules.returns.ui.return_detail_popup import ReturnDetailPopup
from modules.returns.ui.return_edit_dialog import ReturnEditDialog
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class ReturnListView(QWidget):
    def __init__(self, controller: ReturnController) -> None:
        super().__init__()
        self._controller = controller
        self._returns: list[ReturnInvoice] = []

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Tìm theo mã trả hàng")
        self._search_input.textChanged.connect(self._apply_filter)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(["Mã trả hàng", "Thời điểm", "Hóa đơn gốc", "Khách", "Tổng trả", "Xử lý"])
        configure_table_widget(self._table)
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
            self._returns = list(self._controller.list_return_invoices())
            self._apply_filter()
        except Exception as exc:
            MessageBox.error(self, "Không tải được lịch sử trả hàng", str(exc))

    def _apply_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        if not query:
            filtered = self._returns
        else:
            filtered = [return_invoice for return_invoice in self._returns if query in return_invoice.return_code.lower()]
        self._render_rows(filtered)

    def _render_rows(self, rows: list[ReturnInvoice]) -> None:
        self._table.setRowCount(len(rows))
        for row_index, return_invoice in enumerate(rows):
            source_invoice_code = return_invoice.source_invoice.invoice_code if return_invoice.source_invoice else "Trả nhanh"
            customer_name = return_invoice.customer_snapshot_name
            self._table.setItem(row_index, 0, QTableWidgetItem(return_invoice.return_code))
            self._table.setItem(row_index, 1, QTableWidgetItem(format_datetime(return_invoice.return_datetime)))
            self._table.setItem(row_index, 2, QTableWidgetItem(source_invoice_code))
            self._table.setItem(row_index, 3, QTableWidgetItem(customer_name))
            self._table.setItem(row_index, 4, QTableWidgetItem(format_money(return_invoice.total_amount)))
            self._table.setItem(row_index, 5, QTableWidgetItem(return_invoice.handling_mode.value))
            self._table.item(row_index, 0).setData(256, return_invoice.id)

    def _selected_return_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return None if item is None else item.data(256)

    def _open_detail(self, *_args: object) -> None:
        return_id = self._selected_return_id()
        if return_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một phiếu trả hàng để xem.")
            return
        try:
            return_invoice = self._controller.get_return_invoice_detail(return_id)
            ReturnDetailPopup(return_invoice, self, controller=self._controller, on_updated=self.reload).exec()
        except Exception as exc:
            MessageBox.error(self, "Không tải được chi tiết trả hàng", str(exc))

    def _open_edit(self) -> None:
        return_id = self._selected_return_id()
        if return_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một phiếu trả hàng để sửa.")
            return
        try:
            return_invoice = self._controller.get_return_invoice_detail(return_id)
            if return_invoice.source_invoice_id is None:
                MessageBox.warning(self, "Chưa hỗ trợ", "Chưa hỗ trợ sửa phiếu trả hàng nhanh ở bước này.")
                return
            detail = self._controller.get_return_edit_detail(return_id)
            dialog = ReturnEditDialog(self._controller, detail, self)
            if dialog.exec():
                MessageBox.info(self, "Thành công", "Đã cập nhật phiếu trả hàng.")
                self.reload()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được phiếu trả hàng", str(exc))
