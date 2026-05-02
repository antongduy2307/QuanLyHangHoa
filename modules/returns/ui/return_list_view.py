from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from modules.returns.controller import ReturnController
from modules.returns.models import ReturnInvoice
from modules.returns.ui.return_detail_popup import ReturnDetailPopup
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.autocomplete_line_edit import AutocompleteLineEdit
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class ReturnListView(QWidget):
    def __init__(
        self,
        controller: ReturnController,
        *,
        on_history_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._on_history_changed = on_history_changed
        self._returns: list[ReturnInvoice] = []

        self._search_input = AutocompleteLineEdit()
        self._search_input.setPlaceholderText("Tìm theo tên khách hàng")
        self._search_input.textChanged.connect(self._apply_filter)
        self._search_input.suggestion_selected.connect(self._handle_search_suggestion_selected)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Khách hàng", "Tổng trả", "Xử lý", "Thời điểm"])
        configure_table_widget(self._table, "returns.list")
        self._table.itemDoubleClicked.connect(self._open_detail)

        view_button = QPushButton("Xem")
        view_button.clicked.connect(self._open_detail)
        delete_button = QPushButton("Xóa")
        delete_button.clicked.connect(self._delete_return)
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
            self._returns = list(self._controller.list_return_invoices())
            self._apply_filter()
        except Exception as exc:
            MessageBox.error(self, "Không tải được lịch sử trả hàng", str(exc))

    def _apply_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        if not query:
            filtered = self._returns
        else:
            filtered = [return_invoice for return_invoice in self._returns if query in return_invoice.customer_snapshot_name.lower()]
        self._render_rows(filtered)
        self._update_search_suggestions(query, filtered)

    def _update_search_suggestions(self, query: str, rows: list[ReturnInvoice]) -> None:
        if not query:
            self._search_input.hide_suggestions()
            return
        seen_names: set[str] = set()
        suggestions: list[tuple[str, object]] = []
        for row in rows:
            customer_name = row.customer_snapshot_name
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

    def _render_rows(self, rows: list[ReturnInvoice]) -> None:
        self._table.setRowCount(len(rows))
        for row_index, return_invoice in enumerate(rows):
            self._table.setItem(row_index, 0, QTableWidgetItem(return_invoice.customer_snapshot_name))
            self._table.setItem(row_index, 1, QTableWidgetItem(format_money(return_invoice.total_amount)))
            self._table.setItem(row_index, 2, QTableWidgetItem(return_invoice.handling_mode.value))
            self._table.setItem(row_index, 3, QTableWidgetItem(format_datetime(return_invoice.return_datetime)))
            self._table.item(row_index, 0).setData(Qt.ItemDataRole.UserRole, return_invoice.id)

    def _selected_return_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _open_detail(self, *_args: object) -> None:
        return_id = self._selected_return_id()
        if return_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một phiếu trả hàng để xem.")
            return
        try:
            return_invoice = self._controller.get_return_invoice_detail(return_id)
            ReturnDetailPopup(return_invoice, self, controller=self._controller, on_updated=self._handle_history_changed).exec()
        except Exception as exc:
            MessageBox.error(self, "Không tải được chi tiết trả hàng", str(exc))

    def _open_edit(self) -> None:
        return_id = self._selected_return_id()
        if return_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một phiếu trả hàng để sửa.")
            return
        app_window = self.window()
        if hasattr(app_window, "open_sales_return_editor"):
            app_window.open_sales_return_editor(return_id)
            return
        MessageBox.warning(self, "Chưa hỗ trợ", "Không mở được tab sửa phiếu trả hàng từ màn hình hiện tại.")

    def _delete_return(self) -> None:
        return_id = self._selected_return_id()
        if return_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một phiếu trả hàng để xóa.")
            return

        confirmed = QMessageBox.question(self, "Xác nhận xóa", "Xóa phiếu trả hàng đã chọn?")
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        try:
            self._controller.delete_return_invoice(return_id)
            MessageBox.info(self, "Thành công", "Đã xóa phiếu trả hàng.")
            self._handle_history_changed()
        except Exception as exc:
            MessageBox.error(self, "Không xóa được phiếu trả hàng", str(exc))

    def _handle_history_changed(self) -> None:
        if self._on_history_changed is not None:
            self._on_history_changed()
            return
        self.reload()
