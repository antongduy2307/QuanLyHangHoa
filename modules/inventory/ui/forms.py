from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLineEdit


class InventoryFilterForm(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Bộ lọc tạm")
        layout = QFormLayout(self)
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("Tìm theo mã hoặc tên hàng hóa")
        layout.addRow("Từ khóa", self.keyword_input)
