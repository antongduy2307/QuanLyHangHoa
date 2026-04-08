from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox, QVBoxLayout

from core.exceptions import ValidationError
from shared.widgets.numeric_inputs import SelectAllSpinBox


class CustomerDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        customer_name: str = "",
        phone: str | None = None,
        address: str | None = None,
        current_balance: Decimal = Decimal("0"),
        edit_mode: bool = False,
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        self._edit_mode = edit_mode
        self.setWindowTitle(title)
        self.resize(420, 240)

        self.name_input = QLineEdit(customer_name)
        self.phone_input = QLineEdit(phone or "")
        self.address_input = QLineEdit(address or "")
        self.balance_input = SelectAllSpinBox()
        self.balance_input.setRange(-999999999, 999999999)
        self.balance_input.setValue(int(current_balance))

        form_layout = QFormLayout()
        form_layout.addRow("Tên khách", self.name_input)
        form_layout.addRow("Điện thoại", self.phone_input)
        form_layout.addRow("Địa chỉ", self.address_input)
        form_layout.addRow("Công nợ hiện tại" if edit_mode else "Công nợ ban đầu", self.balance_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form_layout)
        layout.addWidget(buttons)

    def payload(self) -> dict[str, object]:
        return {
            "customer_name": self.name_input.text(),
            "phone": self.phone_input.text() or None,
            "address": self.address_input.text() or None,
            "current_balance": Decimal(self.balance_input.value()),
            "initial_balance": Decimal(self.balance_input.value()),
        }

    def _handle_accept(self) -> None:
        if not self.name_input.text().strip():
            QMessageBox.critical(self, "Lỗi dữ liệu", "Tên khách hàng không được để trống.")
            return
        warnings: list[str] = []
        if not self.phone_input.text().strip():
            warnings.append("Khách hàng này không có số điện thoại.")
        if not self.address_input.text().strip():
            warnings.append("Khách hàng này không có địa chỉ.")
        if warnings:
            QMessageBox.warning(self, "Cảnh báo", "\n".join(warnings))
        self.accept()
