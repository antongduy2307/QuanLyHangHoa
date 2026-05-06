import os
import shutil
import sqlite3
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from sqlalchemy import select

import main_window
from main_window import MainWindow
from models import BagType
from models import Employee
from models import Team
from models import WorkType
import attendance_service


class FixedDate(date):
    today_value = date(2026, 4, 6)

    @classmethod
    def today(cls) -> "FixedDate":
        return cls(cls.today_value.year, cls.today_value.month, cls.today_value.day)


class ReportUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.workspace_temp_root = Path.cwd() / ".tmp_testdata"
        self.workspace_temp_root.mkdir(exist_ok=True)
        self.temp_dir_path = self.workspace_temp_root / f"report_{uuid.uuid4().hex}"
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
        self.date_patcher = mock.patch.object(main_window, "date", FixedDate)
        self.date_patcher.start()

        self.window = MainWindow()
        self.process_events()
        self.seed_report_periods()
        self.seed_blow_report_data()
        self.seed_cut_report_data()
        self.window.reload_all_ui_data()
        self.process_events()

    def tearDown(self) -> None:
        self.window.close()
        self.window.engine.dispose()
        self.date_patcher.stop()
        self.engine_patcher.stop()
        for patcher in reversed(self.messagebox_patches):
            patcher.stop()
        shutil.rmtree(self.temp_dir_path, ignore_errors=True)

    def process_events(self) -> None:
        self.app.processEvents()

    def seed_report_periods(self) -> None:
        with self.window.SessionLocal() as session:
            self.window.ensure_period_for_date(session, date(2026, 4, 12))
            self.window.ensure_period_for_date(session, date(2026, 4, 21))
            session.commit()

    def get_employee(self, session, name: str) -> Employee:
        employee = session.scalar(select(Employee).where(Employee.name == name))
        self.assertIsNotNone(employee)
        return employee

    def get_work_type_id_map(self, session) -> dict[str, int]:
        return {work_type.name: work_type.id for work_type in session.scalars(select(WorkType)).all()}

    def get_bag_type_id_map(self, session) -> dict[str, int]:
        return {bag_type.name: bag_type.id for bag_type in session.scalars(select(BagType)).all()}

    def seed_blow_record(
        self,
        employee_name: str,
        selected_day: date,
        entries: dict[str, int | None],
        *,
        absent: bool = False,
    ) -> None:
        with self.window.SessionLocal() as session:
            self.window.ensure_period_for_date(session, selected_day)
            employee = self.get_employee(session, employee_name)
            work_type_ids = self.get_work_type_id_map(session)
            attendance_service.save_attendance(
                session,
                employee.id,
                selected_day,
                Team.BLOW,
                {work_type_ids[work_name]: quantity for work_name, quantity in entries.items()},
                [],
                is_absent=absent,
                mark_done=True,
            )

    def seed_cut_record(
        self,
        employee_name: str,
        selected_day: date,
        entries: dict[str, int],
        *,
        absent: bool = False,
        keep_inactive_after_save: bool = False,
    ) -> None:
        with self.window.SessionLocal() as session:
            self.window.ensure_period_for_date(session, selected_day)
            employee = self.get_employee(session, employee_name)
            original_active = employee.is_active
            if not employee.is_active:
                employee.is_active = True
                session.flush()
            bag_type_ids = self.get_bag_type_id_map(session)
            for bag_name in entries:
                bag_type = session.scalar(select(BagType).where(BagType.name == bag_name))
                self.assertIsNotNone(bag_type)
                if not bag_type.is_active:
                    bag_type.is_active = True
            session.flush()
            attendance_service.save_attendance(
                session,
                employee.id,
                selected_day,
                Team.CUT,
                {},
                [(bag_type_ids[bag_name], quantity) for bag_name, quantity in entries.items()],
                is_absent=absent,
                mark_done=True,
            )

        if keep_inactive_after_save and not original_active:
            with self.window.SessionLocal() as session:
                employee = self.get_employee(session, employee_name)
                employee.is_active = False
                for bag_name in entries:
                    if bag_name == "Bao PP":
                        bag_type = session.scalar(select(BagType).where(BagType.name == bag_name))
                        self.assertIsNotNone(bag_type)
                        bag_type.is_active = False
                session.commit()

    def seed_blow_report_data(self) -> None:
        self.seed_blow_record("Nguyen Van An", date(2026, 4, 1), {"Thừa máy": 2, "Máy nhỏ": 5})
        self.seed_blow_record("Le Quoc Cuong", date(2026, 4, 1), {"Phụ găng 1 máy": None})
        self.seed_blow_record("Nguyen Van An", date(2026, 4, 2), {"Phụ cắt": 3})
        self.seed_blow_record("Le Quoc Cuong", date(2026, 4, 2), {"Máy to": 1, "Phụ găng 2 máy": None})
        self.seed_blow_record("Hoang Minh Em", date(2026, 4, 2), {"Máy nhỏ": 2})

    def seed_cut_report_data(self) -> None:
        self.seed_cut_record("Tran Thi Binh", date(2026, 4, 11), {"Bao 25kg": 15})
        self.seed_cut_record("Pham Thi Dung", date(2026, 4, 11), {"Bao 50kg": 4}, keep_inactive_after_save=True)
        self.seed_cut_record("Tran Thi Binh", date(2026, 4, 12), {}, absent=True)
        self.seed_cut_record(
            "Pham Thi Dung",
            date(2026, 4, 12),
            {"Bao 25kg": 9, "Bao 50kg": 3, "Bao PP": 4},
            keep_inactive_after_save=True,
        )
        self.seed_cut_record("Tran Thi Binh", date(2026, 4, 13), {"Bao 50kg": 7})

    def test_blow_report_hides_future_dates_and_uses_real_db_data(self) -> None:
        FixedDate.today_value = date(2026, 4, 6)
        self.window.report_team_combo.setCurrentIndex(0)
        self.window.report_period_combo.setCurrentIndex(0)
        self.window.refresh_report_table()
        self.process_events()

        self.assertEqual(self.window.report_table.rowCount(), 6)
        self.assertEqual(self.window.report_table.columnCount(), 12)
        self.assertFalse(self.window.report_table.horizontalHeader().isVisible())
        self.assertEqual(
            [label.text() for label in self.window.report_header_top_labels[1:4]],
            ["Hoang Minh Em", "Le Quoc Cuong", "Nguyen Van An"],
        )

        bottom_texts = [label.text() for label in self.window.report_header_bottom_labels]
        self.assertEqual(bottom_texts[1:3], ["MN", "Tổng"])
        self.assertEqual(bottom_texts[3:7], ["MT", "PG1", "PG2", "Tổng"])
        self.assertEqual(bottom_texts[7:11], ["TM", "MN", "PC", "Tổng"])

        self.assertEqual(self.window.report_table.item(0, 0).text(), "01/04")
        row0 = [self.window.report_table.item(0, c).text() for c in range(self.window.report_table.columnCount())]
        row1 = [self.window.report_table.item(1, c).text() for c in range(self.window.report_table.columnCount())]
        self.assertIn("1", row0)
        self.assertIn("30,000", row0)
        self.assertIn("310,000", row0)
        self.assertIn("340,000", row0)
        self.assertIn("2", row1)
        self.assertIn("3", row1)
        self.assertIn("90,000", row1)
        self.assertIn("150,000", row1)
        self.assertIn("60,000", row1)
        self.assertIn("300,000", row1)
        self.assertEqual(self.window.report_table.item(5, 0).text(), "06/04")
        self.assertEqual(self.window.report_table.item(5, 11).text(), "0")
        self.assertEqual(self.window.summary_total_employees.text(), "3")
        self.assertEqual(self.window.summary_total_days.text(), "5")
        self.assertEqual(self.window.summary_total_amount.text(), "640,000")

    def test_future_only_period_hides_all_rows_but_keeps_employee_groups(self) -> None:
        FixedDate.today_value = date(2026, 4, 6)
        self.window.report_team_combo.setCurrentIndex(1)
        self.window.report_period_combo.setCurrentIndex(2)
        self.window.refresh_report_table()
        self.process_events()

        self.assertEqual(self.window.report_table.rowCount(), 0)
        self.assertEqual(self.window.report_table.columnCount(), 3)
        self.assertEqual(self.window.summary_total_employees.text(), "1")
        self.assertEqual(self.window.summary_total_days.text(), "0")
        self.assertEqual(self.window.summary_total_amount.text(), "0")

    def test_cut_report_uses_real_db_data_and_includes_inactive_employee_with_history(self) -> None:
        FixedDate.today_value = date(2026, 4, 15)
        self.window.report_team_combo.setCurrentIndex(1)
        self.window.report_period_combo.setCurrentIndex(1)
        self.window.refresh_report_table()
        self.process_events()

        self.assertEqual(self.window.report_table.rowCount(), 5)
        self.assertEqual(self.window.report_table.columnCount(), 9)
        self.assertEqual(
            [label.text() for label in self.window.report_header_top_labels[1:3]],
            ["Pham Thi Dung", "Tran Thi Binh"],
        )

        bottom_texts = [label.text() for label in self.window.report_header_bottom_labels]
        self.assertEqual(bottom_texts[1:5], ["25kg", "50kg", "PP", "Tổng"])
        self.assertEqual(bottom_texts[5:8], ["25kg", "50kg", "Tổng"])

        self.assertEqual(self.window.report_table.item(0, 0).text(), "11/04")
        row0 = [self.window.report_table.item(0, c).text() for c in range(self.window.report_table.columnCount())]
        row1 = [self.window.report_table.item(1, c).text() for c in range(self.window.report_table.columnCount())]
        self.assertIn("4", row0)
        self.assertIn("16,800", row0)
        self.assertIn("15", row0)
        self.assertIn("52,500", row0)
        self.assertIn("69,300", row0)
        self.assertIn("9", row1)
        self.assertIn("3", row1)
        self.assertIn("4", row1)
        self.assertIn("59,700", row1)
        self.assertIn("0", row1)
        self.assertEqual(self.window.summary_total_employees.text(), "2")
        self.assertEqual(self.window.summary_total_days.text(), "4")
        self.assertEqual(self.window.summary_total_amount.text(), "158,400")


if __name__ == "__main__":
    unittest.main()
