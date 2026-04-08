from __future__ import annotations

from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from core.db import SessionFactory
from modules.customer.controller import CustomerController
from modules.customer.ui.debt_payment_list_view import DebtPaymentListView
from modules.returns.controller import ReturnController
from modules.returns.ui.return_list_view import ReturnListView
from modules.sales.controller import SalesController
from modules.sales.ui.invoice_list_view import InvoiceListView
from modules.sales.ui.transaction_history_view import TransactionHistoryView


class HistoryPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        sales_controller = SalesController(SessionFactory)
        return_controller = ReturnController(SessionFactory)
        customer_controller = CustomerController(SessionFactory)

        tabs = QTabWidget()
        tabs.addTab(TransactionHistoryView(sales_controller), "Lịch sử giao dịch")
        tabs.addTab(InvoiceListView(sales_controller), "Hóa đơn")
        tabs.addTab(ReturnListView(return_controller), "Lịch sử trả hàng")
        tabs.addTab(DebtPaymentListView(customer_controller), "Trả nợ")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
