from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.inventory.controller import InventoryController
from modules.inventory.dto import InventoryProductDTO
from modules.inventory.ui.inventory_adjustment_dialog import InventoryAdjustmentDialog
from modules.inventory.ui.inventory_receipt_dialog import InventoryReceiptDialog
from modules.inventory.ui.product_dialog import ProductDialog
from shared.widgets.autocomplete_line_edit import AutocompleteLineEdit
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class ProductListView(QWidget):
    def __init__(self, controller: InventoryController) -> None:
        super().__init__()
        self._controller = controller
        self._products: list[InventoryProductDTO] = []

        self._search_input = AutocompleteLineEdit()
        self._search_input.setPlaceholderText("Tìm theo mã hoặc tên hàng...")
        self._search_input.textChanged.connect(self._apply_filter)
        self._search_input.suggestion_selected.connect(self._handle_search_suggestion_selected)

        self._show_inactive_checkbox = QCheckBox("Hiện cả hàng ngừng sử dụng")
        self._show_inactive_checkbox.toggled.connect(self.reload)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Mã hàng", "Tên hàng", "Đơn vị bán", "Tồn hiện tại", "Trạng thái"])
        configure_table_widget(self._table, "inventory.product_list")
        self._table.itemDoubleClicked.connect(self._open_edit_product)

        create_button = QPushButton("Tạo mới")
        create_button.clicked.connect(self._open_create_product)
        edit_button = QPushButton("Sửa")
        edit_button.clicked.connect(self._open_edit_product)
        delete_button = QPushButton("Xóa")
        delete_button.clicked.connect(self._delete_product)
        receipt_button = QPushButton("Nhập kho")
        receipt_button.clicked.connect(self._open_receipt_dialog)
        adjustment_button = QPushButton("Điều chỉnh kho")
        adjustment_button.clicked.connect(self._open_adjustment_dialog)
        refresh_button = QPushButton("Tải lại")
        refresh_button.clicked.connect(self.reload)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self._search_input, 1)
        top_bar.addWidget(self._show_inactive_checkbox)
        top_bar.addWidget(create_button)
        top_bar.addWidget(edit_button)
        top_bar.addWidget(delete_button)
        top_bar.addWidget(receipt_button)
        top_bar.addWidget(adjustment_button)
        top_bar.addWidget(refresh_button)

        layout = QVBoxLayout(self)
        title = QLabel("Quản lý hàng hóa")
        subtitle = QLabel("Hàng ngừng sử dụng sẽ bị ẩn mặc định. Khi xóa, hàng chưa phát sinh sẽ bị xóa vĩnh viễn; hàng đã có lịch sử sẽ chuyển sang ngừng sử dụng.")
        subtitle.setProperty("class", "muted")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(top_bar)
        layout.addWidget(self._table)

        self.reload()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.reload()

    def reload(self) -> None:
        try:
            self._products = list(self._controller.list_products(include_inactive=self._show_inactive_checkbox.isChecked()))
            self._apply_filter()
        except Exception as exc:
            MessageBox.error(self, "Lỗi tải dữ liệu", str(exc))

    def _apply_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        if not query:
            filtered = self._products
        else:
            code_matches = [p for p in self._products if query in p.product_code_base.lower()]
            if code_matches:
                filtered = code_matches
            else:
                filtered = [p for p in self._products if query in p.product_name.lower()]
        self._render_rows(filtered)
        self._update_search_suggestions(query, filtered)

    def _update_search_suggestions(self, query: str, products: list[InventoryProductDTO]) -> None:
        if not query:
            self._search_input.hide_suggestions()
            return
        suggestions = [(f"{product.product_code_base} - {product.product_name}", product.id) for product in products[:20]]
        self._search_input.set_suggestions(suggestions)

    def _handle_search_suggestion_selected(self, product_id: object) -> None:
        if product_id is None:
            return
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == int(product_id):
                self._table.setCurrentCell(row_index, 0)
                break

    def _render_rows(self, products: list[InventoryProductDTO]) -> None:
        self._table.setRowCount(len(products))
        for row_index, product in enumerate(products):
            self._table.setItem(row_index, 0, QTableWidgetItem(product.product_code_base))
            name_item = QTableWidgetItem(product.product_name)
            status_item = QTableWidgetItem("Đang dùng" if product.is_active else "Ngừng sử dụng")
            if not product.is_active:
                muted_color = QColor("#6b7280")
                name_item.setForeground(muted_color)
                status_item.setForeground(muted_color)
            self._table.setItem(row_index, 1, name_item)
            self._table.setItem(row_index, 2, QTableWidgetItem(self._controller.get_unit_display(product)))
            self._table.setItem(row_index, 3, QTableWidgetItem(self._controller.get_on_hand_display(product)))
            self._table.setItem(row_index, 4, status_item)
            self._table.item(row_index, 0).setData(Qt.ItemDataRole.UserRole, product.id)

    def _selected_product_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _open_create_product(self, *_args: object) -> None:
        dialog = ProductDialog(self)
        if dialog.exec():
            try:
                payload = dialog.payload()
                self._controller.create_product(**payload)
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Không tạo được hàng hóa", str(exc))

    def _open_edit_product(self, *_args: object) -> None:
        product_id = self._selected_product_id()
        if product_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một hàng hóa để sửa.")
            return
        try:
            detail = self._controller.get_product_for_edit(product_id)
            dialog = ProductDialog(
                self,
                edit_mode=True,
                product_code_base=detail.product_code_base,
                product_name=detail.product_name,
                unit_mode=detail.unit_mode,
                enabled_prices=detail.enabled_prices,
                all_prices=detail.all_prices,
            )
            if dialog.exec():
                payload = dialog.payload()
                self._controller.update_product(
                    product_id,
                    product_name=str(payload["product_name"]),
                    unit_mode=detail.unit_mode,
                    enabled_prices=payload["enabled_prices"],
                )
                self.reload()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được hàng hóa", str(exc))

    def _delete_product(self) -> None:
        product_id = self._selected_product_id()
        if product_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một hàng hóa để xóa.")
            return
        try:
            delete_mode = self._controller.get_delete_mode(product_id)
        except Exception as exc:
            MessageBox.error(self, "Không xác định được thao tác xóa", str(exc))
            return

        if delete_mode == "hard_delete":
            message = "Hàng hóa chưa phát sinh giao dịch. Xóa vĩnh viễn?"
        else:
            message = "Hàng hóa đã phát sinh giao dịch/chứng từ kho. Sẽ chuyển sang ngừng sử dụng thay vì xóa vĩnh viễn. Tiếp tục?"

        confirmed = QMessageBox.question(self, "Xác nhận xóa", message)
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self._controller.delete_product(product_id)
            self.reload()
            if getattr(result, "action", None) == "hard_deleted":
                MessageBox.info(self, "Thành công", "Đã xóa vĩnh viễn hàng hóa chưa phát sinh giao dịch.")
            else:
                MessageBox.info(self, "Thành công", "Hàng hóa đã được chuyển sang ngừng sử dụng và bị ẩn khỏi các nghiệp vụ tạo mới.")
        except Exception as exc:
            MessageBox.error(self, "Không xóa được hàng hóa", str(exc))

    def _open_receipt_dialog(self) -> None:
        dialog = InventoryReceiptDialog(self._controller.list_product_options(), self)
        if dialog.exec():
            try:
                self._controller.create_receipt(dialog.payload())
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Không tạo được phiếu nhập", str(exc))

    def _open_adjustment_dialog(self) -> None:
        dialog = InventoryAdjustmentDialog(self._controller.list_product_options(), self)
        if dialog.exec():
            try:
                self._controller.create_adjustment(dialog.payload())
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Không tạo được phiếu điều chỉnh", str(exc))
