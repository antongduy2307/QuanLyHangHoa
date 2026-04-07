from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QWidget

from modules.reporting.service import ReportingService
from modules.reporting.ui.widgets import SummaryCard


class ReportingPage(QWidget):
    def __init__(self, service: ReportingService) -> None:
        super().__init__()
        self._service = service
        self._inventory_card = SummaryCard("So hang hoa")
        self._customer_card = SummaryCard("So khach hang")
        self._sales_card = SummaryCard("So don ban hang")

        layout = QVBoxLayout(self)
        title = QLabel("Module Bao cao")
        subtitle = QLabel("Bao cao tong hop placeholder. Logic lay so lieu nam trong repository/service, khong o UI.")
        subtitle.setWordWrap(True)
        subtitle.setProperty("class", "muted")
        refresh_button = QPushButton("Lam moi thong ke")
        refresh_button.clicked.connect(self.refresh)

        card_layout = QHBoxLayout()
        card_layout.addWidget(self._inventory_card)
        card_layout.addWidget(self._customer_card)
        card_layout.addWidget(self._sales_card)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(refresh_button)
        layout.addLayout(card_layout)
        layout.addStretch()

        self.refresh()

    def refresh(self) -> None:
        summary = self._service.get_summary()
        self._inventory_card.set_value(summary.inventory_count)
        self._customer_card.set_value(summary.customer_count)
        self._sales_card.set_value(summary.sales_order_count)
