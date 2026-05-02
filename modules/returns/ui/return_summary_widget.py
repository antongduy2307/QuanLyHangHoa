from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QFormLayout, QLabel, QWidget

from core.enums import ReturnHandlingMode
from shared.formatting.money import format_money


class ReturnSummaryWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._handling_mode = ReturnHandlingMode.REFUND_NOW

        self.original_total_label = QLabel(format_money(Decimal("0")))
        self.return_total_label = QLabel(format_money(Decimal("0")))
        self.refund_due_label = QLabel(format_money(Decimal("0")))

        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addRow("Tổng giá gốc mua", self.original_total_label)
        layout.addRow("Tổng tiền trả", self.return_total_label)
        layout.addRow("Cần trả khách", self.refund_due_label)

    def set_original_total(self, amount: Decimal) -> None:
        self.original_total_label.setText(format_money(amount))

    def set_return_total(self, amount: Decimal) -> None:
        self.return_total_label.setText(format_money(amount))

    def set_refund_due(self, amount: Decimal) -> None:
        self.refund_due_label.setText(format_money(amount))

    def set_handling_mode(self, mode: ReturnHandlingMode) -> None:
        self._handling_mode = mode

    def selected_mode(self) -> ReturnHandlingMode:
        return self._handling_mode

    def reset(self) -> None:
        self._handling_mode = ReturnHandlingMode.REFUND_NOW
        self.set_original_total(Decimal("0"))
        self.set_return_total(Decimal("0"))
        self.set_refund_due(Decimal("0"))
