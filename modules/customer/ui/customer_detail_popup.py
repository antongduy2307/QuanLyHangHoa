from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QDialog, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from modules.customer.controller import CustomerDetailData
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.table_helpers import configure_table_widget


class CustomerDetailPopup(QDialog):
    def __init__(self, detail: CustomerDetailData, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chi tiết khách hàng")
        self.resize(560, 400)

        customer = detail.customer
        balance_color = "#b91c1c" if customer.current_balance < Decimal("0") else "#14532d"

        invoices_table = QTableWidget(0, 3)
        invoices_table.setHorizontalHeaderLabels(["Mã hóa đơn", "Thời điểm", "Tổng tiền"])
        configure_table_widget(invoices_table)
        invoices_table.setRowCount(len(detail.recent_invoices))
        for row, invoice in enumerate(detail.recent_invoices):
            invoices_table.setItem(row, 0, QTableWidgetItem(invoice.invoice_code))
            invoices_table.setItem(row, 1, QTableWidgetItem(format_datetime(invoice.invoice_datetime)))
            invoices_table.setItem(row, 2, QTableWidgetItem(format_money(invoice.total_amount)))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Tên: {customer.customer_name}"))
        layout.addWidget(QLabel(f"Điện thoại: {customer.phone or '-'}"))
        layout.addWidget(QLabel(f"Địa chỉ: {customer.address or '-'}"))
        layout.addWidget(QLabel(f"<span style='color:{balance_color}; font-size:18px;'>Công nợ hiện tại: {customer.current_balance:,.0f}</span>"))
        layout.addWidget(QLabel(f"Tổng mua: {format_money(customer.total_sales)}"))
        layout.addWidget(QLabel("Hóa đơn gần nhất"))
        layout.addWidget(invoices_table)
