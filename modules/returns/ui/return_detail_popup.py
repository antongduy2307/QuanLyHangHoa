from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout

from modules.returns.models import ReturnInvoice
from modules.returns.ui.return_edit_dialog import ReturnEditDialog
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.formatting.quantity import format_quantity
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget
from shared.widgets.ui_scale import apply_large_ui


class ReturnDetailPopup(QDialog):
    def __init__(
        self,
        return_invoice: ReturnInvoice,
        parent: QDialog | None = None,
        *,
        controller=None,
        on_updated: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._return_invoice = return_invoice
        self._controller = controller
        self._on_updated = on_updated
        self.setWindowTitle(f"Phiếu trả {return_invoice.return_code}")
        self.resize(1050, 720)
        self.setMinimumSize(920, 620)

        items_table = QTableWidget(0, 6)
        items_table.setHorizontalHeaderLabels(["Mã hàng", "Tên hàng", "Đơn vị", "Số lượng", "Đơn giá", "Thành tiền"])
        configure_table_widget(items_table, "returns.detail.items")
        items_table.setMinimumHeight(320)
        for row_index, item in enumerate(return_invoice.items):
            items_table.insertRow(row_index)
            items_table.setItem(row_index, 0, QTableWidgetItem(item.product_code_snapshot))
            items_table.setItem(row_index, 1, QTableWidgetItem(item.product_name_snapshot))
            items_table.setItem(row_index, 2, QTableWidgetItem(item.unit_type.value))
            items_table.setItem(row_index, 3, QTableWidgetItem(format_quantity(item.quantity)))
            items_table.setItem(row_index, 4, QTableWidgetItem(format_money(item.unit_price)))
            items_table.setItem(row_index, 5, QTableWidgetItem(format_money(item.line_total)))

        source_invoice_code = return_invoice.source_invoice.invoice_code if return_invoice.source_invoice else "Trả nhanh"
        customer_name = return_invoice.customer_snapshot_name
        return_type = "Trả hàng nhanh" if return_invoice.is_quick_return else "Trả theo hóa đơn"
        open_invoice_button = QPushButton("Mở hóa đơn gốc")
        open_invoice_button.clicked.connect(self._open_source_invoice)
        open_invoice_button.setEnabled(return_invoice.source_invoice is not None)
        edit_button = QPushButton("Sửa")
        edit_button.clicked.connect(self._edit_return)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addWidget(QLabel(f"Mã trả hàng: {return_invoice.return_code}"))
        layout.addWidget(QLabel(f"Loại: {return_type}"))
        layout.addWidget(QLabel(f"Thời điểm: {format_datetime(return_invoice.return_datetime)}"))
        layout.addWidget(QLabel(f"Hóa đơn gốc: {source_invoice_code}"))
        layout.addWidget(QLabel(f"Khách: {customer_name}"))
        layout.addWidget(QLabel(f"Tổng tiền trả: {format_money(return_invoice.total_amount)}"))
        layout.addWidget(QLabel(f"Xử lý: {return_invoice.handling_mode.value}"))
        layout.addWidget(QLabel(f"Ghi chú: {return_invoice.note or '-'}"))
        layout.addWidget(open_invoice_button)
        layout.addWidget(edit_button)
        layout.addWidget(items_table)
        apply_large_ui(self)
        self.setStyleSheet(self.styleSheet() + "\nQDialog QLabel { font-size: 16px; }\nQTableWidget { font-size: 15px; }\n")

    def _open_source_invoice(self) -> None:
        if self._return_invoice.source_invoice is None:
            return
        from core.db import SessionFactory
        from modules.sales.controller import SalesController
        from modules.sales.ui.invoice_detail_popup import InvoiceDetailPopup

        controller = SalesController(SessionFactory)
        try:
            invoice = controller.get_invoice_detail(self._return_invoice.source_invoice.id)
            InvoiceDetailPopup(invoice, self).exec()
        except Exception as exc:
            MessageBox.error(self, "Không tải được hóa đơn gốc", str(exc))

    def _edit_return(self) -> None:
        if self._return_invoice.source_invoice_id is None:
            MessageBox.warning(self, "Chưa hỗ trợ", "Chưa hỗ trợ sửa phiếu trả hàng nhanh ở bước này.")
            return
        try:
            if self._controller is None:
                from core.db import SessionFactory
                from modules.returns.controller import ReturnController

                controller = ReturnController(SessionFactory)
            else:
                controller = self._controller
            detail = controller.get_return_edit_detail(self._return_invoice.id)
            dialog = ReturnEditDialog(controller, detail, self)
            if dialog.exec():
                if self._on_updated is not None:
                    self._on_updated()
                MessageBox.info(self, "Thành công", "Đã cập nhật phiếu trả hàng.")
                self.accept()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được phiếu trả hàng", str(exc))
