from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QLabel, QGridLayout, QWidget

from modules.reporting.dto import SalesSummaryDTO
from shared.formatting.money import format_money


class SalesSummaryWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._gross_label = QLabel(format_money(Decimal("0")))
        self._return_label = QLabel(format_money(Decimal("0")))
        self._net_label = QLabel(format_money(Decimal("0")))
        self._net_label.setStyleSheet("font-size: 24px; font-weight: 700;")

        layout = QGridLayout(self)
        layout.addWidget(QLabel("Doanh thu gộp"), 0, 0)
        layout.addWidget(self._gross_label, 1, 0)
        layout.addWidget(QLabel("Hàng trả"), 0, 1)
        layout.addWidget(self._return_label, 1, 1)
        layout.addWidget(QLabel("Doanh thu ròng"), 0, 2)
        layout.addWidget(self._net_label, 1, 2)

    def set_summary(self, summary: SalesSummaryDTO) -> None:
        self._gross_label.setText(format_money(summary.gross_sales_amount))
        self._return_label.setText(format_money(summary.return_amount))
        self._net_label.setText(format_money(summary.net_revenue))
