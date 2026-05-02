from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from modules.customer.controller import CustomerController
from modules.customer.service import CustomerService
from modules.customer.ui.customer_list_view import CustomerListView
from shared.widgets.ui_scale import apply_large_ui


class CustomerPage(QWidget):
    transaction_changed = pyqtSignal()

    def __init__(self, service: CustomerService) -> None:
        super().__init__()
        controller = CustomerController(service._repository._session_factory)
        self._customer_list_view = CustomerListView(controller)
        self._customer_list_view.transaction_changed.connect(self._emit_transaction_changed)

        layout = QVBoxLayout(self)
        layout.addWidget(self._customer_list_view)
        apply_large_ui(self)

    def _emit_transaction_changed(self) -> None:
        self.transaction_changed.emit()
