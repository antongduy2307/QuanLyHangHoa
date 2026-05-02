from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from core.db import SessionFactory
from modules.customer.controller import CustomerController
from modules.customer.ui.debt_payment_list_view import DebtPaymentListView
from modules.returns.controller import ReturnController
from modules.returns.ui.return_list_view import ReturnListView
from modules.sales.controller import SalesController
from modules.sales.ui.invoice_list_view import InvoiceListView
from modules.sales.ui.transaction_history_view import TransactionHistoryView
from shared.widgets.ui_scale import apply_large_ui


class HistoryPage(QWidget):
    history_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        sales_controller = SalesController(SessionFactory)
        return_controller = ReturnController(SessionFactory)
        customer_controller = CustomerController(SessionFactory)

        self._transaction_history_view = TransactionHistoryView(sales_controller, on_history_changed=self.reload_all_views)
        self._invoice_list_view = InvoiceListView(sales_controller, on_history_changed=self.reload_all_views)
        self._return_list_view = ReturnListView(return_controller, on_history_changed=self.reload_all_views)
        self._debt_payment_list_view = DebtPaymentListView(customer_controller, on_history_changed=self.reload_all_views)

        tabs = QTabWidget()
        tabs.addTab(self._transaction_history_view, "Lịch sử giao dịch")
        tabs.addTab(self._invoice_list_view, "Hóa đơn")
        tabs.addTab(self._return_list_view, "Lịch sử trả hàng")
        tabs.addTab(self._debt_payment_list_view, "Trả nợ")
        self._tabs = tabs

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        apply_large_ui(self)

    def reload_all_views(self) -> None:
        self._transaction_history_view.reload()
        self._invoice_list_view.reload()
        self._return_list_view.reload()
        self._debt_payment_list_view.reload()
        self.history_changed.emit()

    def open_transaction_detail(self, transaction_kind: str, transaction_id: int) -> None:
        self._tabs.setCurrentWidget(self._transaction_history_view)
        self._transaction_history_view.open_transaction_detail(transaction_kind, transaction_id)
