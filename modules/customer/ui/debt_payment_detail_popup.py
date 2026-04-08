from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout

from modules.customer.models import CustomerBalanceLedger
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money


class DebtPaymentDetailPopup(QDialog):
    def __init__(self, ledger: CustomerBalanceLedger, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Trả nợ {ledger.ref_id}")
        self.resize(420, 240)

        customer_name = ledger.customer.customer_name if ledger.customer else "-"
        phone = ledger.customer.phone if ledger.customer and ledger.customer.phone else "-"

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Loại giao dịch: Trả nợ"))
        layout.addWidget(QLabel(f"Tên khách: {customer_name}"))
        layout.addWidget(QLabel(f"Điện thoại: {phone}"))
        layout.addWidget(QLabel(f"Thời gian: {format_datetime(ledger.created_at)}"))
        layout.addWidget(QLabel(f"Số tiền trả nợ: {format_money(abs(ledger.amount_delta))}"))
        layout.addWidget(QLabel(f"Ghi chú: {ledger.note or '-'}"))
