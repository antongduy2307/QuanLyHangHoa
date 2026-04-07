from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLineEdit


class ReturnsForm(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Biểu mẫu tạm")
        layout = QFormLayout(self)
        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("Lý do trả hàng")
        layout.addRow("Lý do", self.reason_input)
