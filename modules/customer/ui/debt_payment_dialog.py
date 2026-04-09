from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout

from core.config import MAX_MONEY_INPUT
from core.exceptions import ValidationError
from modules.customer.dto import CustomerDTO
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox
from shared.widgets.numeric_inputs import SelectAllSpinBox
from shared.widgets.ui_scale import apply_large_ui


class DebtPaymentDialog(QDialog):
    def __init__(
        self,
        customer: CustomerDTO,
        parent: QDialog | None = None,
        *,
        edit_mode: bool = False,
        amount: Decimal = Decimal("0"),
        note: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._customer = customer
        self._edit_mode = edit_mode
        self.setWindowTitle("Sửa giao dịch trả nợ" if edit_mode else "Thanh toán nợ")
        self.resize(360, 220)

        self.amount_input = SelectAllSpinBox()
        self.amount_input.setRange(0, MAX_MONEY_INPUT)
        self.amount_input.setValue(int(amount))
        self.note_input = QLineEdit(note or "")

        form_layout = QFormLayout()
        form_layout.addRow("Tên khách", QLabel(customer.customer_name))
        form_layout.addRow("Điện thoại", QLabel(customer.phone or "-"))
        form_layout.addRow("Công nợ hiện tại", QLabel(format_money(customer.current_balance)))
        form_layout.addRow("Số tiền trả", self.amount_input)
        form_layout.addRow("Ghi chú", self.note_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form_layout)
        layout.addWidget(buttons)
        apply_large_ui(self)

    def payload(self) -> dict[str, object]:
        return {
            "amount": Decimal(self.amount_input.value()),
            "note": self.note_input.text() or None,
        }

    def _handle_accept(self) -> None:
        try:
            amount = Decimal(self.amount_input.value())
            if amount <= Decimal("0"):
                raise ValidationError("Số tiền trả phải > 0.")
        except Exception as exc:
            MessageBox.error(self, "Lỗi dữ liệu", str(exc))
            return
        self.accept()
