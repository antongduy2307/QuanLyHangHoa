from __future__ import annotations

from decimal import Decimal, InvalidOperation

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
        self._is_reformatting = False
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
        previous = self._value
        normalized = self._clamp(int(value))
        self._value = normalized
        formatted = self._format_number(normalized)
        if self.text() != formatted:
            self._set_formatted_text(formatted)
        if normalized != previous:
            self.valueChanged.emit(self._value)

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
        if self._is_reformatting:
            return
        parsed = self._parse_text(text)
        if parsed is None:
            if text.strip() == "":
                normalized = 0 if self._minimum <= 0 <= self._maximum else self._minimum
                if normalized != self._value:
                    self._value = normalized
                    self.valueChanged.emit(self._value)
            return

        normalized = self._clamp(parsed)
        if normalized != self._value:
            self._value = normalized
            self.valueChanged.emit(self._value)

        formatted = self._format_number(parsed)
        if formatted != text:
            self._reformat_preserving_cursor(text, formatted)

    def _normalize_text(self) -> None:
        parsed = self._parse_text(self.text())
        if parsed is None:
            parsed = 0 if self._minimum <= 0 <= self._maximum else self._minimum
        normalized = self._clamp(parsed)
        previous = self._value
        self._value = normalized
        formatted = self._format_number(normalized)
        if self.text() != formatted:
            self._set_formatted_text(formatted)
        if normalized != previous:
            self.valueChanged.emit(self._value)

    def _update_validator(self) -> None:
        allow_negative = self._minimum < 0
        pattern = r"-?[\d,]*" if allow_negative else r"[\d,]*"
        self.setValidator(QRegularExpressionValidator(QRegularExpression(pattern), self))

    def _clamp(self, value: int) -> int:
        if value < self._minimum:
            return self._minimum
        if value > self._maximum:
            return self._maximum
        return value

    def _reformat_preserving_cursor(self, original_text: str, formatted_text: str) -> None:
        cursor = self.cursorPosition()
        digits_before_cursor = sum(ch.isdigit() for ch in original_text[:cursor])
        has_minus_before_cursor = original_text.startswith("-") and cursor > 0
        self._set_formatted_text(formatted_text)
        self.setCursorPosition(self._cursor_position_from_digit_index(formatted_text, digits_before_cursor, has_minus_before_cursor))

    def _set_formatted_text(self, text: str) -> None:
        self._is_reformatting = True
        try:
            self.setText(text)
        finally:
            self._is_reformatting = False

    def _cursor_position_from_digit_index(self, text: str, digits_before_cursor: int, has_minus_before_cursor: bool) -> int:
        if digits_before_cursor <= 0:
            if has_minus_before_cursor and text.startswith("-"):
                return 1
            return 0

        digits_seen = 0
        for index, char in enumerate(text):
            if char.isdigit():
                digits_seen += 1
                if digits_seen == digits_before_cursor:
                    return index + 1
        return len(text)

    @staticmethod
    def _format_number(value: int) -> str:
        return f"{value:,}"

    @staticmethod
    def _parse_text(text: str) -> int | None:
        stripped = text.strip().replace(",", "")
        if stripped in {"", "-"}:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None


class SelectAllDecimalInput(QLineEdit):
    valueChanged = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._minimum = Decimal("0")
        self._maximum = Decimal("2147483647")
        self._value = Decimal("0")
        self._is_reformatting = False
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.textChanged.connect(self._handle_text_changed)
        self.editingFinished.connect(self._normalize_text)
        self._update_validator()
        self.setText("0")

    def setRange(self, minimum: Decimal | int | str, maximum: Decimal | int | str) -> None:
        minimum_decimal = self._to_decimal(minimum)
        maximum_decimal = self._to_decimal(maximum)
        if minimum_decimal > maximum_decimal:
            raise ValueError("minimum must be <= maximum")
        self._minimum = minimum_decimal
        self._maximum = maximum_decimal
        self._update_validator()
        self.setValue(self._value)

    def setValue(self, value: Decimal | int | str) -> None:
        previous = self._value
        normalized = self._clamp(self._to_decimal(value))
        self._value = normalized
        formatted = self._format_number(normalized)
        if self.text() != formatted:
            self._set_formatted_text(formatted)
        if normalized != previous:
            self.valueChanged.emit(self._value)

    def value(self) -> Decimal:
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
        if self._is_reformatting:
            return
        parsed = self._parse_text(text)
        if parsed is None:
            if text.strip() == "":
                normalized = Decimal("0") if self._minimum <= Decimal("0") <= self._maximum else self._minimum
                if normalized != self._value:
                    self._value = normalized
                    self.valueChanged.emit(self._value)
            return

        normalized = self._clamp(parsed)
        if normalized != self._value:
            self._value = normalized
            self.valueChanged.emit(self._value)

    def _normalize_text(self) -> None:
        parsed = self._parse_text(self.text())
        if parsed is None:
            parsed = Decimal("0") if self._minimum <= Decimal("0") <= self._maximum else self._minimum
        normalized = self._clamp(parsed)
        self._value = normalized
        formatted = self._format_number(normalized)
        if self.text() != formatted:
            self._set_formatted_text(formatted)

    def _update_validator(self) -> None:
        allow_negative = self._minimum < 0
        pattern = r"-?[\d,]*\.?[\d]*" if allow_negative else r"[\d,]*\.?[\d]*"
        self.setValidator(QRegularExpressionValidator(QRegularExpression(pattern), self))

    def _clamp(self, value: Decimal) -> Decimal:
        if value < self._minimum:
            return self._minimum
        if value > self._maximum:
            return self._maximum
        return value

    def _set_formatted_text(self, text: str) -> None:
        self._is_reformatting = True
        try:
            self.setText(text)
        finally:
            self._is_reformatting = False

    @staticmethod
    def _format_number(value: Decimal) -> str:
        normalized = value.quantize(Decimal("0.01"))
        text = f"{normalized:,.2f}".rstrip("0").rstrip(".")
        return text or "0"

    @staticmethod
    def _parse_text(text: str) -> Decimal | None:
        stripped = text.strip().replace(",", "")
        if stripped in {"", "-", ".", "-."}:
            return None
        try:
            return Decimal(stripped)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _to_decimal(value: Decimal | int | str) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))


class SelectAllQuantityInput(SelectAllDecimalInput):
    @staticmethod
    def _format_number(value: Decimal) -> str:
        normalized = value.quantize(Decimal("0.001"))
        text = f"{normalized:,.3f}".rstrip("0").rstrip(".")
        return text or "0"
