from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout


class SummaryCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("pageCard")
        self._value_label = QLabel("0")
        self._value_label.setStyleSheet("font-size: 28px; font-weight: 600;")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        layout.addWidget(self._value_label)

    def set_value(self, value: int) -> None:
        self._value_label.setText(str(value))
