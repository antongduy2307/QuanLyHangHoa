from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget
from sqlalchemy import inspect

import core.config
import core.db
from modules.attendance.db import (
    AttendanceSessionLocal,
    get_attendance_db_path,
    get_attendance_engine,
    init_attendance_db,
    reset_attendance_engine_cache,
)
from modules.attendance.models import BagType, Employee, WorkType
from shell.bootstrap import load_module_specs


class AttendanceBatch1TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temp_root = Path(tempfile.mkdtemp(prefix="attendance-batch1-"))
        self._env_patch = patch.dict(os.environ, {"LOCALAPPDATA": str(self._temp_root)}, clear=False)
        self._env_patch.start()
        core.config.get_settings.cache_clear()
        core.db.reset_engine_cache()
        reset_attendance_engine_cache()

    def tearDown(self) -> None:
        get_attendance_engine().dispose()
        reset_attendance_engine_cache()
        core.config.get_settings.cache_clear()
        self._env_patch.stop()
        core.db.reset_engine_cache()
        shutil.rmtree(self._temp_root, ignore_errors=True)

    def test_init_attendance_db_creates_standalone_schema_and_seed_idempotently(self) -> None:
        init_attendance_db()
        init_attendance_db()

        self.assertEqual(get_attendance_db_path(), self._temp_root / "QuanLyHangHoa" / "attendance.db")
        self.assertTrue(get_attendance_db_path().exists())

        table_names = set(inspect(get_attendance_engine()).get_table_names())
        self.assertTrue(
            {
                "employees",
                "periods",
                "employee_shift_periods",
                "daily_records",
                "work_types",
                "work_logs",
                "bag_types",
                "cut_logs",
            }.issubset(table_names)
        )

        with AttendanceSessionLocal() as session:
            self.assertEqual(session.query(WorkType).count(), 6)
            self.assertEqual(session.query(BagType).count(), 3)
            self.assertEqual(session.query(Employee).count(), 0)

        inspector = inspect(get_attendance_engine())
        cut_quantity = next(column for column in inspector.get_columns("cut_logs") if column["name"] == "quantity")
        extra_cut_quantity = next(column for column in inspector.get_columns("extra_cut_work_logs") if column["name"] == "quantity")
        self.assertIn("NUMERIC", str(cut_quantity["type"]).upper())
        self.assertIn("NUMERIC", str(extra_cut_quantity["type"]).upper())

    def test_sales_database_does_not_receive_attendance_tables(self) -> None:
        core.db.init_db()
        core_tables = set(inspect(core.db.ENGINE).get_table_names())
        self.assertFalse(
            {
                "employees",
                "periods",
                "employee_shift_periods",
                "daily_records",
                "work_types",
                "work_logs",
                "bag_types",
                "cut_logs",
            }
            & core_tables
        )

    def test_attendance_module_registry_and_page_factory(self) -> None:
        specs = load_module_specs()
        attendance_spec = next(spec for spec in specs if spec.key == "attendance")

        self.assertEqual(attendance_spec.label, "Chấm công")
        page = attendance_spec.page_factory()

        self.assertIsInstance(page, QWidget)
        tabs = page.findChild(QTabWidget)
        self.assertIsNotNone(tabs)
        assert tabs is not None
        self.assertEqual([tabs.tabText(index) for index in range(tabs.count())], ["Nhân viên", "Chấm công", "Báo cáo"])


if __name__ == "__main__":
    unittest.main()
