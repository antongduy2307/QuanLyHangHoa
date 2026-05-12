from __future__ import annotations

from decimal import Decimal
import unittest

from PyQt6.QtWidgets import QApplication

from core.enums import UnitType
from modules.sales.ui.invoice_items_table import InvoiceItemsTable
from shared.widgets.numeric_inputs import SelectAllDecimalInput


class InvoiceItemsTablePrecisionTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_decimal_unit_price_is_preserved_without_rounding_to_integer(self) -> None:
        table = InvoiceItemsTable()
        try:
            table.add_or_merge_item(
                {
                    "product_id": 1,
                    "product_code_base": "P001",
                    "product_name": "Gao Nep",
                    "unit_type": UnitType.BAO,
                    "quantity": Decimal("2"),
                    "unit_price": Decimal("100"),
                }
            )

            unit_price_editor = table.cellWidget(0, 4)
            self.assertIsInstance(unit_price_editor, SelectAllDecimalInput)
            unit_price_editor.setValue(Decimal("43.5"))
            table._handle_unit_price_finished(0, unit_price_editor.value())

            payload = table.items_payload()[0]
            self.assertEqual(payload["unit_price"], Decimal("43.5"))
            self.assertEqual(payload["line_total"], Decimal("87.0"))

            line_total_editor = table.cellWidget(0, 5)
            self.assertIsInstance(line_total_editor, SelectAllDecimalInput)
            self.assertEqual(line_total_editor.text(), "87")
        finally:
            table.deleteLater()


if __name__ == "__main__":
    unittest.main()
