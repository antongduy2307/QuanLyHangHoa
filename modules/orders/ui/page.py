from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from modules.orders.controller import OrderController
from modules.orders.models import OrderRequest
from modules.orders.service import OrderService
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

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Ngày đặt", "Tên khách hàng", "Ngày cần giao", "Ghi chú", "Trạng thái"])
        self._table.setProperty("column_minimum_widths", {0: 160, 1: 220, 2: 160, 3: 260, 4: 130})
        configure_table_widget(self._table, "orders.active_list")
        self._table.itemDoubleClicked.connect(self._open_detail)

        open_button = QPushButton("Xem")
        open_button.clicked.connect(self._open_detail)
        refresh_button = QPushButton("Làm mới")
        refresh_button.clicked.connect(self.reload)

        controls = QHBoxLayout()
        controls.addStretch()
        controls.addWidget(open_button)
        controls.addWidget(refresh_button)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self._table, 1)
        apply_large_ui(self)
        self.reload()

    def reload(self) -> None:
        try:
            self._orders = list(self._controller.list_active_orders())
            self._render_rows()
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
                "Đã hoàn thành" if order.status == "PREPARED" else "Đang mở",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {0, 2, 4}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if order.status == "PREPARED":
                    item.setBackground(prepared_color)
                self._table.setItem(row, column, item)
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, order.id)

    def _selected_order_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _open_detail(self, *_args: object) -> None:
        order_id = self._selected_order_id()
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
