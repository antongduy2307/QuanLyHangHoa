from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFormLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from core.exceptions import ValidationError
from modules.sales.controller import SalesController
from modules.sales.models import Invoice
from modules.sales.ui.invoice_items_table import InvoiceItemsTable
from modules.sales.ui.product_search_widget import ProductSearchWidget
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money_precise
from shared.widgets.message_box import MessageBox
from shared.widgets.ui_scale import apply_large_ui, boost_font_size


class InvoiceEditDialog(QDialog):
    def __init__(self, controller: SalesController, invoice: Invoice, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sửa hóa đơn {invoice.invoice_code}")
        self.resize(1100, 780)
        self.setMinimumSize(900, 640)
        self.setSizeGripEnabled(True)

        self._controller = controller
        self._invoice = invoice
        self._product_search = ProductSearchWidget(controller.list_sellable_products(), self)
        self._product_search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._items_table = InvoiceItemsTable("sales.invoice_items.edit_dialog")
        self._items_table.setMinimumHeight(320)
        self._items_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._note_label = QLabel(invoice.note or "-")
        self._note_label.setWordWrap(True)
        self._note_label.setStyleSheet(f"font-size: {boost_font_size(18)}px;")
        self._total_label = QLabel(format_money_precise(invoice.total_amount))
        self._total_label.setStyleSheet(f"font-size: {boost_font_size(28)}px; font-weight: 700;")
        self._change_label = QLabel(format_money_precise(max((invoice.paid_amount or 0) - invoice.total_amount, 0)))
        self._change_label.setProperty("class", "muted")
        self._change_label.setStyleSheet(f"font-size: {boost_font_size(20)}px;")

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
        summary.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        summary.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        summary.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        summary.addRow("Mã hóa đơn", QLabel(invoice.invoice_code))
        summary.addRow("Thời điểm", QLabel(format_datetime(invoice.invoice_datetime)))
        summary.addRow("Khách", QLabel(invoice.customer_snapshot_name))
        summary.addRow("Khách trả", QLabel(format_money_precise(invoice.paid_amount or 0)))
        summary.addRow("Tiền dư hiện tại", self._change_label)
        summary.addRow("Thanh toán", QLabel(invoice.payment_method.value if invoice.payment_method else "-"))
        summary.addRow("Ghi chú", self._note_label)
        summary.addRow("Tổng tiền mới", self._total_label)

        for index in range(summary.rowCount()):
            label_item = summary.itemAt(index, QFormLayout.ItemRole.LabelRole)
            field_item = summary.itemAt(index, QFormLayout.ItemRole.FieldRole)
            if label_item is not None and label_item.widget() is not None:
                label_item.widget().setStyleSheet(f"font-size: {boost_font_size(18)}px; font-weight: 600;")
            if field_item is not None and field_item.widget() is not None and field_item.widget() not in {self._total_label, self._change_label, self._note_label}:
                field_item.widget().setStyleSheet(f"font-size: {boost_font_size(18)}px;")
                field_item.widget().setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        save_button = QPushButton("Lưu thay đổi")
        save_button.clicked.connect(self._save)
        save_button.setMinimumHeight(56)
        save_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        save_button.setStyleSheet(f"font-size: {boost_font_size(20)}px; font-weight: 700; padding: 12px 18px;")

        content = QWidget(self)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)
        layout.addLayout(summary)
        layout.addWidget(self._product_search)
        layout.addWidget(self._items_table, 1)
        layout.addWidget(save_button)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setWidget(content)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self._scroll)
        apply_large_ui(self)

    def _handle_item_added(self, item: object) -> None:
        self._items_table.add_or_merge_item(dict(item))

    def _refresh_total(self) -> None:
        total = self._items_table.total_amount()
        self._total_label.setText(format_money_precise(total))
        overpayment = max((self._invoice.paid_amount or 0) - total, 0)
        self._change_label.setText(format_money_precise(overpayment))

    def _save(self) -> None:
        try:
            items = self._items_table.items_payload()
            if not items:
                raise ValidationError("Phải có ít nhất 1 dòng hàng hóa.")
            self._controller.update_invoice(self._invoice.id, items=items, note=self._invoice.note)
            self.accept()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được hóa đơn", str(exc))
