from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLineEdit


class ReturnsForm(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Form placeholder")
        layout = QFormLayout(self)
        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("Ly do tra hang")
        layout.addRow("Ly do", self.reason_input)
