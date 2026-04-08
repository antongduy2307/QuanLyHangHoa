from __future__ import annotations

from decimal import Decimal
from typing import Callable

from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from modules.customer.controller import CustomerController
from modules.customer.mappers import to_dto
from modules.customer.models import CustomerBalanceLedger
from modules.customer.ui.debt_payment_dialog import DebtPaymentDialog
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox


class DebtPaymentDetailPopup(QDialog):
    def __init__(
        self,
        ledger: CustomerBalanceLedger,
        parent: QDialog | None = None,
        *,
        controller: CustomerController | None = None,
        on_updated: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._ledger = ledger
        self._controller = controller
        self._on_updated = on_updated
        self.setWindowTitle(f"Trả nợ {ledger.ref_id}")
        self.resize(420, 260)

        customer_name = ledger.customer.customer_name if ledger.customer else "-"
        phone = ledger.customer.phone if ledger.customer and ledger.customer.phone else "-"

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Loại giao dịch: Trả nợ"))
        layout.addWidget(QLabel(f"Tên khách: {customer_name}"))
        layout.addWidget(QLabel(f"Điện thoại: {phone}"))
        layout.addWidget(QLabel(f"Thời gian: {format_datetime(ledger.created_at)}"))
        layout.addWidget(QLabel(f"Số tiền trả nợ: {format_money(abs(ledger.amount_delta))}"))
        layout.addWidget(QLabel(f"Ghi chú: {ledger.note or '-'}"))

        if self._controller is not None and ledger.customer is not None:
            edit_button = QPushButton("Sửa")
            edit_button.clicked.connect(self._edit_payment)
            layout.addWidget(edit_button)

    def _edit_payment(self) -> None:
        if self._controller is None or self._ledger.customer is None:
            return
        try:
            latest_ledger = self._controller.get_debt_payment_detail(self._ledger.id)
            dialog = DebtPaymentDialog(
                to_dto(latest_ledger.customer),
                self,
                edit_mode=True,
                amount=abs(latest_ledger.amount_delta),
                note=latest_ledger.note,
            )
            if dialog.exec():
                payload = dialog.payload()
                updated = self._controller.update_debt_payment(latest_ledger.id, Decimal(payload["amount"]), note=payload["note"])
                if self._on_updated is not None:
                    self._on_updated()
                MessageBox.info(self, "Thành công", "Đã cập nhật giao dịch trả nợ.")
                self.accept()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được giao dịch trả nợ", str(exc))
