from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLineEdit


class SalesFilterForm(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Bo loc placeholder")
        layout = QFormLayout(self)
        self.order_input = QLineEdit()
        self.order_input.setPlaceholderText("Tim theo so phieu")
        layout.addRow("So phieu", self.order_input)
