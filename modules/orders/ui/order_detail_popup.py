from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout

from modules.orders.controller import OrderController
from modules.orders.models import OrderRequest
from shared.formatting.dates import format_datetime
from shared.formatting.quantity import format_quantity
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


DONE_ROW_BACKGROUND = "#d1fae5"


class OrderDetailPopup(QDialog):
    order_changed = pyqtSignal()

    def __init__(self, order: OrderRequest, controller: OrderController, parent=None) -> None:
        super().__init__(parent)
        self._order = order
        self._controller = controller
        self.setWindowTitle(f"Chi tiết đơn đặt {order.order_code}")
        self.resize(720, 520)

        self._prepared_checkbox = QCheckBox("Đã hoàn thành")
        self._prepared_checkbox.setChecked(order.status == "PREPARED")
        self._prepared_checkbox.toggled.connect(self._toggle_prepared)

        header = QLabel(self._summary_text(order))
        header.setWordWrap(True)

        self._progress_label = QLabel()

        self._items_table = QTableWidget(0, 4)
        self._items_table.setHorizontalHeaderLabels(["Xong", "Tên hàng", "Đơn vị", "Số lượng"])
        self._items_table.setProperty("column_minimum_widths", {0: 70, 1: 320, 2: 120, 3: 120})
        configure_table_widget(self._items_table, "orders.detail_items.v2")
        self._render_items(order)
        self._items_table.itemChanged.connect(self._handle_item_changed)

        self._sell_button = QPushButton("Bán hàng")
        self._sell_button.clicked.connect(self._open_sales_draft)
        self._edit_button = QPushButton("Sửa")
        self._edit_button.clicked.connect(self._open_editor)
        self._delete_button = QPushButton("Xóa")
        self._delete_button.clicked.connect(self._delete_order)
        close_button = QPushButton("Đóng")
        close_button.clicked.connect(self.accept)

        footer = QHBoxLayout()
        footer.addWidget(self._prepared_checkbox)
        footer.addStretch()
        footer.addWidget(self._edit_button)
        footer.addWidget(self._delete_button)
        footer.addWidget(self._sell_button)
        footer.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(header)
        layout.addWidget(self._progress_label)
        layout.addWidget(self._items_table, 1)
        layout.addLayout(footer)

        if order.status == "CONVERTED":
            # Sold orders are read-only: only the close button stays available.
            for widget in (self._prepared_checkbox, self._edit_button, self._delete_button, self._sell_button):
                widget.setVisible(False)

    def _summary_text(self, order: OrderRequest) -> str:
        delivery = format_datetime(order.required_delivery_datetime) if order.required_delivery_datetime is not None else "-"
        note = order.note or "-"
        return (
            f"Mã đơn: {order.order_code}\n"
            f"Ngày đặt: {format_datetime(order.order_datetime)}\n"
            f"Khách hàng: {order.customer_name_snapshot}\n"
            f"Ngày cần giao: {delivery}\n"
            f"Ghi chú: {note}"
            f"{self._converted_text(order)}"
        )

    @staticmethod
    def _converted_text(order: OrderRequest) -> str:
        if order.status != "CONVERTED":
            return ""
        invoice = getattr(order, "source_invoice", None)
        invoice_code = invoice.invoice_code if invoice is not None else "-"
        sold_at = format_datetime(order.completed_at) if order.completed_at is not None else "-"
        return f"\nĐã bán: hóa đơn {invoice_code} lúc {sold_at}"

    def _render_items(self, order: OrderRequest) -> None:
        editable = order.status != "CONVERTED"
        self._items_table.blockSignals(True)
        self._items_table.setRowCount(len(order.items))
        for row, item in enumerate(order.items):
            done_item = QTableWidgetItem()
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if editable:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
            done_item.setFlags(flags)
            done_item.setCheckState(Qt.CheckState.Checked if item.is_done else Qt.CheckState.Unchecked)
            done_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self._items_table.setItem(row, 0, done_item)
            self._items_table.setItem(row, 1, QTableWidgetItem(item.product_name_snapshot))
            self._items_table.setItem(row, 2, QTableWidgetItem(item.unit_type.value))
            quantity_item = QTableWidgetItem(format_quantity(item.quantity))
            quantity_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._items_table.setItem(row, 3, quantity_item)
            self._apply_done_style(row, bool(item.is_done))
        self._items_table.blockSignals(False)
        self._update_progress_label()

    def _apply_done_style(self, row: int, done: bool) -> None:
        background = QColor(DONE_ROW_BACKGROUND) if done else QColor(0, 0, 0, 0)
        for column in range(self._items_table.columnCount()):
            cell = self._items_table.item(row, column)
            if cell is not None:
                cell.setBackground(background)

    def _update_progress_label(self) -> None:
        total = len(self._order.items)
        done = sum(1 for item in self._order.items if item.is_done)
        self._progress_label.setText(f"Đã làm xong {done}/{total} dòng hàng")

    def _handle_item_changed(self, cell: QTableWidgetItem) -> None:
        if cell.column() != 0:
            return
        row = cell.row()
        item = self._order.items[row]
        done = cell.checkState() == Qt.CheckState.Checked
        if bool(item.is_done) == done:
            return
        try:
            self._controller.mark_item_done(item.id, done)
        except Exception as exc:
            self._items_table.blockSignals(True)
            cell.setCheckState(Qt.CheckState.Checked if item.is_done else Qt.CheckState.Unchecked)
            self._items_table.blockSignals(False)
            MessageBox.error(self, "Không cập nhật được dòng hàng", str(exc))
            return
        item.is_done = done
        self._items_table.blockSignals(True)
        self._apply_done_style(row, done)
        self._items_table.blockSignals(False)
        self._update_progress_label()
        self.order_changed.emit()

    def _toggle_prepared(self, checked: bool) -> None:
        try:
            self._controller.mark_prepared(self._order.id, checked)
            self.order_changed.emit()
        except Exception as exc:
            self._prepared_checkbox.blockSignals(True)
            self._prepared_checkbox.setChecked(not checked)
            self._prepared_checkbox.blockSignals(False)
            MessageBox.error(self, "Không cập nhật được trạng thái", str(exc))

    def _open_sales_draft(self) -> None:
        app_window = self._app_window()
        if hasattr(app_window, "open_order_sales_draft"):
            app_window.open_order_sales_draft(self._order.id)
            self.accept()
            return
        MessageBox.warning(self, "Chưa hỗ trợ", "Không mở được tab bán hàng từ đơn đặt.")

    def _open_editor(self) -> None:
        app_window = self._app_window()
        if hasattr(app_window, "open_order_editor"):
            app_window.open_order_editor(self._order.id)
            self.accept()
            return
        MessageBox.warning(self, "Chưa hỗ trợ", "Không mở được tab sửa đơn đặt.")

    def _delete_order(self) -> None:
        confirmed = QMessageBox.question(self, "Xác nhận xóa", "Bạn có chắc muốn xóa đơn đặt hàng này không?")
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self._controller.delete_order(self._order.id)
            self.order_changed.emit()
            self.accept()
        except Exception as exc:
            MessageBox.error(self, "Không xóa được đơn đặt hàng", str(exc))

    def _app_window(self) -> object:
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, "open_order_sales_draft") or hasattr(widget, "open_order_editor"):
                return widget
            widget = widget.parent()
        return self.window()
