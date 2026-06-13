from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)

from core.config import MAX_MONEY_INPUT
from shared.widgets.numeric_inputs import SelectAllSpinBox
from shared.widgets.ui_scale import apply_large_ui


class CustomerDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        customer_name: str = "",
        phone: str | None = None,
        address: str | None = None,
        note: str | None = None,
        current_balance: Decimal = Decimal("0"),
        balance_transaction_datetime: datetime | None = None,
        edit_mode: bool = False,
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        self._edit_mode = edit_mode
        self.setWindowTitle(title)
        self.resize(460, 360)

        self.name_input = QLineEdit(customer_name)
        self.phone_input = QLineEdit(phone or "")
        self.address_input = QLineEdit(address or "")
        self.note_input = QTextEdit(note or "")
        self.note_input.setPlaceholderText("Ghi chú nội bộ về khách hàng (không bắt buộc)")
        self.note_input.setMinimumHeight(96)
        self.balance_input = SelectAllSpinBox()
        self.balance_input.setRange(-MAX_MONEY_INPUT, MAX_MONEY_INPUT)
        self.balance_input.setValue(int(current_balance))
        self.balance_transaction_datetime_input: QDateTimeEdit | None = None
        if edit_mode:
            selected_datetime = balance_transaction_datetime or datetime.now()
            self.balance_transaction_datetime_input = QDateTimeEdit(QDateTime(selected_datetime))
            self.balance_transaction_datetime_input.setCalendarPopup(True)
            self.balance_transaction_datetime_input.setDisplayFormat("dd/MM/yyyy HH:mm")

        form_layout = QFormLayout()
        form_layout.addRow("Tên khách", self.name_input)
        form_layout.addRow("Điện thoại", self.phone_input)
        form_layout.addRow("Địa chỉ", self.address_input)
        form_layout.addRow("Ghi chú", self.note_input)
        form_layout.addRow("Công nợ hiện tại" if edit_mode else "Công nợ ban đầu", self.balance_input)
        if self.balance_transaction_datetime_input is not None:
            form_layout.addRow("Ngày giờ giao dịch", self.balance_transaction_datetime_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form_layout)
        layout.addWidget(buttons)
        apply_large_ui(self)

    def payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "customer_name": self.name_input.text(),
            "phone": self.phone_input.text() or None,
            "address": self.address_input.text() or None,
            "note": self.note_input.toPlainText().strip() or None,
            "current_balance": Decimal(self.balance_input.value()),
            "initial_balance": Decimal(self.balance_input.value()),
        }
        if self.balance_transaction_datetime_input is not None:
            payload["balance_transaction_datetime"] = (
                self.balance_transaction_datetime_input.dateTime().toPyDateTime()
            )
        return payload

    def _handle_accept(self) -> None:
        if not self.name_input.text().strip():
            QMessageBox.critical(self, "Lỗi dữ liệu", "Tên khách hàng không được để trống.")
            return
        if (
            self.balance_transaction_datetime_input is not None
            and not self.balance_transaction_datetime_input.dateTime().isValid()
        ):
            QMessageBox.critical(
                self,
                "Lỗi dữ liệu",
                "Vui lòng chọn ngày giờ giao dịch công nợ.",
            )
            return
        warnings: list[str] = []
        if not self.phone_input.text().strip():
            warnings.append("Khách hàng này không có số điện thoại.")
        if not self.address_input.text().strip():
            warnings.append("Khách hàng này không có địa chỉ.")
        if warnings:
            QMessageBox.warning(self, "Cảnh báo", "\n".join(warnings))
        self.accept()
