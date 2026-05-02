from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from shared.widgets.ui_scale import boost_font_size


class SummaryCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("pageCard")
        self._value_label = QLabel("0")
        self._value_label.setStyleSheet(f"font-size: {boost_font_size(28)}px; font-weight: 600;")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        layout.addWidget(self._value_label)

    def set_value(self, value: int) -> None:
        self._value_label.setText(str(value))
