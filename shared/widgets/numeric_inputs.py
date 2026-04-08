from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFocusEvent, QMouseEvent
from PyQt6.QtWidgets import QSpinBox


class SelectAllSpinBox(QSpinBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        line_edit = self.lineEdit()
        if line_edit is not None:
            QTimer.singleShot(0, line_edit.selectAll)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        should_select_all = not self.hasFocus()
        super().mousePressEvent(event)
        if should_select_all:
            line_edit = self.lineEdit()
            if line_edit is not None:
                QTimer.singleShot(0, line_edit.selectAll)
