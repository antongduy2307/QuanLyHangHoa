from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from modules.customer.service import CustomerService
from modules.customer.ui.dialogs import CustomerDialog
from modules.customer.ui.forms import CustomerFilterForm
from modules.customer.ui.widgets import CustomerTable


class CustomerPage(QWidget):
    def __init__(self, service: CustomerService) -> None:
        super().__init__()
        self._service = service
        self._table = CustomerTable()
        self._status_label = QLabel()
        self._status_label.setProperty("class", "muted")

        layout = QVBoxLayout(self)
        title = QLabel("Module Khach hang")
        subtitle = QLabel("Module nay san sang cho CRUD khach hang, nhung business rules van duoc giu o service layer.")
        subtitle.setWordWrap(True)
        subtitle.setProperty("class", "muted")

        refresh_button = QPushButton("Tai lai du lieu")
        refresh_button.clicked.connect(self.refresh)
        dialog_button = QPushButton("Mo dialog mau")
        dialog_button.clicked.connect(self.open_dialog)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._status_label)
        layout.addWidget(CustomerFilterForm())
        layout.addWidget(refresh_button)
        layout.addWidget(dialog_button)
        layout.addWidget(self._table)

        self.refresh()

    def refresh(self) -> None:
        customers = list(self._service.list_customers())
        self._table.set_customers(customers)
        self._status_label.setText(f"San sang. Co {len(customers)} khach hang trong co so du lieu local.")

    def open_dialog(self) -> None:
        CustomerDialog().exec()
