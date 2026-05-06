import os
import shutil
import sqlite3
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main_window
from main_window import MainWindow
from models import DailyRecord
from models import Employee
from PyQt6.QtWidgets import QApplication
from services import get_or_create_daily_record


class EmployeeManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.workspace_temp_root = Path.cwd() / ".tmp_testdata"
        self.workspace_temp_root.mkdir(exist_ok=True)
        self.temp_dir_path = self.workspace_temp_root / f"employee_{uuid.uuid4().hex}"
        self.temp_dir_path.mkdir()
        self.db_file = self.temp_dir_path / "chamcong.db"
        sqlite3.connect(self.db_file).close()

        self.messagebox_patches = [
            mock.patch.object(main_window.QMessageBox, "information", return_value=None),
            mock.patch.object(main_window.QMessageBox, "warning", return_value=None),
            mock.patch.object(
                main_window.QMessageBox,
                "question",
                return_value=main_window.QMessageBox.StandardButton.Yes,
            ),
        ]
        for patcher in self.messagebox_patches:
            patcher.start()

        original_create_engine = main_window.create_engine
        self.engine_patcher = mock.patch.object(
            main_window,
            "create_engine",
            new=lambda *_args, **kwargs: original_create_engine(f"sqlite:///{self.db_file.as_posix()}", **kwargs),
        )
        self.engine_patcher.start()

        self.window = MainWindow()
        self.process_events()

    def tearDown(self) -> None:
        self.window.close()
        self.window.engine.dispose()
        self.engine_patcher.stop()
        for patcher in reversed(self.messagebox_patches):
            patcher.stop()
        shutil.rmtree(self.temp_dir_path, ignore_errors=True)

    def process_events(self) -> None:
        self.app.processEvents()

    def _select_management_employee(self, employee_name: str) -> int:
        employee_id = next(employee["id"] for employee in self.window.employees if employee["name"] == employee_name)
        restored = self.window.restore_management_employee_selection(employee_id)
        self.assertTrue(restored)
        self.process_events()
        return employee_id

    def test_add_edit_and_delete_employee_behaviors_remain_stable(self) -> None:
        with mock.patch.object(main_window.EmployeeDialog, "exec", return_value=main_window.QDialog.DialogCode.Accepted), mock.patch.object(
            main_window.EmployeeDialog,
            "get_form_data",
            return_value={"name": "Vo Minh Kha", "team_label": "Tổ thổi", "is_active": True},
        ):
            self.window.add_employee()
        self.process_events()

        with self.window.SessionLocal() as session:
            created = session.query(Employee).filter(Employee.name == "Vo Minh Kha").one_or_none()
            self.assertIsNotNone(created)
            self.assertTrue(created.is_active)

        self._select_management_employee("Vo Minh Kha")
        with mock.patch.object(main_window.EmployeeDialog, "exec", return_value=main_window.QDialog.DialogCode.Accepted), mock.patch.object(
            main_window.EmployeeDialog,
            "get_form_data",
            return_value={"name": "Vo Minh Kha Updated", "team_label": "Tổ cắt", "is_active": False},
        ):
            self.window.edit_employee()
        self.process_events()

        with self.window.SessionLocal() as session:
            updated = session.query(Employee).filter(Employee.name == "Vo Minh Kha Updated").one_or_none()
            self.assertIsNotNone(updated)
            self.assertFalse(updated.is_active)

        self._select_management_employee("Vo Minh Kha Updated")
        self.window.delete_employee()
        self.process_events()

        with self.window.SessionLocal() as session:
            deleted = session.query(Employee).filter(Employee.name == "Vo Minh Kha Updated").one_or_none()
            self.assertIsNone(deleted)

    def test_delete_employee_with_history_deactivates_instead_of_deleting(self) -> None:
        employee_id = self._select_management_employee("Nguyen Van An")

        with self.window.SessionLocal() as session:
            selected_day = date(2026, 4, 2)
            self.window.ensure_period_for_date(session, selected_day)
            get_or_create_daily_record(session, employee_id, selected_day)
            session.commit()

        self.window.delete_employee()
        self.process_events()

        with self.window.SessionLocal() as session:
            employee = session.get(Employee, employee_id)
            self.assertIsNotNone(employee)
            assert employee is not None
            self.assertFalse(employee.is_active)
            record = session.query(DailyRecord).filter(DailyRecord.employee_id == employee_id).one_or_none()
            self.assertIsNotNone(record)


if __name__ == "__main__":
    unittest.main()
