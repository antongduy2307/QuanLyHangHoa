from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QFormLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget, QSizePolicy

from core.exceptions import ValidationError
from modules.sales.controller import SalesController
from modules.sales.models import Invoice
from modules.sales.ui.invoice_items_table import InvoiceItemsTable
from modules.sales.ui.product_search_widget import ProductSearchWidget
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox
from shared.widgets.ui_scale import apply_large_ui


class InvoiceEditDialog(QDialog):
    def __init__(self, controller: SalesController, invoice: Invoice, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sửa hóa đơn {invoice.invoice_code}")
        self.resize(1100, 780)
        self._controller = controller
        self._invoice = invoice
        self._product_search = ProductSearchWidget(controller.list_sellable_products(), self)
        self._items_table = InvoiceItemsTable()
        self._items_table.setMinimumHeight(320)
        self._items_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self._note_label = QLabel(invoice.note or "-")
        self._note_label.setStyleSheet("font-size: 18px;")
        self._total_label = QLabel(format_money(invoice.total_amount))
        self._total_label.setStyleSheet("font-size: 28px; font-weight: 700;")
        self._change_label = QLabel(format_money(max((invoice.paid_amount or 0) - invoice.total_amount, 0)))
        self._change_label.setProperty("class", "muted")
        self._change_label.setStyleSheet("font-size: 20px;")

        self._product_search.item_added.connect(self._handle_item_added)
        self._items_table.totals_changed.connect(self._refresh_total)

        for item in invoice.items:
            self._items_table.add_or_merge_item(
                {
                    "product_id": item.product_id,
                    "product_code_base": item.product_code_snapshot,
                    "product_name": item.product_name_snapshot,
                    "unit_type": item.unit_type,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "line_total": item.line_total,
                }
            )
        self._refresh_total()

        summary = QFormLayout()
        summary.setSpacing(16)
        summary.setLabelAlignment(summary.labelAlignment())
        summary.addRow("Mã hóa đơn", QLabel(invoice.invoice_code))
        summary.addRow("Thời điểm", QLabel(format_datetime(invoice.invoice_datetime)))
        summary.addRow("Khách", QLabel(invoice.customer_snapshot_name))
        summary.addRow("Khách trả", QLabel(format_money(invoice.paid_amount or 0)))
        summary.addRow("Tiền dư hiện tại", self._change_label)
        summary.addRow("Thanh toán", QLabel(invoice.payment_method.value if invoice.payment_method else '-'))
        summary.addRow("Ghi chú", self._note_label)
        summary.addRow("Tổng tiền mới", self._total_label)

        for index in range(summary.rowCount()):
            label_item = summary.itemAt(index, QFormLayout.ItemRole.LabelRole)
            field_item = summary.itemAt(index, QFormLayout.ItemRole.FieldRole)
            if label_item is not None and label_item.widget() is not None:
                label_item.widget().setStyleSheet("font-size: 18px; font-weight: 600;")
            if field_item is not None and field_item.widget() is not None and field_item.widget() not in {self._total_label, self._change_label, self._note_label}:
                field_item.widget().setStyleSheet("font-size: 18px;")

        save_button = QPushButton("Lưu thay đổi")
        save_button.clicked.connect(self._save)
        save_button.setMinimumHeight(56)
        save_button.setStyleSheet("font-size: 20px; font-weight: 700; padding: 12px 18px;")

        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)
        layout.addLayout(summary)
        layout.addWidget(self._product_search)
        layout.addWidget(self._items_table)
        layout.addWidget(save_button)
        layout.addStretch()

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)
        apply_large_ui(self)

    def _handle_item_added(self, item: object) -> None:
        self._items_table.add_or_merge_item(dict(item))

    def _refresh_total(self) -> None:
        total = self._items_table.total_amount()
        self._total_label.setText(format_money(total))
        overpayment = max((self._invoice.paid_amount or 0) - total, 0)
        self._change_label.setText(format_money(overpayment))

    def _save(self) -> None:
        try:
            items = self._items_table.items_payload()
            if not items:
                raise ValidationError("Phải có ít nhất 1 dòng hàng hóa.")
            self._controller.update_invoice(self._invoice.id, items=items, note=self._invoice.note)
            self.accept()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được hóa đơn", str(exc))
