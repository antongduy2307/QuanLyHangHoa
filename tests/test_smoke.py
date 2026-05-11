from __future__ import annotations

import unittest
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget
from sqlalchemy import inspect

from core.config import Settings
from core.db import ENGINE, init_db
from shell.app_window import AppWindow
from shell.bootstrap import load_module_specs


class SmokeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_init_db_and_module_registry(self) -> None:
        init_db()
        specs = load_module_specs()
        self.assertEqual(
            [spec.label for spec in specs],
            ["Hàng hóa", "Bán hàng", "Đặt hàng", "Khách hàng", "Báo cáo", "Chấm công", "Cài đặt"],
        )

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

    def test_main_tab_order_places_history_before_attendance_and_settings(self) -> None:
        temp_root = Path(tempfile.mkdtemp(prefix="tab-order-"))
        settings = Settings(
            app_name="QuanLyHangHoaTest",
            app_data_dir=temp_root / "appdata",
            db_path=temp_root / "appdata" / "app.db",
            log_dir=temp_root / "appdata" / "logs",
            export_dir=temp_root / "appdata" / "exports",
            backup_dir=temp_root / "appdata" / "backups",
            temp_dir=temp_root / "appdata" / "temp",
            log_level="INFO",
            update_manifest_url="https://example.com/version.json",
            update_check_timeout_ms=1000,
            update_download_timeout_ms=1000,
            update_download_retry_count=1,
            update_startup_delay_ms=60_000,
        )
        modules = (
            SimpleNamespace(key="inventory", label="Hàng hóa", page_factory=QWidget),
            SimpleNamespace(key="sales", label="Bán hàng", page_factory=QWidget),
            SimpleNamespace(key="orders", label="Đặt hàng", page_factory=QWidget),
            SimpleNamespace(key="customer", label="Khách hàng", page_factory=QWidget),
            SimpleNamespace(key="reporting", label="Báo cáo", page_factory=QWidget),
            SimpleNamespace(key="attendance", label="Chấm công", page_factory=QWidget),
            SimpleNamespace(key="settings", label="Cài đặt", page_factory=QWidget),
        )
        try:
            window = AppWindow("Test", modules, settings)
            tabs = window.findChild(QTabWidget)
            self.assertIsNotNone(tabs)
            assert tabs is not None
            self.assertEqual(
                [tabs.tabText(index) for index in range(tabs.count())],
                ["Hàng hóa", "Bán hàng", "Đặt hàng", "Khách hàng", "Báo cáo", "Lịch sử", "Chấm công", "Cài đặt"],
            )
        finally:
            window.close()
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
