from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QTableWidget

import core.config
from core.exceptions import ValidationError
from modules.attendance.db import AttendanceSessionLocal, get_attendance_engine, init_attendance_db, reset_attendance_engine_cache
from modules.attendance.models import DailyRecord, DailyRecordStatus, Employee, Period, Team
from modules.attendance.service import AttendanceEmployeeService
from modules.attendance.ui.employee_tab import EmployeeManagementTab
from modules.attendance.ui.page import AttendancePage


class AttendanceEmployeeManagementTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temp_root = Path(tempfile.mkdtemp(prefix="attendance-employee-"))
        self._env_patch = patch.dict(os.environ, {"LOCALAPPDATA": str(self._temp_root)}, clear=False)
        self._env_patch.start()
        core.config.get_settings.cache_clear()
        reset_attendance_engine_cache()
        init_attendance_db()
        self.service = AttendanceEmployeeService()

    def tearDown(self) -> None:
        get_attendance_engine().dispose()
        reset_attendance_engine_cache()
        core.config.get_settings.cache_clear()
        self._env_patch.stop()
        shutil.rmtree(self._temp_root, ignore_errors=True)

    def test_create_employee_defaults_active(self) -> None:
        employee = self.service.create_employee(name=" Nguyễn Văn A ", team=Team.BLOW)

        with AttendanceSessionLocal() as session:
            stored = session.get(Employee, employee.id)
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertEqual(stored.name, "Nguyễn Văn A")
            self.assertEqual(stored.team, Team.BLOW)
            self.assertTrue(stored.is_active)

    def test_duplicate_stripped_employee_name_raises_validation_error(self) -> None:
        self.service.create_employee(name="Nguyễn Văn A", team=Team.BLOW)

        with self.assertRaises(ValidationError):
            self.service.create_employee(name="  Nguyễn Văn A  ", team=Team.CUT)

    def test_update_employee_changes_name_team_and_active_flag(self) -> None:
        employee = self.service.create_employee(name="Nguyễn Văn A", team=Team.BLOW)

        updated = self.service.update_employee(
            employee.id,
            name="Trần Thị B",
            team=Team.CUT,
            is_active=False,
        )

        self.assertEqual(updated.name, "Trần Thị B")
        self.assertEqual(updated.team, Team.CUT)
        self.assertFalse(updated.is_active)

    def test_update_duplicate_name_ignores_current_employee_only(self) -> None:
        employee = self.service.create_employee(name="Nguyễn Văn A", team=Team.BLOW)
        self.service.update_employee(employee.id, name=" Nguyễn Văn A ", team=Team.CUT, is_active=True)
        other = self.service.create_employee(name="Trần Thị B", team=Team.CUT)

        with self.assertRaises(ValidationError):
            self.service.update_employee(other.id, name="Nguyễn Văn A", team=Team.CUT, is_active=True)

    def test_delete_employee_without_history_hard_deletes(self) -> None:
        employee = self.service.create_employee(name="Nguyễn Văn A", team=Team.BLOW)

        result = self.service.delete_or_deactivate_employee(employee.id)

        self.assertTrue(result.deleted_without_history)
        with AttendanceSessionLocal() as session:
            self.assertIsNone(session.get(Employee, employee.id))

    def test_delete_employee_with_history_deactivates(self) -> None:
        employee = self.service.create_employee(name="Nguyễn Văn A", team=Team.BLOW)
        with AttendanceSessionLocal() as session:
            period = Period(start_date=date(2026, 5, 1), end_date=date(2026, 5, 10))
            session.add(period)
            session.flush()
            session.add(
                DailyRecord(
                    employee_id=employee.id,
                    date=date(2026, 5, 1),
                    period_id=period.id,
                    status=DailyRecordStatus.DRAFT,
                    total_amount_snapshot=0,
                )
            )
            session.commit()

        result = self.service.delete_or_deactivate_employee(employee.id)

        self.assertFalse(result.deleted_without_history)
        with AttendanceSessionLocal() as session:
            stored = session.get(Employee, employee.id)
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertFalse(stored.is_active)

    def test_list_employees_hides_inactive_by_default(self) -> None:
        active = self.service.create_employee(name="Active", team=Team.BLOW)
        inactive = self.service.create_employee(name="Inactive", team=Team.CUT, is_active=False)

        active_names = {employee.name for employee in self.service.list_employees()}
        all_names = {employee.name for employee in self.service.list_employees(include_inactive=True)}

        self.assertIn(active.name, active_names)
        self.assertNotIn(inactive.name, active_names)
        self.assertEqual(all_names, {"Active", "Inactive"})

    def test_search_employees_filters_by_name(self) -> None:
        self.service.create_employee(name="Nguyễn Văn A", team=Team.BLOW)
        self.service.create_employee(name="Trần Thị B", team=Team.CUT)

        names = {employee.name for employee in self.service.list_employees(search_text="văn")}

        self.assertEqual(names, {"Nguyễn Văn A"})

    def test_attendance_page_uses_real_employee_tab(self) -> None:
        page = AttendancePage()
        employee_tab = page.findChild(EmployeeManagementTab)

        self.assertIsNotNone(employee_tab)
        assert employee_tab is not None
        table = employee_tab.table
        self.assertIsNotNone(table)
        assert table is not None
        self.assertEqual([table.horizontalHeaderItem(index).text() for index in range(table.columnCount())], ["Tên", "Tổ", "Trạng thái"])


if __name__ == "__main__":
    unittest.main()
