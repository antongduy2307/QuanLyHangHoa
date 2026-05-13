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
from shared.widgets.table_selection_mode import TableSelectionModeController


class ProductListView(QWidget):
    def __init__(self, controller: InventoryController) -> None:
        super().__init__()
        self._controller = controller
        self._products: list[InventoryProductDTO] = []

        self._search_input = AutocompleteLineEdit()
        self._search_input.setPlaceholderText("Tìm theo tên hàng...")
        self._search_input.textChanged.connect(self._handle_filter_changed)
        self._search_input.suggestion_selected.connect(self._handle_search_suggestion_selected)

        self._show_inactive_checkbox = QCheckBox("Hiện cả hàng ngừng sử dụng")
        self._show_inactive_checkbox.toggled.connect(self._handle_include_inactive_changed)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Mã hàng", "Tên hàng", "Đơn vị bán", "Tồn hiện tại", "Trạng thái"])
        configure_table_widget(self._table, "inventory.product_list")
        self._table.itemDoubleClicked.connect(lambda *_args: self._handle_table_double_clicked())
        self._selection_mode = TableSelectionModeController(
            self._table,
            id_source_column=0,
            on_selection_changed=self._handle_delete_selection_changed,
        )

        self._create_button = QPushButton("Tạo mới")
        self._create_button.clicked.connect(self._open_create_product)
        self._edit_button = QPushButton("Sửa")
        self._edit_button.clicked.connect(self._open_edit_product)
        self._delete_button = QPushButton("Xóa")
        self._delete_button.clicked.connect(self._enter_delete_selection_mode)
        self._delete_selected_button = QPushButton("Xóa đã chọn")
        self._cancel_delete_button = QPushButton("Hủy")
        self._selected_count_label = QLabel("Đã chọn: 0")
        self._delete_selected_button.clicked.connect(self._delete_selected_products)
        self._cancel_delete_button.clicked.connect(self._exit_delete_selection_mode)
        self._delete_selected_button.hide()
        self._cancel_delete_button.hide()
        self._selected_count_label.hide()
        self._receipt_button = QPushButton("Nhập kho")
        self._receipt_button.clicked.connect(self._open_receipt_dialog)
        self._adjustment_button = QPushButton("Điều chỉnh kho")
        self._adjustment_button.clicked.connect(self._open_adjustment_dialog)
        self._refresh_button = QPushButton("Tải lại")
        self._refresh_button.clicked.connect(self.reload)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self._search_input, 1)
        top_bar.addWidget(self._show_inactive_checkbox)
        top_bar.addWidget(self._create_button)
        top_bar.addWidget(self._edit_button)
        top_bar.addWidget(self._delete_button)
        top_bar.addWidget(self._delete_selected_button)
        top_bar.addWidget(self._cancel_delete_button)
        top_bar.addWidget(self._selected_count_label)
        top_bar.addWidget(self._receipt_button)
        top_bar.addWidget(self._adjustment_button)
        top_bar.addWidget(self._refresh_button)

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
        if self._selection_mode.is_active:
            self._exit_delete_selection_mode()
        try:
            self._products = list(self._controller.list_products(include_inactive=self._show_inactive_checkbox.isChecked()))
            self._apply_filter()
        except Exception as exc:
            MessageBox.error(self, "Lỗi tải dữ liệu", str(exc))

    def _handle_filter_changed(self, *_args: object) -> None:
        if self._selection_mode.is_active:
            self._exit_delete_selection_mode()
        self._apply_filter()

    def _handle_include_inactive_changed(self, *_args: object) -> None:
        if self._selection_mode.is_active:
            self._exit_delete_selection_mode()
        self.reload()

    def _apply_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        if not query:
            filtered = self._products
        else:
            filtered = [p for p in self._products if query in p.product_name.lower()]
        self._render_rows(filtered)
        self._update_search_suggestions(query, filtered)

    def _update_search_suggestions(self, query: str, products: list[InventoryProductDTO]) -> None:
        if not query:
            self._search_input.hide_suggestions()
            return
        suggestions = [(product.product_name, product.id) for product in products[:20]]
        self._search_input.set_suggestions(suggestions)

    def _handle_search_suggestion_selected(self, product_id: object) -> None:
        if product_id is None:
            return
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == int(product_id):
                self._table.setCurrentCell(row_index, 1 if self._selection_mode.is_active else 0)
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
        item = self._table.item(row, 1 if self._selection_mode.is_active else 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _handle_table_double_clicked(self) -> None:
        if self._selection_mode.is_active:
            return
        self._open_edit_product()

    def _enter_delete_selection_mode(self) -> None:
        if self._table.rowCount() == 0:
            return
        self._table.clearSelection()
        self._selection_mode.enter()
        self._create_button.hide()
        self._edit_button.hide()
        self._delete_button.hide()
        self._receipt_button.hide()
        self._adjustment_button.hide()
        self._delete_selected_button.show()
        self._cancel_delete_button.show()
        self._selected_count_label.show()
        self._handle_delete_selection_changed([])

    def _exit_delete_selection_mode(self) -> None:
        self._selection_mode.exit(clear=True)
        self._create_button.show()
        self._edit_button.show()
        self._delete_button.show()
        self._receipt_button.show()
        self._adjustment_button.show()
        self._delete_selected_button.hide()
        self._cancel_delete_button.hide()
        self._selected_count_label.hide()

    def _handle_delete_selection_changed(self, selected_ids: list[int]) -> None:
        self._selected_count_label.setText(f"Đã chọn: {len(selected_ids)}")
        self._delete_selected_button.setEnabled(bool(selected_ids))

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

    def _delete_selected_products(self) -> None:
        selected_ids = self._selection_mode.selected_ids()
        if not selected_ids:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn ít nhất một hàng hóa để xóa.")
            return

        products_by_id = {product.id: product for product in self._products}
        hard_delete_ids: list[int] = []
        deactivate_ids: list[int] = []
        mode_failures: list[str] = []
        for product_id in selected_ids:
            product_name = products_by_id.get(product_id).product_name if product_id in products_by_id else str(product_id)
            try:
                delete_mode = self._controller.get_delete_mode(product_id)
            except Exception as exc:
                mode_failures.append(f"{product_name}: {exc}")
                continue
            if delete_mode == "hard_delete":
                hard_delete_ids.append(product_id)
            else:
                deactivate_ids.append(product_id)

        selected_names = [products_by_id[product_id].product_name for product_id in selected_ids if product_id in products_by_id]
        preview_names = "\n".join(f"- {name}" for name in selected_names[:5])
        remaining_count = len(selected_names) - 5
        if remaining_count > 0:
            preview_names = f"{preview_names}\n- ... và {remaining_count} hàng hóa khác"
        message_parts = [
            f"Bạn đã chọn {len(selected_ids)} hàng hóa.",
            f"{len(hard_delete_ids)} hàng hóa chưa có lịch sử sẽ bị xóa vĩnh viễn.",
            f"{len(deactivate_ids)} hàng hóa đã có lịch sử sẽ được chuyển sang ngừng sử dụng.",
        ]
        if mode_failures:
            message_parts.append(f"Có {len(mode_failures)} hàng hóa chưa xác định được thao tác xóa.")
            message_parts.extend(mode_failures[:3])
        if preview_names:
            message_parts.append("Một số hàng hóa đã chọn:")
            message_parts.append(preview_names)
        confirmed = QMessageBox.question(
            self,
            "Xác nhận xóa",
            "\n\n".join(message_parts),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        hard_deleted = 0
        deactivated = 0
        failures = list(mode_failures)
        for product_id in hard_delete_ids + deactivate_ids:
            product_name = products_by_id.get(product_id).product_name if product_id in products_by_id else str(product_id)
            try:
                result = self._controller.delete_product(product_id)
                if getattr(result, "action", None) == "hard_deleted":
                    hard_deleted += 1
                else:
                    deactivated += 1
            except Exception as exc:
                failures.append(f"{product_name}: {exc}")

        self._exit_delete_selection_mode()
        self.reload()

        summary_parts: list[str] = []
        if hard_deleted:
            summary_parts.append(f"Đã xóa vĩnh viễn {hard_deleted} hàng hóa.")
        if deactivated:
            summary_parts.append(f"Đã chuyển {deactivated} hàng hóa sang ngừng sử dụng.")
        if failures:
            summary_parts.append(f"Có {len(failures)} hàng hóa không xử lý được.")
            summary_parts.extend(failures[:3])
        summary = "\n".join(summary_parts) if summary_parts else "Không có hàng hóa nào được xử lý."
        if failures:
            MessageBox.warning(self, "Kết quả xóa hàng hóa", summary)
        else:
            MessageBox.info(self, "Kết quả xóa hàng hóa", summary)

    def _delete_product(self) -> None:
        self._enter_delete_selection_mode()

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
