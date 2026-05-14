from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget
from sqlalchemy import inspect, text

import core.config
import core.db
from modules.attendance.db import (
    AttendanceSessionLocal,
    get_attendance_db_path,
    get_attendance_engine,
    init_attendance_db,
    reset_attendance_engine_cache,
    _upgrade_attendance_schema,
)
from modules.attendance.models import BagType, DailyRecord, Employee, Period, Team, WorkLog, WorkType
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
        work_quantity = next(column for column in inspector.get_columns("work_logs") if column["name"] == "quantity")
        cut_quantity = next(column for column in inspector.get_columns("cut_logs") if column["name"] == "quantity")
        extra_cut_quantity = next(column for column in inspector.get_columns("extra_cut_work_logs") if column["name"] == "quantity")
        self.assertIn("NUMERIC", str(work_quantity["type"]).upper())
        self.assertIn("NUMERIC", str(cut_quantity["type"]).upper())
        self.assertIn("NUMERIC", str(extra_cut_quantity["type"]).upper())

    def test_upgrade_attendance_schema_rebuilds_integer_work_log_quantity(self) -> None:
        init_attendance_db()
        with AttendanceSessionLocal() as session:
            employee = Employee(name="Legacy Blow", team=Team.BLOW)
            period = Period(start_date=date(2026, 5, 1), end_date=date(2026, 5, 10))
            work_type = session.query(WorkType).filter_by(team=Team.BLOW).first()
            assert work_type is not None
            session.add_all([employee, period])
            session.flush()
            record = DailyRecord(employee_id=employee.id, date=date(2026, 5, 6), period_id=period.id)
            session.add(record)
            session.flush()
            record_id = int(record.id)
            work_type_id = int(work_type.id)
            session.commit()

        engine = get_attendance_engine()
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=OFF"))
            connection.execute(text("DROP TABLE work_logs"))
            connection.execute(
                text(
                    """
                    CREATE TABLE work_logs (
                        id INTEGER NOT NULL,
                        daily_record_id INTEGER NOT NULL,
                        work_type_id INTEGER NOT NULL,
                        quantity INTEGER NOT NULL,
                        unit_price_snapshot INTEGER NOT NULL,
                        amount_snapshot INTEGER NOT NULL,
                        PRIMARY KEY (id),
                        CONSTRAINT uq_work_log_daily_work_type UNIQUE (daily_record_id, work_type_id),
                        CONSTRAINT ck_work_log_quantity_positive CHECK (quantity >= 1),
                        CONSTRAINT ck_work_log_unit_price_non_negative CHECK (unit_price_snapshot >= 0),
                        CONSTRAINT ck_work_log_amount_non_negative CHECK (amount_snapshot >= 0),
                        FOREIGN KEY(daily_record_id) REFERENCES daily_records (id) ON DELETE CASCADE,
                        FOREIGN KEY(work_type_id) REFERENCES work_types (id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO work_logs (
                        id, daily_record_id, work_type_id, quantity,
                        unit_price_snapshot, amount_snapshot
                    )
                    VALUES (1, :record_id, :work_type_id, 5, 30000, 150000)
                    """
                ),
                {"record_id": record_id, "work_type_id": work_type_id},
            )
            connection.execute(text("PRAGMA foreign_keys=ON"))

        _upgrade_attendance_schema(engine)
        _upgrade_attendance_schema(engine)

        inspector = inspect(engine)
        work_quantity = next(column for column in inspector.get_columns("work_logs") if column["name"] == "quantity")
        self.assertIn("NUMERIC", str(work_quantity["type"]).upper())
        with engine.connect() as connection:
            table_sql = connection.execute(
                text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'work_logs'")
            ).scalar_one()
        self.assertIn("quantity >= 0.5", table_sql)
        with AttendanceSessionLocal() as session:
            log = session.query(WorkLog).one()
            self.assertEqual(log.quantity, Decimal("5.000"))
            self.assertEqual(log.amount_snapshot, 150000)

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
