from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLineEdit


class SalesFilterForm(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Bộ lọc tạm")
        layout = QFormLayout(self)
        self.order_input = QLineEdit()
        self.order_input.setPlaceholderText("Tìm theo số phiếu")
        layout.addRow("Số phiếu", self.order_input)
