from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QTableWidget

import core.config
from core.exceptions import ValidationError
from modules.attendance.db import AttendanceSessionLocal, get_attendance_engine, init_attendance_db, reset_attendance_engine_cache
from modules.attendance.models import DailyRecord, DailyRecordStatus, Employee, Period, Team
from modules.attendance.service import AttendanceEmployeeService, EmployeeDeleteResult
from modules.attendance.ui.employee_tab import EmployeeManagementTab
from modules.attendance.ui.page import AttendancePage
from shared.widgets.message_box import MessageBox


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

    def test_employee_tab_delete_button_enters_selection_mode_and_cancel_exits(self) -> None:
        self.service.create_employee(name="Alpha", team=Team.BLOW)
        self.service.create_employee(name="Beta", team=Team.CUT)
        tab = EmployeeManagementTab(self.service)

        tab.delete_button.click()

        self.assertEqual(tab.table.columnCount(), 4)
        self.assertTrue(tab.add_button.isHidden())
        self.assertFalse(tab.delete_selected_button.isHidden())
        self.assertFalse(tab.cancel_delete_button.isHidden())
        self.assertEqual(tab.selected_count_label.text(), "Đã chọn: 0")

        checkbox = tab.table.item(self._row_for_name(tab, "Alpha"), 0)
        self.assertIsNotNone(checkbox)
        assert checkbox is not None
        checkbox.setCheckState(Qt.CheckState.Checked)
        self.assertEqual(tab.selected_count_label.text(), "Đã chọn: 1")
        self.assertTrue(tab.delete_selected_button.isEnabled())

        tab.cancel_delete_button.click()

        self.assertEqual(tab.table.columnCount(), 3)
        self.assertFalse(tab.add_button.isHidden())
        self.assertTrue(tab.delete_selected_button.isHidden())
        self.assertEqual(tab.selected_count_label.text(), "Đã chọn: 0")

    def test_employee_tab_batch_delete_hard_deletes_and_deactivates_selected_employees(self) -> None:
        hard_deleted_employee = self.service.create_employee(name="Hard Delete", team=Team.BLOW)
        deactivated_employee = self.service.create_employee(name="Deactivate", team=Team.CUT)
        self._add_daily_record(deactivated_employee.id)
        tab = EmployeeManagementTab(self.service)
        changed_emissions: list[bool] = []
        tab.employees_changed.connect(lambda: changed_emissions.append(True))
        tab.delete_button.click()
        for name in ("Hard Delete", "Deactivate"):
            checkbox = tab.table.item(self._row_for_name(tab, name), 0)
            self.assertIsNotNone(checkbox)
            assert checkbox is not None
            checkbox.setCheckState(Qt.CheckState.Checked)

        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
            patch.object(MessageBox, "info") as info_mock,
            patch.object(MessageBox, "warning") as warning_mock,
        ):
            tab.delete_selected_button.click()

        with AttendanceSessionLocal() as session:
            self.assertIsNone(session.get(Employee, hard_deleted_employee.id))
            stored = session.get(Employee, deactivated_employee.id)
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertFalse(stored.is_active)
        self.assertEqual(len(changed_emissions), 1)
        warning_mock.assert_not_called()
        summary = info_mock.call_args.args[2]
        self.assertIn("1", summary)
        self.assertIn("xóa", summary.lower())
        self.assertIn("ngừng sử dụng", summary.lower())

    def test_employee_tab_batch_delete_continues_after_one_failure(self) -> None:
        class FakeService:
            def __init__(self) -> None:
                self.deleted_ids: list[int] = []

            def list_employees(self, *, search_text: str = "", include_inactive: bool = False):
                return [
                    SimpleNamespace(id=1, name="Ok", team=Team.BLOW, is_active=True),
                    SimpleNamespace(id=2, name="Fail", team=Team.CUT, is_active=True),
                ]

            def delete_or_deactivate_employee(self, employee_id: int) -> EmployeeDeleteResult:
                self.deleted_ids.append(employee_id)
                if employee_id == 2:
                    raise ValidationError("boom")
                return EmployeeDeleteResult(employee_id=employee_id, employee_name="Ok", deleted_without_history=True)

        service = FakeService()
        tab = EmployeeManagementTab(service)  # type: ignore[arg-type]
        changed_emissions: list[bool] = []
        tab.employees_changed.connect(lambda: changed_emissions.append(True))
        tab.delete_button.click()
        for name in ("Ok", "Fail"):
            checkbox = tab.table.item(self._row_for_name(tab, name), 0)
            self.assertIsNotNone(checkbox)
            assert checkbox is not None
            checkbox.setCheckState(Qt.CheckState.Checked)

        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
            patch.object(MessageBox, "warning") as warning_mock,
            patch.object(MessageBox, "info"),
        ):
            tab.delete_selected_button.click()

        self.assertEqual(service.deleted_ids, [1, 2])
        self.assertEqual(len(changed_emissions), 1)
        warning_summary = warning_mock.call_args.args[2]
        self.assertIn("1", warning_summary)
        self.assertIn("không xử lý", warning_summary.lower())

    def test_employee_tab_filter_change_exits_delete_selection_mode(self) -> None:
        self.service.create_employee(name="Alpha", team=Team.BLOW)
        self.service.create_employee(name="Beta", team=Team.CUT)
        tab = EmployeeManagementTab(self.service)
        tab.delete_button.click()
        self.assertEqual(tab.table.columnCount(), 4)

        tab.search_input.setText("Alpha")

        self.assertEqual(tab.table.columnCount(), 3)
        self.assertTrue(tab.delete_selected_button.isHidden())
        self.assertFalse(tab.add_button.isHidden())
        self.assertEqual(tab.table.rowCount(), 1)

    def test_attendance_page_uses_real_employee_tab(self) -> None:
        page = AttendancePage()
        employee_tab = page.findChild(EmployeeManagementTab)

        self.assertIsNotNone(employee_tab)
        assert employee_tab is not None
        table = employee_tab.table
        self.assertIsNotNone(table)
        assert table is not None
        self.assertEqual([table.horizontalHeaderItem(index).text() for index in range(table.columnCount())], ["Tên", "Tổ", "Trạng thái"])


    def _add_daily_record(self, employee_id: int) -> None:
        with AttendanceSessionLocal() as session:
            period = Period(start_date=date(2026, 5, 1), end_date=date(2026, 5, 10))
            session.add(period)
            session.flush()
            session.add(
                DailyRecord(
                    employee_id=employee_id,
                    date=date(2026, 5, 1),
                    period_id=period.id,
                    status=DailyRecordStatus.DRAFT,
                    total_amount_snapshot=0,
                )
            )
            session.commit()

    def _row_for_name(self, tab: EmployeeManagementTab, name: str) -> int:
        name_column = 1 if tab.table.columnCount() == 4 else 0
        for row in range(tab.table.rowCount()):
            item = tab.table.item(row, name_column)
            if item is not None and item.text() == name:
                return row
        raise AssertionError(f"employee row not found: {name}")


if __name__ == "__main__":
    unittest.main()
