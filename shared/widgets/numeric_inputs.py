from __future__ import annotations

from PyQt6.QtCore import QRegularExpression, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFocusEvent, QMouseEvent, QRegularExpressionValidator
from PyQt6.QtWidgets import QLineEdit


class SelectAllSpinBox(QLineEdit):
    valueChanged = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 2_147_483_647
        self._value = 0
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.textChanged.connect(self._handle_text_changed)
        self.editingFinished.connect(self._normalize_text)
        self._update_validator()
        self.setText("0")

    def setRange(self, minimum: int, maximum: int) -> None:
        if minimum > maximum:
            raise ValueError("minimum must be <= maximum")
        self._minimum = int(minimum)
        self._maximum = int(maximum)
        self._update_validator()
        self.setValue(self._value)

    def setValue(self, value: int) -> None:
        normalized = self._clamp(int(value))
        self._value = normalized
        text = str(normalized)
        if self.text() != text:
            self.setText(text)

    def value(self) -> int:
        return self._value

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        should_select_all = not self.hasFocus()
        super().mousePressEvent(event)
        if should_select_all:
            QTimer.singleShot(0, self.selectAll)

    def _handle_text_changed(self, text: str) -> None:
        parsed = self._parse_text(text)
        if parsed is None:
            return
        normalized = self._clamp(parsed)
        if normalized != self._value:
            self._value = normalized
        self.valueChanged.emit(self._value)

    def _normalize_text(self) -> None:
        parsed = self._parse_text(self.text())
        if parsed is None:
            parsed = 0 if self._minimum <= 0 <= self._maximum else self._minimum
        normalized = self._clamp(parsed)
        self._value = normalized
        normalized_text = str(normalized)
        if self.text() != normalized_text:
            self.setText(normalized_text)

    def _update_validator(self) -> None:
        allow_negative = self._minimum < 0
        pattern = r"-?\d*" if allow_negative else r"\d*"
        self.setValidator(QRegularExpressionValidator(QRegularExpression(pattern), self))

    def _clamp(self, value: int) -> int:
        if value < self._minimum:
            return self._minimum
        if value > self._maximum:
            return self._maximum
        return value

    @staticmethod
    def _parse_text(text: str) -> int | None:
        stripped = text.strip()
        if stripped in {"", "-"}:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
