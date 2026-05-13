from __future__ import annotations

import unittest
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget
from sqlalchemy import inspect

import core.config
import core.db
from shell.app_window import AppWindow
from shell.bootstrap import load_module_specs


class SmokeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def tearDown(self) -> None:
        QApplication.closeAllWindows()
        QApplication.processEvents()

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
        temp_root = Path(tempfile.mkdtemp(prefix="tab-order-"))
        env = {
            "APP_NAME": "QuanLyHangHoaTest",
            "APP_DB_PATH": str(temp_root / "appdata" / "app.db"),
            "APP_LOG_DIR": str(temp_root / "appdata" / "logs"),
            "APP_EXPORT_DIR": str(temp_root / "appdata" / "exports"),
            "APP_BACKUP_DIR": str(temp_root / "appdata" / "backups"),
            "APP_TEMP_DIR": str(temp_root / "appdata" / "temp"),
            "APP_UPDATE_MANIFEST_URL": "https://example.com/version.json",
            "APP_UPDATE_TIMEOUT_MS": "1000",
            "APP_UPDATE_DOWNLOAD_TIMEOUT_MS": "1000",
            "APP_UPDATE_DOWNLOAD_RETRY_COUNT": "1",
            "APP_UPDATE_STARTUP_DELAY_MS": "60000",
        }
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
            with patch.dict("os.environ", env, clear=False):
                core.config.get_settings.cache_clear()
                core.db.reset_engine_cache()
                core.db.init_db()
                settings = core.config.get_settings()
                self.assertTrue(settings.db_path.exists())
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
            core.db.ENGINE.dispose()
            core.db.reset_engine_cache()
            core.config.get_settings.cache_clear()
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
