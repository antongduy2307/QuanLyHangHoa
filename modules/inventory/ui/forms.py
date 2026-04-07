from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLineEdit


class InventoryFilterForm(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Bo loc placeholder")
        layout = QFormLayout(self)
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("Tim theo SKU hoac ten hang hoa")
        layout.addRow("Tu khoa", self.keyword_input)
