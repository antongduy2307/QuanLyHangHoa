from __future__ import annotations

from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from modules.sales.dto import InvoiceDTO
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.table_helpers import configure_table_widget


class SalesTable(QTableWidget):
    def __init__(self) -> None:
        super().__init__(0, 4)
        self.setHorizontalHeaderLabels(["Số hóa đơn", "Khách", "Tổng tiền", "Thời điểm"])
        configure_table_widget(self)

    def set_orders(self, invoices: list[InvoiceDTO]) -> None:
        self.setRowCount(len(invoices))
        for row, invoice in enumerate(invoices):
            self.setItem(row, 0, QTableWidgetItem(invoice.invoice_code))
            self.setItem(row, 1, QTableWidgetItem(invoice.customer_snapshot_name))
            self.setItem(row, 2, QTableWidgetItem(format_money(invoice.total_amount)))
            self.setItem(row, 3, QTableWidgetItem(format_datetime(invoice.invoice_datetime)))
