from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from modules.sales.service import SalesService
from modules.sales.ui.dialogs import SalesDialog
from modules.sales.ui.forms import SalesFilterForm
from modules.sales.ui.widgets import SalesTable


class SalesPage(QWidget):
    def __init__(self, service: SalesService) -> None:
        super().__init__()
        self._service = service
        self._table = SalesTable()
        self._status_label = QLabel()
        self._status_label.setProperty("class", "muted")

        layout = QVBoxLayout(self)
        title = QLabel("Module Ban hang")
        subtitle = QLabel("Domain sales da duoc doi sang Invoice / InvoiceItem, ho tro khach le va snapshot ten khach.")
        subtitle.setWordWrap(True)
        subtitle.setProperty("class", "muted")

        refresh_button = QPushButton("Tai lai du lieu")
        refresh_button.clicked.connect(self.refresh)
        dialog_button = QPushButton("Mo dialog mau")
        dialog_button.clicked.connect(self.open_dialog)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._status_label)
        layout.addWidget(SalesFilterForm())
        layout.addWidget(refresh_button)
        layout.addWidget(dialog_button)
        layout.addWidget(self._table)

        self.refresh()

    def refresh(self) -> None:
        invoices = list(self._service.list_invoices())
        self._table.set_orders(invoices)
        self._status_label.setText(f"San sang. Co {len(invoices)} hoa don trong bo nho local.")

    def open_dialog(self) -> None:
        SalesDialog().exec()
