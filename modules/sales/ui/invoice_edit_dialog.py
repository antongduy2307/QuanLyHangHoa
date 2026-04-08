from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QDialog, QFormLayout, QLabel, QPushButton, QVBoxLayout

from core.exceptions import ValidationError
from modules.sales.controller import SalesController
from modules.sales.models import Invoice
from modules.sales.ui.invoice_items_table import InvoiceItemsTable
from modules.sales.ui.product_search_widget import ProductSearchWidget
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox


class InvoiceEditDialog(QDialog):
    def __init__(self, controller: SalesController, invoice: Invoice, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sửa hóa đơn {invoice.invoice_code}")
        self.resize(820, 560)
        self._controller = controller
        self._invoice = invoice
        self._product_search = ProductSearchWidget(controller.list_sellable_products(), self)
        self._items_table = InvoiceItemsTable()
        self._note_label = QLabel(invoice.note or "-")
        self._total_label = QLabel(format_money(invoice.total_amount))
        self._total_label.setStyleSheet("font-size: 18px; font-weight: 600;")

        self._original_remove = self._items_table.remove_row_at
        self._items_table.remove_row_at = self._remove_row_and_refresh  # type: ignore[method-assign]
        self._product_search.item_added.connect(self._handle_item_added)

        for item in invoice.items:
            self._items_table.add_or_merge_item(
                {
                    "product_id": item.product_id,
                    "product_code_base": item.product_code_snapshot,
                    "product_name": item.product_name_snapshot,
                    "unit_type": item.unit_type,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                }
            )
        self._refresh_total()

        summary = QFormLayout()
        summary.addRow("Mã hóa đơn", QLabel(invoice.invoice_code))
        summary.addRow("Thời điểm", QLabel(format_datetime(invoice.invoice_datetime)))
        summary.addRow("Khách", QLabel(invoice.customer_snapshot_name))
        summary.addRow("Khách trả", QLabel(format_money(invoice.paid_amount or 0)))
        summary.addRow("Thanh toán", QLabel(invoice.payment_method.value if invoice.payment_method else '-'))
        summary.addRow("Ghi chú", self._note_label)
        summary.addRow("Tổng tiền mới", self._total_label)

        save_button = QPushButton("Lưu thay đổi")
        save_button.clicked.connect(self._save)

        layout = QVBoxLayout(self)
        layout.addLayout(summary)
        layout.addWidget(self._product_search)
        layout.addWidget(self._items_table)
        layout.addWidget(save_button)

    def _handle_item_added(self, item: object) -> None:
        self._items_table.add_or_merge_item(dict(item))
        self._refresh_total()

    def _remove_row_and_refresh(self, row_index: int) -> None:
        self._original_remove(row_index)
        self._refresh_total()

    def _refresh_total(self) -> None:
        self._total_label.setText(format_money(self._items_table.total_amount()))

    def _save(self) -> None:
        try:
            items = self._items_table.items_payload()
            if not items:
                raise ValidationError("Phải có ít nhất 1 dòng hàng hóa.")
            self._controller.update_invoice(self._invoice.id, items=items, note=self._invoice.note)
            self.accept()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được hóa đơn", str(exc))
