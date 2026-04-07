from __future__ import annotations

from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from modules.customer.dto import CustomerDTO
from shared.formatting.money import format_money
from shared.widgets.table_helpers import configure_table_widget


class CustomerTable(QTableWidget):
    def __init__(self) -> None:
        super().__init__(0, 4)
        self.setHorizontalHeaderLabels(["Ten", "Dien thoai", "Cong no", "Tong mua"])
        configure_table_widget(self)

    def set_customers(self, customers: list[CustomerDTO]) -> None:
        self.setRowCount(len(customers))
        for row, customer in enumerate(customers):
            self.setItem(row, 0, QTableWidgetItem(customer.customer_name))
            self.setItem(row, 1, QTableWidgetItem(customer.phone or "-"))
            self.setItem(row, 2, QTableWidgetItem(format_money(customer.current_balance)))
            self.setItem(row, 3, QTableWidgetItem(format_money(customer.total_sales)))
