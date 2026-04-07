from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from modules.customer.controller import CustomerController
from modules.customer.service import CustomerService
from modules.customer.ui.customer_list_view import CustomerListView


class CustomerPage(QWidget):
    def __init__(self, service: CustomerService) -> None:
        super().__init__()
        controller = CustomerController(service._repository._session_factory)

        layout = QVBoxLayout(self)
        layout.addWidget(CustomerListView(controller))
