from __future__ import annotations

import unittest

from sqlalchemy import inspect

from core.db import ENGINE, init_db
from shell.bootstrap import load_module_specs


class SmokeTestCase(unittest.TestCase):
    def test_init_db_and_module_registry(self) -> None:
        init_db()
        specs = load_module_specs()
        self.assertEqual([spec.label for spec in specs], ["Hàng hóa", "Bán hàng", "Khách hàng", "Báo cáo", "Cài đặt"])

    def test_core_tables_exist(self) -> None:
        init_db()
        table_names = set(inspect(ENGINE).get_table_names())
        expected = {
            "products",
            "product_prices",
            "inventory_balances",
            "inventory_receipts",
            "inventory_receipt_items",
            "inventory_adjustments",
            "inventory_adjustment_items",
            "customers",
            "customer_balance_ledgers",
            "invoices",
            "invoice_items",
            "return_invoices",
            "return_invoice_items",
        }
        self.assertTrue(expected.issubset(table_names))


if __name__ == "__main__":
    unittest.main()
