from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from modules.returns.service import ReturnsService
from modules.returns.ui.forms import ReturnsForm
from modules.returns.ui.widgets import ReturnsWidget


class ReturnsPage(QWidget):
    def __init__(self, service: ReturnsService) -> None:
        super().__init__()
        self._service = service

        layout = QVBoxLayout(self)
        title = QLabel("Module Tra hang")
        subtitle = QLabel("Domain tra hang da tach thanh ReturnInvoice / ReturnInvoiceItem va lien ket nguon ve InvoiceItem.")
        subtitle.setWordWrap(True)
        subtitle.setProperty("class", "muted")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(ReturnsForm())
        layout.addWidget(ReturnsWidget())
        layout.addWidget(QLabel(f"So phieu tra hang hien tai: {len(list(self._service.list_return_invoices()))}"))
