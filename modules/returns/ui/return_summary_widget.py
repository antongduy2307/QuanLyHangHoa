from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit, QWidget

from core.enums import ReturnHandlingMode
from shared.formatting.money import format_money


class ReturnSummaryWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.total_label = QLabel(format_money(Decimal("0")))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Hoàn tiền ngay", ReturnHandlingMode.REFUND_NOW)
        self.mode_combo.addItem("Lưu có", ReturnHandlingMode.STORE_CREDIT)
        self.note_input = QLineEdit()

        layout = QFormLayout(self)
        layout.addRow("Tổng trả", self.total_label)
        layout.addRow("Xử lý", self.mode_combo)
        layout.addRow("Ghi chú", self.note_input)

    def set_total(self, amount: Decimal) -> None:
        self.total_label.setText(format_money(amount))

    def set_walk_in_mode(self, is_walk_in: bool) -> None:
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.model().item(1).setEnabled(not is_walk_in)

    def selected_mode(self) -> ReturnHandlingMode:
        return self.mode_combo.currentData()

    def reset(self) -> None:
        self.mode_combo.setCurrentIndex(0)
        self.note_input.clear()
        self.set_total(Decimal("0"))
