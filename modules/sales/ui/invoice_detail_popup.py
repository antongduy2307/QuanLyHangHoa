from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from modules.sales.models import Invoice
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.table_helpers import configure_table_widget


class InvoiceDetailPopup(QDialog):
    def __init__(self, invoice: Invoice, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Hóa đơn {invoice.invoice_code}")
        self.resize(720, 420)

        items_table = QTableWidget(0, 6)
        items_table.setHorizontalHeaderLabels(["Mã hàng", "Tên hàng", "Đơn vị", "Số lượng", "Đơn giá", "Thành tiền"])
        configure_table_widget(items_table)
        items_table.setRowCount(len(invoice.items))
        for row_index, item in enumerate(invoice.items):
            items_table.setItem(row_index, 0, QTableWidgetItem(item.product_code_snapshot))
            items_table.setItem(row_index, 1, QTableWidgetItem(item.product_name_snapshot))
            items_table.setItem(row_index, 2, QTableWidgetItem(item.unit_type.value))
            items_table.setItem(row_index, 3, QTableWidgetItem(str(item.quantity)))
            items_table.setItem(row_index, 4, QTableWidgetItem(format_money(item.unit_price)))
            items_table.setItem(row_index, 5, QTableWidgetItem(format_money(item.line_total)))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Mã hóa đơn: {invoice.invoice_code}"))
        layout.addWidget(QLabel(f"Thời điểm: {format_datetime(invoice.invoice_datetime)}"))
        layout.addWidget(QLabel(f"Khách: {invoice.customer_snapshot_name}"))
        layout.addWidget(QLabel(f"Tổng tiền: {format_money(invoice.total_amount)}"))
        layout.addWidget(QLabel(f"Khách trả: {format_money(invoice.paid_amount or 0)}"))
        layout.addWidget(QLabel(f"Thanh toán: {invoice.payment_method.value if invoice.payment_method else '-'}"))
        layout.addWidget(items_table)
