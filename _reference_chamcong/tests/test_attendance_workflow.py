import os
import shutil
import sqlite3
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication
from sqlalchemy import select

import main_window
from main_window import MainWindow
from models import DailyRecord
from models import DailyRecordStatus


class AttendanceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.workspace_temp_root = Path.cwd() / ".tmp_testdata"
        self.workspace_temp_root.mkdir(exist_ok=True)
        self.temp_dir_path = self.workspace_temp_root / f"case_{uuid.uuid4().hex}"
        self.temp_dir_path.mkdir()
        self.db_file = self.temp_dir_path / "chamcong.db"
        sqlite3.connect(self.db_file).close()
        self.messagebox_patches = [
            mock.patch.object(main_window.QMessageBox, "information", return_value=None),
            mock.patch.object(main_window.QMessageBox, "warning", return_value=None),
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

    def set_attendance_date(self, year: int, month: int, day: int) -> None:
        self.window.attendance_date_edit.setDate(QDate(year, month, day))
        self.process_events()

    def select_employee_by_team(self, team_label: str) -> int:
        employee_id = next(
            employee["id"]
            for employee in self.window.employees
            if employee["team"] == team_label and employee["active"]
        )
        restored = self.window.restore_attendance_employee_selection(employee_id)
        self.assertTrue(restored)
        self.process_events()
        return employee_id

    def get_daily_record_snapshot(self, employee_id: int, selected_day: date) -> dict[str, object]:
        with self.window.SessionLocal() as session:
            record = session.scalar(
                select(DailyRecord).where(
                    DailyRecord.employee_id == employee_id,
                    DailyRecord.date == selected_day,
                )
            )
            self.assertIsNotNone(record)
            return {
                "status": record.status,
                "is_absent": record.is_absent,
                "work_names": {log.work_type.name for log in record.work_logs},
            }

    def test_selected_date_drives_statuses_and_done_records_are_editable(self) -> None:
        employee_id = self.select_employee_by_team("Tổ thổi")

        self.set_attendance_date(2026, 4, 2)
        self.window.blow_glove_checkboxes["Phụ găng 1 máy"].setChecked(True)
        self.window.finalize_current_attendance()
        self.process_events()

        saved_day = date(2026, 4, 2)
        record = self.get_daily_record_snapshot(employee_id, saved_day)
        self.assertEqual(record["status"], DailyRecordStatus.DONE)
        self.assertEqual(record["work_names"], {"Phụ găng 1 máy"})
        self.assertEqual(self.window.attendance_status_map[employee_id], "Đã lưu")
        self.assertEqual(self.window.label_record_status.text(), "Đã lưu")

        self.set_attendance_date(2026, 4, 3)
        self.assertEqual(self.window.label_record_status.text(), "Chưa chấm")
        self.assertNotIn(employee_id, self.window.attendance_status_map)

        self.set_attendance_date(2026, 4, 2)
        self.assertTrue(self.window.blow_glove_checkboxes["Phụ găng 1 máy"].isChecked())
        self.assertEqual(self.window.label_record_status.text(), "Đã lưu")

        self.window.blow_glove_checkboxes["Phụ găng 2 máy"].setChecked(True)
        self.window.save_current_attendance_as_draft()
        self.process_events()

        updated_record = self.get_daily_record_snapshot(employee_id, saved_day)
        self.assertEqual(updated_record["status"], DailyRecordStatus.DRAFT)
        self.assertEqual(updated_record["work_names"], {"Phụ găng 2 máy"})
        self.assertEqual(self.window.attendance_status_map[employee_id], "Nháp")
        self.assertTrue(self.window.blow_glove_checkboxes["Phụ găng 2 máy"].isChecked())

    def test_absent_round_trip_works_for_selected_date(self) -> None:
        employee_id = self.select_employee_by_team("Tổ cắt")

        self.set_attendance_date(2026, 4, 5)
        self.window.absent_checkbox.setChecked(True)
        self.window.save_current_attendance_as_draft()
        self.process_events()

        saved_day = date(2026, 4, 5)
        record = self.get_daily_record_snapshot(employee_id, saved_day)
        self.assertTrue(record["is_absent"])
        self.assertEqual(record["status"], DailyRecordStatus.DRAFT)
        self.assertEqual(self.window.attendance_status_map[employee_id], "Nghỉ")
        self.assertEqual(self.window.label_record_status.text(), "Nghỉ")

        self.set_attendance_date(2026, 4, 6)
        self.assertEqual(self.window.label_record_status.text(), "Chưa chấm")

        self.set_attendance_date(2026, 4, 5)
        self.assertTrue(self.window.absent_checkbox.isChecked())
        self.assertEqual(self.window.label_record_status.text(), "Nghỉ")


if __name__ == "__main__":
    unittest.main()
