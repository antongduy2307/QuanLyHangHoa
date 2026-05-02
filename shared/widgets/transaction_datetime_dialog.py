from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from shared.formatting.dates import format_datetime
from shared.widgets.ui_scale import apply_large_ui


class TransactionDatetimeDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        transaction_type: str,
        transaction_code: str,
        current_datetime: datetime,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(420, 260)

        self._datetime_input = QDateTimeEdit(QDateTime(current_datetime))
        self._datetime_input.setCalendarPopup(True)
        self._datetime_input.setDisplayFormat("dd/MM/yyyy HH:mm")

        form_layout = QFormLayout()
        form_layout.addRow("Loại giao dịch", QLabel(transaction_type))
        form_layout.addRow("Mã giao dịch", QLabel(transaction_code))
        form_layout.addRow("Thời gian hiện tại", QLabel(format_datetime(current_datetime)))
        form_layout.addRow("Thời gian mới", self._datetime_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form_layout)
        layout.addWidget(buttons)

        apply_large_ui(self)

    def selected_datetime(self) -> datetime:
        return self._datetime_input.dateTime().toPyDateTime()
