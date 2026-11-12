from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from modules.orders.controller import OrderController
from modules.orders.models import OrderRequest
from modules.orders.service import OrderQuantitySummary, OrderService
from modules.orders.ui.order_detail_popup import OrderDetailPopup
from shared.formatting.dates import format_datetime
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget
from shared.widgets.ui_scale import apply_large_ui


class OrdersPage(QWidget):
    order_changed = pyqtSignal()

    def __init__(self, service: OrderService) -> None:
        super().__init__()
        self._controller = OrderController(service._repository._session_factory)
        self._orders: list[OrderRequest] = []
        self._summary_rows: list[OrderQuantitySummary] = []
        self._converted_orders: list[OrderRequest] = []

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Ngày đặt", "Tên khách hàng", "Ngày cần giao", "Ghi chú", "Trạng thái"])
        self._table.setProperty("column_minimum_widths", {0: 160, 1: 220, 2: 160, 3: 260, 4: 130})
        configure_table_widget(self._table, "orders.active_list")
        self._table.itemDoubleClicked.connect(self._open_detail)

        customer_tab = QWidget()
        customer_layout = QVBoxLayout(customer_tab)
        customer_layout.setContentsMargins(0, 0, 0, 0)
        customer_layout.addWidget(self._table, 1)

        self._summary_search_input = QLineEdit()
        self._summary_search_input.setPlaceholderText("Tìm theo tên hàng")
        self._summary_search_input.textChanged.connect(self._render_summary_rows)

        self._summary_sort_combo = QComboBox()
        self._summary_sort_combo.addItem("Sắp xếp: Số lượng", "quantity")
        self._summary_sort_combo.addItem("Sắp xếp: Tên hàng", "name")
        self._summary_sort_combo.currentIndexChanged.connect(self._render_summary_rows)

        self._summary_table = QTableWidget(0, 5)
        self._summary_table.setHorizontalHeaderLabels(["Mã hàng", "Tên hàng", "Đơn vị", "Tổng số lượng cần làm", "Tồn kho hiện tại"])
        self._summary_table.setProperty("column_minimum_widths", {0: 120, 1: 280, 2: 120, 3: 190, 4: 160})
        configure_table_widget(self._summary_table, "orders.quantity_summary")

        summary_controls = QHBoxLayout()
        summary_controls.setContentsMargins(0, 0, 0, 0)
        summary_controls.addWidget(self._summary_search_input, 1)
        summary_controls.addWidget(self._summary_sort_combo, 0)

        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.addLayout(summary_controls)
        summary_layout.addWidget(self._summary_table, 1)

        self._converted_table = QTableWidget(0, 5)
        self._converted_table.setHorizontalHeaderLabels(["Ngày bán", "Tên khách hàng", "Ngày đặt", "Mã hóa đơn", "Ghi chú"])
        self._converted_table.setProperty("column_minimum_widths", {0: 160, 1: 220, 2: 160, 3: 160, 4: 260})
        configure_table_widget(self._converted_table, "orders.converted_list")
        self._converted_table.itemDoubleClicked.connect(self._open_converted_detail)

        converted_tab = QWidget()
        converted_layout = QVBoxLayout(converted_tab)
        converted_layout.setContentsMargins(0, 0, 0, 0)
        converted_layout.addWidget(self._converted_table, 1)

        self._tabs = QTabWidget()
        self._tabs.addTab(customer_tab, "Khách hàng")
        self._tabs.addTab(summary_tab, "Tổng số lượng hàng cần làm")
        self._tabs.addTab(converted_tab, "Đã bán")

        layout = QVBoxLayout(self)
        layout.addWidget(self._tabs, 1)
        apply_large_ui(self)
        self.reload()

    def reload(self) -> None:
        try:
            self._orders = list(self._controller.list_active_orders())
            self._summary_rows = list(self._controller.list_active_quantity_summary())
            self._converted_orders = list(self._controller.list_converted_orders())
            self._render_rows()
            self._render_summary_rows()
            self._render_converted_rows()
        except Exception as exc:
            MessageBox.error(self, "Không tải được đơn đặt hàng", str(exc))

    def _render_rows(self) -> None:
        self._table.setRowCount(len(self._orders))
        prepared_color = QColor("#d1fae5")
        for row, order in enumerate(self._orders):
            values = [
                format_datetime(order.order_datetime),
                order.customer_name_snapshot,
                format_datetime(order.required_delivery_datetime) if order.required_delivery_datetime is not None else "-",
                order.note or "",
                self._status_text(order),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {0, 2, 4}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if order.status == "PREPARED":
                    item.setBackground(prepared_color)
                self._table.setItem(row, column, item)
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, order.id)

    @staticmethod
    def _status_text(order: OrderRequest) -> str:
        if order.status == "PREPARED":
            return "Đã hoàn thành"
        total = len(order.items)
        done = sum(1 for item in order.items if item.is_done)
        if done == 0 or total == 0:
            return "Đang mở"
        return f"Đang mở · xong {done}/{total}"

    def _render_summary_rows(self) -> None:
        query = self._summary_search_input.text().strip().lower()
        rows = [
            row for row in self._summary_rows
            if not query or query in row.product_name.lower()
        ]
        if self._summary_sort_combo.currentData() == "name":
            rows.sort(key=lambda row: (row.product_name.lower(), row.unit_type.value, row.product_id))
        else:
            rows.sort(key=lambda row: (row.quantity, row.product_name.lower(), row.unit_type.value), reverse=True)

        self._summary_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                str(row.product_id),
                row.product_name,
                row.unit_type.value,
                self._format_quantity(row.quantity),
                "-" if row.stock_available is None else self._format_quantity(row.stock_available),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {2, 3, 4}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._summary_table.setItem(row_index, column, item)

    def _render_converted_rows(self) -> None:
        self._converted_table.setRowCount(len(self._converted_orders))
        for row, order in enumerate(self._converted_orders):
            invoice = order.source_invoice
            values = [
                format_datetime(order.completed_at) if order.completed_at is not None else "-",
                order.customer_name_snapshot,
                format_datetime(order.order_datetime),
                invoice.invoice_code if invoice is not None else "-",
                order.note or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {0, 2, 3}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._converted_table.setItem(row, column, item)
            self._converted_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, order.id)

    @staticmethod
    def _selected_id_in(table: QTableWidget) -> int | None:
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _selected_order_id(self) -> int | None:
        return self._selected_id_in(self._table)

    def _open_converted_detail(self, *_args: object) -> None:
        self._open_order_popup(self._selected_id_in(self._converted_table))

    def _open_detail(self, *_args: object) -> None:
        self._open_order_popup(self._selected_order_id())

    def _open_order_popup(self, order_id: int | None) -> None:
        if order_id is None:
            return
        try:
            order = self._controller.get_order(order_id)
            popup = OrderDetailPopup(order, self._controller, self)
            popup.order_changed.connect(self._handle_order_changed)
            popup.exec()
        except Exception as exc:
            MessageBox.error(self, "Không tải được chi tiết đơn đặt hàng", str(exc))

    def _handle_order_changed(self) -> None:
        self.reload()
        self.order_changed.emit()

    @staticmethod
    def _format_quantity(quantity: Decimal) -> str:
        if quantity == quantity.to_integral_value():
            return f"{quantity:,.0f}"
        return f"{quantity:,.3f}".rstrip("0").rstrip(".")
