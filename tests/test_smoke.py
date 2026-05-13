from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget
from sqlalchemy import inspect

import core.db
from shell.app_window import AppWindow
from shell.bootstrap import load_module_specs
from tests.helpers.runtime import TempMainDbRuntime


class SmokeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._runtime = TempMainDbRuntime(prefix="smoke-runtime-")
        self._runtime.__enter__()

    def tearDown(self) -> None:
        QApplication.closeAllWindows()
        QApplication.processEvents()
        self._runtime.__exit__(None, None, None)

    def test_init_db_and_module_registry(self) -> None:
        core.db.init_db()
        specs = load_module_specs()
        self.assertEqual(
            [spec.label for spec in specs],
            ["Hàng hóa", "Bán hàng", "Đặt hàng", "Khách hàng", "Báo cáo", "Chấm công", "Cài đặt"],
        )

    def test_core_tables_exist(self) -> None:
        core.db.init_db()
        table_names = set(inspect(core.db.ENGINE).get_table_names())
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

    def test_main_tab_order_places_history_before_attendance_and_settings(self) -> None:
        modules = (
            SimpleNamespace(key="inventory", label="Hàng hóa", page_factory=QWidget),
            SimpleNamespace(key="sales", label="Bán hàng", page_factory=QWidget),
            SimpleNamespace(key="orders", label="Đặt hàng", page_factory=QWidget),
            SimpleNamespace(key="customer", label="Khách hàng", page_factory=QWidget),
            SimpleNamespace(key="reporting", label="Báo cáo", page_factory=QWidget),
            SimpleNamespace(key="attendance", label="Chấm công", page_factory=QWidget),
            SimpleNamespace(key="settings", label="Cài đặt", page_factory=QWidget),
        )
        window = None
        try:
            settings = self._runtime.settings
            assert settings is not None
            self.assertIn("invoices", set(inspect(core.db.ENGINE).get_table_names()))
            with patch("modules.sales.ui.transaction_history_view.MessageBox.error") as history_error:
                window = AppWindow("Test", modules, settings)
                history_error.assert_not_called()
            tabs = window.findChild(QTabWidget)
            self.assertIsNotNone(tabs)
            assert tabs is not None
            self.assertEqual(
                [tabs.tabText(index) for index in range(tabs.count())],
                ["Hàng hóa", "Bán hàng", "Đặt hàng", "Khách hàng", "Báo cáo", "Lịch sử", "Chấm công", "Cài đặt"],
            )
        finally:
            if window is not None:
                window.close()
                window.deleteLater()


if __name__ == "__main__":
    unittest.main()
