from __future__ import annotations

import unittest

from PyQt6.QtWidgets import QApplication

from decimal import Decimal

from shared.widgets.numeric_inputs import SelectAllDecimalInput, SelectAllQuantityInput, SelectAllSpinBox


class SelectAllSpinBoxFormattingTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_set_value_formats_with_thousand_separators(self) -> None:
        widget = SelectAllSpinBox()
        try:
            widget.setValue(1_000_000)
            self.assertEqual(widget.text(), "1,000,000")
            self.assertEqual(widget.value(), 1_000_000)
        finally:
            widget.deleteLater()

    def test_typing_digits_reformats_and_keeps_clean_numeric_value(self) -> None:
        widget = SelectAllSpinBox()
        try:
            widget.setText("1000")
            self.assertEqual(widget.text(), "1,000")
            self.assertEqual(widget.value(), 1000)

            widget.setText("1000000")
            self.assertEqual(widget.text(), "1,000,000")
            self.assertEqual(widget.value(), 1_000_000)
        finally:
            widget.deleteLater()

    def test_negative_ranges_keep_minus_and_format(self) -> None:
        widget = SelectAllSpinBox()
        try:
            widget.setRange(-1_000_000, 1_000_000)
            widget.setText("-1000")
            self.assertEqual(widget.text(), "-1,000")
            self.assertEqual(widget.value(), -1000)
        finally:
            widget.deleteLater()

    def test_comma_input_parses_to_clean_integer(self) -> None:
        widget = SelectAllSpinBox()
        try:
            widget.setText("1,200,000")
            self.assertEqual(widget.value(), 1_200_000)
            widget.editingFinished.emit()
            self.assertEqual(widget.text(), "1,200,000")
        finally:
            widget.deleteLater()

class SelectAllDecimalInputFormattingTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_set_value_formats_decimal_with_optional_fraction(self) -> None:
        widget = SelectAllDecimalInput()
        try:
            widget.setValue(Decimal("43.5"))
            self.assertEqual(widget.text(), "43.5")
            self.assertEqual(widget.value(), Decimal("43.5"))
        finally:
            widget.deleteLater()

    def test_comma_input_uses_thousands_separator_and_dot_as_decimal_separator(self) -> None:
        widget = SelectAllDecimalInput()
        try:
            widget.setText("1,234.5")
            self.assertEqual(widget.value(), Decimal("1234.5"))
            widget.editingFinished.emit()
            self.assertEqual(widget.text(), "1,234.5")
        finally:
            widget.deleteLater()

    def test_clear_sets_value_to_zero_and_set_value_emits_change(self) -> None:
        widget = SelectAllDecimalInput()
        emitted_values: list[Decimal] = []
        widget.valueChanged.connect(emitted_values.append)
        try:
            widget.setValue(Decimal("7.5"))
            widget.clear()

            self.assertEqual(widget.value(), Decimal("0"))
            self.assertEqual(emitted_values, [Decimal("7.5"), Decimal("0")])
        finally:
            widget.deleteLater()


class SelectAllQuantityInputFormattingTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_quantity_keeps_decimal_fraction_without_integer_rounding(self) -> None:
        widget = SelectAllQuantityInput()
        try:
            widget.setRange(Decimal("0"), Decimal("999999"))
            widget.setValue(Decimal("4.8"))
            self.assertEqual(widget.text(), "4.8")
            self.assertEqual(widget.value(), Decimal("4.8"))

            widget.setText("12.25")
            widget.editingFinished.emit()
            self.assertEqual(widget.text(), "12.25")
            self.assertEqual(widget.value(), Decimal("12.25"))
        finally:
            widget.deleteLater()


if __name__ == "__main__":
    unittest.main()
