from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QDialog, QPushButton, QTabWidget, QTableWidget

import core.config
from core.exceptions import ValidationError
from modules.attendance.db import AttendanceSessionLocal, get_attendance_engine, init_attendance_db, reset_attendance_engine_cache
from modules.attendance.dto import AttendanceSavePayload, BlowWorkInput, CutWorkInput
from modules.attendance.models import BagType, CutLog, DailyRecord, Period, Team, WorkInputType, WorkLog, WorkType
from modules.attendance.report_service import AttendanceReportService
from modules.attendance.service import AttendanceDayEntryService, AttendanceEmployeeService
from modules.attendance.settings_service import AttendanceSettingsService
from modules.attendance.ui.settings_tab import AttendancePriceSettingsTab, BagTypeFormValue, WorkTypeFormValue
from modules.settings.service import SettingsService
from modules.settings.ui.page import SettingsPage


class _SignalStub:
    def connect(self, _callback) -> None:
        return


class _NoopProductSyncService:
    def sync_products_to_cut_work(self):
        return type("SyncResult", (), {"warnings": []})()


class _NoopInventoryEffectService:
    def reconcile_daily_record_effects(self, snapshot):
        self.last_snapshot = snapshot
        return None


class AttendanceSettingsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temp_root = Path(tempfile.mkdtemp(prefix="attendance-settings-"))
        self._env_patch = patch.dict(os.environ, {"LOCALAPPDATA": str(self._temp_root)}, clear=False)
        self._env_patch.start()
        core.config.get_settings.cache_clear()
        reset_attendance_engine_cache()
        init_attendance_db()
        self.employee_service = AttendanceEmployeeService()
        self.day_service = AttendanceDayEntryService(inventory_effect_service=_NoopInventoryEffectService())
        self.settings_service = AttendanceSettingsService()
        self.report_service = AttendanceReportService()

    def _settings_tab(self) -> AttendancePriceSettingsTab:
        return AttendancePriceSettingsTab(AttendanceSettingsService(), product_sync_service=_NoopProductSyncService())

    def tearDown(self) -> None:
        get_attendance_engine().dispose()
        reset_attendance_engine_cache()
        core.config.get_settings.cache_clear()
        self._env_patch.stop()
        shutil.rmtree(self._temp_root, ignore_errors=True)

    def _work_type(self, name: str) -> WorkType:
        with AttendanceSessionLocal() as session:
            return session.query(WorkType).filter_by(name=name).one()

    def _bag_type(self, name: str) -> BagType:
        with AttendanceSessionLocal() as session:
            return session.query(BagType).filter_by(name=name).one()

    def _configure_bag_type(self, name: str, *, quota_quantity: int, excess_unit_price: int) -> BagType:
        bag_type = self._bag_type(name)
        self.settings_service.update_bag_type(
            bag_type.id,
            name=bag_type.name,
            quota_quantity=quota_quantity,
            excess_unit_price=excess_unit_price,
            is_active=True,
        )
        with AttendanceSessionLocal() as session:
            stored = session.get(BagType, bag_type.id)
            assert stored is not None
            stored.is_product_linked = True
            stored.source_product_id = int(stored.id) + 10_000
            stored.source_product_name_snapshot = stored.name
            stored.is_excluded_from_attendance = False
            stored.is_legacy = False
            session.commit()
        return self._bag_type(name)

    def _period_id_for(self, selected_date: date) -> int:
        self.day_service.ensure_period_for_date(selected_date)
        with AttendanceSessionLocal() as session:
            return int(session.query(Period).filter(Period.start_date <= selected_date, Period.end_date >= selected_date).one().id)

    def _model_row(self, model, date_label: str):
        for row in model.rows:
            if row.date_label == date_label:
                return row
        self.fail(f"model row {date_label!r} not found")

    def test_work_type_price_update_affects_future_snapshot(self) -> None:
        employee = self.employee_service.create_employee(name="Blow A", team=Team.BLOW)
        may_nho = self._work_type("Máy nhỏ")
        self.settings_service.update_work_type(may_nho.id, name=may_nho.name, unit_price=45000, is_active=True)

        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[BlowWorkInput(work_type_id=may_nho.id, quantity=5)],
            ),
            finalize=True,
        )

        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            log = session.query(WorkLog).filter_by(daily_record_id=record.id, work_type_id=may_nho.id).one()
            self.assertEqual(log.unit_price_snapshot, 45000)
            self.assertEqual(log.amount_snapshot, 225000)

    def test_old_snapshot_unchanged_after_work_type_price_update(self) -> None:
        employee = self.employee_service.create_employee(name="Blow A", team=Team.BLOW)
        may_nho = self._work_type("Máy nhỏ")
        selected_date = date(2026, 5, 6)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                blow_work=[BlowWorkInput(work_type_id=may_nho.id, quantity=5)],
            ),
            finalize=True,
        )

        self.settings_service.update_work_type(may_nho.id, name=may_nho.name, unit_price=99999, is_active=True)
        period_id = self._period_id_for(selected_date)
        model = self.report_service.build_report(team=Team.BLOW, period_id=period_id, today=selected_date)

        self.assertEqual(self._model_row(model, "06/05").values, ["06/05", "5", "150,000", "150,000"])
        self.assertEqual(model.total_amount, 150000)

    def test_bag_type_price_update_affects_future_snapshot(self) -> None:
        employee = self.employee_service.create_employee(name="Cut A", team=Team.CUT)
        bag_25 = self._configure_bag_type("Bao 25kg", quota_quantity=0, excess_unit_price=3500)
        self.settings_service.update_bag_type(
            bag_25.id,
            name=bag_25.name,
            quota_quantity=2,
            excess_unit_price=5000,
            is_active=True,
        )

        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                cut_work=[CutWorkInput(bag_type_id=bag_25.id, quantity=3)],
            ),
            finalize=True,
        )

        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            log = session.query(CutLog).filter_by(daily_record_id=record.id, bag_type_id=bag_25.id).one()
            self.assertEqual(log.unit_price_snapshot, 5000)
            self.assertEqual(log.quota_quantity_snapshot, 2)
            self.assertEqual(log.excess_unit_price_snapshot, 5000)
            self.assertEqual(record.total_amount_snapshot, 5000)

    def test_inactive_work_type_hides_from_new_entry_but_report_keeps_history(self) -> None:
        employee = self.employee_service.create_employee(name="Blow A", team=Team.BLOW)
        may_nho = self._work_type("Máy nhỏ")
        selected_date = date(2026, 5, 6)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                blow_work=[BlowWorkInput(work_type_id=may_nho.id, quantity=5)],
            ),
            finalize=True,
        )
        self.settings_service.set_work_type_active(may_nho.id, False)

        new_entry = self.day_service.get_day_entry(employee.id, date(2026, 5, 7))
        old_entry = self.day_service.get_day_entry(employee.id, selected_date)
        period_id = self._period_id_for(selected_date)
        model = self.report_service.build_report(team=Team.BLOW, period_id=period_id, today=selected_date)

        self.assertNotIn(may_nho.id, {work_type.id for work_type in new_entry.work_types})
        self.assertIn(may_nho.id, {work_type.id for work_type in old_entry.work_types})
        self.assertEqual(model.employee_groups[0].work_labels, ["MN"])
        self.assertEqual(self._model_row(model, "06/05").values, ["06/05", "5", "150,000", "150,000"])

    def test_inactive_bag_type_hides_from_new_entry_but_report_keeps_history(self) -> None:
        employee = self.employee_service.create_employee(name="Cut A", team=Team.CUT)
        bag_25 = self._configure_bag_type("Bao 25kg", quota_quantity=1, excess_unit_price=3500)
        selected_date = date(2026, 5, 6)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                cut_work=[CutWorkInput(bag_type_id=bag_25.id, quantity=3)],
            ),
            finalize=True,
        )
        self.settings_service.set_bag_type_active(bag_25.id, False)

        new_entry = self.day_service.get_day_entry(employee.id, date(2026, 5, 7))
        old_entry = self.day_service.get_day_entry(employee.id, selected_date)
        period_id = self._period_id_for(selected_date)
        model = self.report_service.build_report(team=Team.CUT, period_id=period_id, today=selected_date)

        self.assertNotIn(bag_25.id, {bag_type.id for bag_type in new_entry.bag_types})
        self.assertIn(bag_25.id, {bag_type.id for bag_type in old_entry.bag_types})
        self.assertEqual(model.employee_groups[0].work_labels, ["25kg"])
        self.assertEqual(self._model_row(model, "06/05").values, ["06/05", "3", "7,000", "7,000"])

    def test_validation_rejects_empty_duplicate_and_negative_price(self) -> None:
        may_nho = self._work_type("Máy nhỏ")
        may_to = self._work_type("Máy to")
        bag_25 = self._bag_type("Bao 25kg")
        bag_50 = self._bag_type("Bao 50kg")

        with self.assertRaises(ValidationError):
            self.settings_service.update_work_type(may_nho.id, name="  ", unit_price=1000, is_active=True)
        with self.assertRaises(ValidationError):
            self.settings_service.update_work_type(may_nho.id, name=may_to.name, unit_price=1000, is_active=True)
        with self.assertRaises(ValidationError):
            self.settings_service.update_work_type(may_nho.id, name=may_nho.name, unit_price=-1, is_active=True)
        with self.assertRaises(ValidationError):
            self.settings_service.update_bag_type(bag_25.id, name="  ", quota_quantity=0, excess_unit_price=1000, is_active=True)
        with self.assertRaises(ValidationError):
            self.settings_service.update_bag_type(bag_25.id, name=bag_50.name, quota_quantity=0, excess_unit_price=1000, is_active=True)
        with self.assertRaises(ValidationError):
            self.settings_service.update_bag_type(bag_25.id, name=bag_25.name, quota_quantity=-1, excess_unit_price=1000, is_active=True)
        with self.assertRaises(ValidationError):
            self.settings_service.update_bag_type(bag_25.id, name=bag_25.name, quota_quantity=0, excess_unit_price=-1, is_active=True)

    def test_settings_page_has_general_and_attendance_price_tabs(self) -> None:
        page = SettingsPage(SettingsService())
        tabs = page.findChild(QTabWidget)
        self.assertIsNotNone(tabs)
        self.assertEqual([tabs.tabText(index) for index in range(tabs.count())], ["Cài đặt chung", "Cài đặt giá chấm công"])
        attendance_tab = page.findChild(AttendancePriceSettingsTab)
        self.assertIsNotNone(attendance_tab)
        self.assertGreaterEqual(len(attendance_tab.findChildren(QTableWidget)), 2)
        button_texts = {button.text() for button in attendance_tab.findChildren(QPushButton)}
        self.assertEqual(button_texts, {"Thêm"})
        self.assertEqual(attendance_tab.work_type_table.columnCount(), 3)
        self.assertEqual(attendance_tab.bag_type_table.columnCount(), 4)
        bag_headers = [
            attendance_tab.bag_type_table.horizontalHeaderItem(index).text()
            for index in range(attendance_tab.bag_type_table.columnCount())
        ]
        self.assertEqual(bag_headers[-1], "Không dùng cho chấm công")
        bag_headers = bag_headers[:3]
        self.assertEqual(bag_headers, ["Tên loại bao", "Số lượng khoán", "Thưởng mỗi bao vượt khoán"])

    def test_settings_tab_lists_only_active_rows_without_status_columns(self) -> None:
        may_nho = self._work_type("Máy nhỏ")
        bag_25 = self._bag_type("Bao 25kg")
        self.settings_service.set_work_type_active(may_nho.id, False)
        self.settings_service.set_bag_type_active(bag_25.id, False)

        tab = self._settings_tab()
        work_names = self._table_column_values(tab.work_type_table, 0)
        bag_names = self._table_column_values(tab.bag_type_table, 0)

        self.assertNotIn("Máy nhỏ", work_names)
        self.assertNotIn("Bao 25kg", bag_names)
        self.assertEqual(tab.work_type_table.columnCount(), 3)
        self.assertEqual(tab.bag_type_table.columnCount(), 4)

    def test_work_type_detail_popup_edits_and_deactivates(self) -> None:
        tab = self._settings_tab()
        row = self._find_row(tab.work_type_table, "Máy nhỏ")
        tab.work_type_table.selectRow(row)

        class FakeWorkTypeDialog:
            def __init__(self, *_args, **_kwargs) -> None:
                self.deactivate_requested = _SignalStub()

            def exec(self) -> QDialog.DialogCode:
                return QDialog.DialogCode.Accepted

            def value(self) -> WorkTypeFormValue:
                return WorkTypeFormValue(name="Máy nhỏ chỉnh", input_type=WorkInputType.QUANTITY, unit_price=46000)

        with patch("modules.attendance.ui.settings_tab.WorkTypeDialog", FakeWorkTypeDialog):
            tab._edit_work_type()

        self.assertIn("Máy nhỏ chỉnh", self._table_column_values(tab.work_type_table, 0))
        edited = self._work_type("Máy nhỏ chỉnh")
        fake_dialog = type("Dialog", (), {"accept": lambda self: None})()
        with patch.object(tab, "_confirm_deactivate", return_value=True):
            tab._deactivate_work_type_from_dialog(fake_dialog, edited.id)
        self.assertNotIn("Máy nhỏ chỉnh", self._table_column_values(tab.work_type_table, 0))
        self.assertFalse(self._work_type("Máy nhỏ chỉnh").is_active)

    def test_add_work_type_refreshes_active_table(self) -> None:
        tab = self._settings_tab()

        class FakeWorkTypeDialog:
            def __init__(self, *_args, **_kwargs) -> None:
                return

            def exec(self) -> QDialog.DialogCode:
                return QDialog.DialogCode.Accepted

            def value(self) -> WorkTypeFormValue:
                return WorkTypeFormValue(name="Việc mới", input_type=WorkInputType.QUANTITY, unit_price=12000)

        with patch("modules.attendance.ui.settings_tab.WorkTypeDialog", FakeWorkTypeDialog):
            tab._add_work_type()

        self.assertIn("Việc mới", self._table_column_values(tab.work_type_table, 0))

    def test_bag_type_detail_popup_edits_and_deactivates(self) -> None:
        tab = self._settings_tab()
        row = self._find_row(tab.bag_type_table, "Bao 25kg")
        tab.bag_type_table.selectRow(row)

        class FakeBagTypeDialog:
            def __init__(self, *_args, **_kwargs) -> None:
                self.deactivate_requested = _SignalStub()

            def exec(self) -> QDialog.DialogCode:
                return QDialog.DialogCode.Accepted

            def value(self) -> BagTypeFormValue:
                return BagTypeFormValue(name="Bao 25kg chỉnh", quota_quantity=25, excess_unit_price=5100)

        with patch("modules.attendance.ui.settings_tab.BagTypeDialog", FakeBagTypeDialog):
            tab._edit_bag_type()

        self.assertIn("Bao 25kg chỉnh", self._table_column_values(tab.bag_type_table, 0))
        edited = self._bag_type("Bao 25kg chỉnh")
        fake_dialog = type("Dialog", (), {"accept": lambda self: None})()
        with patch.object(tab, "_confirm_deactivate", return_value=True):
            tab._deactivate_bag_type_from_dialog(fake_dialog, edited.id)
        self.assertNotIn("Bao 25kg chỉnh", self._table_column_values(tab.bag_type_table, 0))
        self.assertFalse(self._bag_type("Bao 25kg chỉnh").is_active)

    def test_add_bag_type_refreshes_active_table(self) -> None:
        tab = self._settings_tab()

        class FakeBagTypeDialog:
            def __init__(self, *_args, **_kwargs) -> None:
                return

            def exec(self) -> QDialog.DialogCode:
                return QDialog.DialogCode.Accepted

            def value(self) -> BagTypeFormValue:
                return BagTypeFormValue(name="Bao mới", quota_quantity=30, excess_unit_price=2200)

        with patch("modules.attendance.ui.settings_tab.BagTypeDialog", FakeBagTypeDialog):
            tab._add_bag_type()

        self.assertIn("Bao mới", self._table_column_values(tab.bag_type_table, 0))

    def _table_column_values(self, table: QTableWidget, column: int) -> list[str]:
        return [
            table.item(row, column).text()
            for row in range(table.rowCount())
            if table.item(row, column) is not None
        ]

    def _find_row(self, table: QTableWidget, text: str) -> int:
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is not None and item.text() == text:
                return row
        self.fail(f"row {text!r} not found")


if __name__ == "__main__":
    unittest.main()
