from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QHeaderView, QTableWidget

import core.config
from modules.attendance.db import AttendanceSessionLocal, get_attendance_engine, init_attendance_db, reset_attendance_engine_cache
from modules.attendance.dto import AttendanceSavePayload, BlowWorkInput, CutWorkInput, ExtraCutWorkInput
from modules.attendance.models import BagType, Employee, Period, Team, WorkInputType, WorkType
from modules.attendance.report_service import AttendanceReportService
from modules.attendance.service import AttendanceDayEntryService, AttendanceEmployeeService
from modules.attendance.settings_service import AttendanceSettingsService
from modules.attendance.ui.report_tab import AttendanceReportTab, OVERALL_TOTAL_COLUMN_MIN_WIDTH, REPORT_GROUP_SPACER_WIDTH


class AttendanceReportTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temp_root = Path(tempfile.mkdtemp(prefix="attendance-report-"))
        self._env_patch = patch.dict(os.environ, {"LOCALAPPDATA": str(self._temp_root)}, clear=False)
        self._env_patch.start()
        core.config.get_settings.cache_clear()
        reset_attendance_engine_cache()
        init_attendance_db()
        self.employee_service = AttendanceEmployeeService()
        self.day_service = AttendanceDayEntryService()
        self.settings_service = AttendanceSettingsService()
        self.report_service = AttendanceReportService()

    def tearDown(self) -> None:
        QApplication.closeAllWindows()
        QApplication.processEvents()
        get_attendance_engine().dispose()
        reset_attendance_engine_cache()
        core.config.get_settings.cache_clear()
        self._env_patch.stop()
        shutil.rmtree(self._temp_root, ignore_errors=True)

    def _bag_type_id(self, name: str) -> int:
        with AttendanceSessionLocal() as session:
            return int(session.query(BagType).filter_by(name=name).one().id)

    def _configure_bag_type(self, name: str, *, quota_quantity: int, excess_unit_price: int) -> int:
        bag_id = self._bag_type_id(name)
        self.settings_service.update_bag_type(
            bag_id,
            name=name,
            quota_quantity=quota_quantity,
            excess_unit_price=excess_unit_price,
            is_active=True,
        )
        return bag_id

    def _period_id_for(self, selected_date: date) -> int:
        self.day_service.ensure_period_for_date(selected_date)
        with AttendanceSessionLocal() as session:
            period = session.query(Period).filter(Period.start_date <= selected_date, Period.end_date >= selected_date).one()
            return int(period.id)

    def _tick_work_type(self) -> tuple[int, int]:
        with AttendanceSessionLocal() as session:
            work_type = (
                session.query(WorkType)
                .filter_by(input_type=WorkInputType.TICK, is_active=True)
                .order_by(WorkType.id.asc())
                .first()
            )
            assert work_type is not None
            return int(work_type.id), int(work_type.unit_price)

    def test_blow_report_without_extra_cut_has_no_vk_column(self) -> None:
        employee = self.employee_service.create_employee(name="Blow No VK", team=Team.BLOW)
        work_type = self.settings_service.create_work_type(
            name="Report no VK quantity",
            input_type=WorkInputType.QUANTITY,
            unit_price=30000,
        )
        selected_date = date(2026, 5, 2)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                blow_work=[BlowWorkInput(work_type_id=work_type.id, quantity=2)],
            ),
            finalize=True,
        )
        period_id = self._period_id_for(selected_date)

        model = self.report_service.build_report(team=Team.BLOW, period_id=period_id, today=selected_date)

        self.assertNotIn("VK", model.employee_groups[0].work_labels)
        date_row = self._model_row(model, "02/05")
        self.assertEqual(date_row.total_amount, 0)
        self.assertEqual(model.rows[-1].date_label, "Tổng")
        self.assertEqual(model.rows[-1].total_amount, 0)
        self.assertEqual(model.total_amount, 0)

    def test_blow_report_uses_quantity_quota_amount(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Report Quota", team=Team.BLOW)
        work_type = self.settings_service.create_work_type(
            name="Report quota quantity",
            input_type=WorkInputType.QUANTITY,
            unit_price=30000,
        )
        selected_date = date(2026, 5, 2)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                blow_work=[BlowWorkInput(work_type_id=work_type.id, quantity=5)],
            ),
            finalize=True,
        )
        period_id = self._period_id_for(selected_date)

        model = self.report_service.build_report(team=Team.BLOW, period_id=period_id, today=selected_date)

        date_row = self._model_row(model, "02/05")
        self.assertEqual(date_row.total_amount, 60000)
        self.assertIn("60,000", date_row.values)
        self.assertNotIn("150,000", date_row.values)

    def test_blow_report_with_extra_cut_single_employee_adds_vk_and_totals(self) -> None:
        employee = self.employee_service.create_employee(name="Blow VK", team=Team.BLOW)
        tick_id, tick_amount = self._tick_work_type()
        bag_25_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)
        bag_50_id = self._configure_bag_type("Bao 50kg", quota_quantity=30, excess_unit_price=4200)
        selected_date = date(2026, 5, 2)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                blow_work=[BlowWorkInput(work_type_id=tick_id, quantity=None)],
                extra_cut_work=[
                    ExtraCutWorkInput(bag_type_id=bag_25_id, quantity=10),
                    ExtraCutWorkInput(bag_type_id=bag_50_id, quantity=5),
                ],
            ),
            finalize=True,
        )
        period_id = self._period_id_for(selected_date)

        model = self.report_service.build_report(team=Team.BLOW, period_id=period_id, today=selected_date)

        self.assertIn("VK", model.employee_groups[0].work_labels)
        self.assertEqual(model.employee_groups[0].columns[-2:], ["VK", "T\u1ed5ng"])
        date_row = self._model_row(model, "02/05")
        self.assertIn("56,000", date_row.values)
        self.assertEqual(date_row.total_amount, tick_amount + 56000)
        self.assertEqual(model.total_amount, tick_amount + 56000)

    def test_blow_report_extra_cut_only_counts_as_paid_day(self) -> None:
        employee = self.employee_service.create_employee(name="Blow VK Only", team=Team.BLOW)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)
        selected_date = date(2026, 5, 2)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=10)],
            ),
            finalize=True,
        )
        period_id = self._period_id_for(selected_date)

        model = self.report_service.build_report(team=Team.BLOW, period_id=period_id, today=selected_date)

        self.assertEqual(model.employee_groups[0].work_labels, ["VK"])
        date_row = self._model_row(model, "02/05")
        self.assertEqual(date_row.values, ["02/05", "35,000", "35,000", "35,000"])
        self.assertEqual(model.total_amount, 35000)
        self.assertEqual(model.total_workdays, 1)

    def test_blow_report_extra_cut_uses_saved_snapshot_after_bag_price_changes(self) -> None:
        employee = self.employee_service.create_employee(name="Blow VK Snapshot", team=Team.BLOW)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)
        selected_date = date(2026, 5, 2)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=10)],
            ),
            finalize=True,
        )
        self.settings_service.update_bag_type(
            bag_id,
            name="Bao 25kg",
            quota_quantity=25,
            excess_unit_price=999999,
            is_active=True,
        )
        period_id = self._period_id_for(selected_date)

        model = self.report_service.build_report(team=Team.BLOW, period_id=period_id, today=selected_date)

        date_row = self._model_row(model, "02/05")
        self.assertEqual(date_row.values, ["02/05", "35,000", "35,000", "35,000"])
        self.assertEqual(model.total_amount, 35000)

    def test_blow_report_vk_is_per_employee_and_day_total_includes_all_employees(self) -> None:
        employee_a = self.employee_service.create_employee(name="Blow A Has VK", team=Team.BLOW)
        employee_b = self.employee_service.create_employee(name="Blow B Plain", team=Team.BLOW)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)
        work_type = self.settings_service.create_work_type(
            name="Report plain quantity",
            input_type=WorkInputType.QUANTITY,
            unit_price=30000,
        )
        selected_date = date(2026, 5, 2)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_a.id,
                selected_date=selected_date,
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=10)],
            ),
            finalize=True,
        )
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_b.id,
                selected_date=selected_date,
                blow_work=[BlowWorkInput(work_type_id=work_type.id, quantity=5)],
            ),
            finalize=True,
        )
        period_id = self._period_id_for(selected_date)

        model = self.report_service.build_report(team=Team.BLOW, period_id=period_id, today=selected_date)

        self.assertEqual([group.employee_name for group in model.employee_groups], ["Blow A Has VK", "Blow B Plain"])
        self.assertEqual(model.employee_groups[0].work_labels, ["VK"])
        self.assertNotIn("VK", model.employee_groups[1].work_labels)
        date_row = self._model_row(model, "02/05")
        self.assertEqual(date_row.total_amount, 95000)
        self.assertEqual(model.total_amount, 95000)

    def test_cut_report_has_no_vk_and_uses_cut_daily_snapshot(self) -> None:
        employee = self.employee_service.create_employee(name="Cut No VK", team=Team.CUT)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=10000)
        selected_date = date(2026, 5, 2)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=30)],
            ),
            finalize=True,
        )
        period_id = self._period_id_for(selected_date)

        model = self.report_service.build_report(team=Team.CUT, period_id=period_id, today=selected_date)

        self.assertNotIn("VK", model.employee_groups[0].columns)
        date_row = self._model_row(model, "02/05")
        self.assertEqual(date_row.values, ["02/05", "30", "50,000", "50,000"])
        self.assertEqual(model.total_amount, 50000)

    def test_report_final_total_row_for_blow(self) -> None:
        employee_a = self.employee_service.create_employee(name="Blow Total A", team=Team.BLOW)
        employee_b = self.employee_service.create_employee(name="Blow Total B", team=Team.BLOW)
        work_type = self.settings_service.create_work_type(
            name="Report total quantity",
            input_type=WorkInputType.QUANTITY,
            unit_price=30000,
        )
        tick_id, tick_amount = self._tick_work_type()
        selected_date = date(2026, 5, 2)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_a.id,
                selected_date=selected_date,
                blow_work=[BlowWorkInput(work_type_id=work_type.id, quantity=5)],
            ),
            finalize=True,
        )
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_b.id,
                selected_date=selected_date,
                blow_work=[BlowWorkInput(work_type_id=tick_id, quantity=None)],
            ),
            finalize=True,
        )
        period_id = self._period_id_for(selected_date)

        model = self.report_service.build_report(team=Team.BLOW, period_id=period_id, today=selected_date)

        total_row = model.rows[-1]
        self.assertTrue(total_row.is_total)
        self.assertEqual(total_row.date_label, "Tổng")
        self.assertEqual(total_row.values, ["Tổng", "", "60,000", "", f"{tick_amount:,}", f"{60000 + tick_amount:,}"])
        self.assertEqual(total_row.total_amount, 60000 + tick_amount)

    def test_report_final_total_row_for_cut(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Total", team=Team.CUT)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=10000)
        selected_date = date(2026, 5, 2)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=30)],
            ),
            finalize=True,
        )
        period_id = self._period_id_for(selected_date)

        model = self.report_service.build_report(team=Team.CUT, period_id=period_id, today=selected_date)

        total_row = model.rows[-1]
        self.assertTrue(total_row.is_total)
        self.assertEqual(total_row.values, ["Tổng", "", "50,000", "50,000"])

    def test_report_final_total_row_sums_visible_partial_period_rows(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Partial", team=Team.BLOW)
        work_type = self.settings_service.create_work_type(
            name="Report partial quantity",
            input_type=WorkInputType.QUANTITY,
            unit_price=30000,
        )
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 2),
                blow_work=[BlowWorkInput(work_type_id=work_type.id, quantity=5)],
            ),
            finalize=True,
        )
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 8),
                blow_work=[BlowWorkInput(work_type_id=work_type.id, quantity=6)],
            ),
            finalize=True,
        )
        period_id = self._period_id_for(date(2026, 5, 2))

        model = self.report_service.build_report(team=Team.BLOW, period_id=period_id, today=date(2026, 5, 4))

        self.assertIsNotNone(self._model_row(model, "02/05"))
        self.assertFalse(any(row.date_label == "08/05" for row in model.rows))
        self.assertEqual(model.rows[-1].values, ["Tổng", "", "60,000", "60,000"])

    def test_report_tab_renders_vk_before_employee_total(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Group VK", team=Team.BLOW)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)
        selected_date = date(2026, 5, 2)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=10)],
            ),
            finalize=True,
        )
        self._period_id_for(selected_date)

        tab = AttendanceReportTab(AttendanceReportService())
        table = tab.table
        data_row = self._find_report_row(table, "02/05")

        self.assertIsInstance(table, QTableWidget)
        self.assertEqual(table.item(0, 1).text(), "Blow Group VK")
        self.assertEqual(table.columnSpan(0, 1), 2)
        self.assertEqual(table.item(1, 1).text(), "VK")
        self.assertEqual([table.item(data_row, column).text() for column in range(0, 4)], ["02/05", "35,000", "35,000", "35,000"])

    def test_report_tab_uses_natural_widths_and_spacer_between_employee_groups(self) -> None:
        employee_a = self.employee_service.create_employee(name="Lebron James", team=Team.BLOW)
        employee_b = self.employee_service.create_employee(name="Stephen Curry", team=Team.BLOW)
        work_type = self.settings_service.create_work_type(
            name="Layout quantity",
            input_type=WorkInputType.QUANTITY,
            unit_price=30000,
        )
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)
        selected_date = date(2026, 5, 2)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_a.id,
                selected_date=selected_date,
                blow_work=[BlowWorkInput(work_type_id=work_type.id, quantity=5)],
            ),
            finalize=True,
        )
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_b.id,
                selected_date=selected_date,
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=10)],
            ),
            finalize=True,
        )
        self._period_id_for(selected_date)

        tab = AttendanceReportTab(AttendanceReportService())
        table = tab.table
        QApplication.processEvents()
        data_row = self._find_report_row(table, "02/05")

        self.assertIsNone(getattr(table, "_full_width_resize_controller", None))
        header = table.horizontalHeader()
        self.assertFalse(header.stretchLastSection())
        for column in range(table.columnCount()):
            self.assertNotEqual(header.sectionResizeMode(column), QHeaderView.ResizeMode.Stretch)
        self.assertEqual(table.columnWidth(3), REPORT_GROUP_SPACER_WIDTH)
        self.assertLess(table.columnWidth(3), table.columnWidth(1))
        self.assertEqual(table.item(0, 3).text(), "")
        self.assertEqual(table.item(data_row, 3).text(), "")
        self.assertEqual(table.item(0, 1).text(), "Lebron James")
        self.assertEqual(table.item(0, 4).text(), "Stephen Curry")
        self.assertLessEqual(table.columnWidth(1), 84)
        self.assertLessEqual(table.columnWidth(2), 128)
        self.assertLessEqual(table.columnWidth(4), 84)
        self.assertGreaterEqual(table.columnWidth(table.columnCount() - 1), OVERALL_TOTAL_COLUMN_MIN_WIDTH)

    def test_monthly_date_range_uses_calendar_month(self) -> None:
        self.assertEqual(
            self.report_service.month_date_range(date(2026, 5, 10)),
            (date(2026, 5, 1), date(2026, 5, 31)),
        )
        self.assertEqual(
            self.report_service.month_date_range(date(2026, 4, 10)),
            (date(2026, 4, 1), date(2026, 4, 30)),
        )
        self.assertEqual(
            self.report_service.month_date_range(date(2024, 2, 10)),
            (date(2024, 2, 1), date(2024, 2, 29)),
        )

    def test_blow_monthly_report_sums_quantities_ticks_and_total_row(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Monthly", team=Team.BLOW)
        quantity_type = self.settings_service.create_work_type(
            name="Monthly quantity",
            input_type=WorkInputType.QUANTITY,
            unit_price=30000,
        )
        tick_type = self.settings_service.create_work_type(
            name="Monthly tick",
            input_type=WorkInputType.TICK,
            unit_price=25000,
        )
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 2),
                blow_work=[BlowWorkInput(work_type_id=quantity_type.id, quantity=5)],
            ),
            finalize=True,
        )
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 12),
                blow_work=[BlowWorkInput(work_type_id=tick_type.id, quantity=None)],
            ),
            finalize=True,
        )
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 25),
                blow_work=[BlowWorkInput(work_type_id=quantity_type.id, quantity=4)],
            ),
            finalize=True,
        )

        model = self.report_service.build_monthly_report(team=Team.BLOW, month_date=date(2026, 5, 1))

        self.assertEqual(model.month_start, date(2026, 5, 1))
        self.assertEqual(model.month_end, date(2026, 5, 31))
        self.assertEqual(model.columns, ["Tên nhân viên", "Monthly quantity", "Monthly tick", "Tổng tiền"])
        self.assertIn(["Blow Monthly", "9", "1", "115,000"], [row.values for row in model.rows])
        self.assertEqual(model.rows[-1].values, ["Tổng", "9", "1", "115,000"])
        self.assertEqual(model.total_amount, 115000)

    def test_blow_monthly_report_includes_vk_money(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Monthly VK", team=Team.BLOW)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 2),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=10)],
            ),
            finalize=True,
        )

        model = self.report_service.build_monthly_report(team=Team.BLOW, month_date=date(2026, 5, 1))

        self.assertEqual(model.columns, ["Tên nhân viên", "VK", "Tổng tiền"])
        self.assertIn(["Blow Monthly VK", "35,000", "35,000"], [row.values for row in model.rows])
        self.assertEqual(model.rows[-1].values, ["Tổng", "35,000", "35,000"])

    def test_cut_monthly_report_sums_bag_quantities_and_snapshots(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Monthly", team=Team.CUT)
        bag_25_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=10000)
        bag_50_id = self._configure_bag_type("Bao 50kg", quota_quantity=30, excess_unit_price=20000)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 2),
                cut_work=[CutWorkInput(bag_type_id=bag_25_id, quantity=30)],
            ),
            finalize=True,
        )
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 12),
                cut_work=[CutWorkInput(bag_type_id=bag_50_id, quantity=35)],
            ),
            finalize=True,
        )
        self.settings_service.update_bag_type(
            bag_25_id,
            name="Bao 25kg",
            quota_quantity=25,
            excess_unit_price=999999,
            is_active=True,
        )

        model = self.report_service.build_monthly_report(team=Team.CUT, month_date=date(2026, 5, 1))

        self.assertEqual(model.columns, ["Tên nhân viên", "25kg", "50kg", "Tổng tiền"])
        self.assertIn(["Cut Monthly", "30", "35", "150,000"], [row.values for row in model.rows])
        self.assertEqual(model.rows[-1].values, ["Tổng", "30", "35", "150,000"])
        self.assertEqual(model.total_amount, 150000)

    def test_monthly_report_includes_inactive_employee_with_records(self) -> None:
        employee = self.employee_service.create_employee(name="Inactive Monthly", team=Team.BLOW)
        work_type = self.settings_service.create_work_type(
            name="Inactive monthly quantity",
            input_type=WorkInputType.QUANTITY,
            unit_price=30000,
        )
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 2),
                blow_work=[BlowWorkInput(work_type_id=work_type.id, quantity=5)],
            ),
            finalize=True,
        )
        with AttendanceSessionLocal() as session:
            stored = session.get(Employee, employee.id)
            assert stored is not None
            stored.is_active = False
            session.commit()

        model = self.report_service.build_monthly_report(team=Team.BLOW, month_date=date(2026, 5, 1))

        self.assertIn("Inactive Monthly", [row.employee_name for row in model.rows])

    def test_report_tab_has_ten_day_and_monthly_subtabs(self) -> None:
        blow_employee = self.employee_service.create_employee(name="Blow UI Monthly", team=Team.BLOW)
        cut_employee = self.employee_service.create_employee(name="Cut UI Monthly", team=Team.CUT)
        work_type = self.settings_service.create_work_type(
            name="UI monthly quantity",
            input_type=WorkInputType.QUANTITY,
            unit_price=30000,
        )
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=10000)
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=blow_employee.id,
                selected_date=date(2026, 5, 2),
                blow_work=[BlowWorkInput(work_type_id=work_type.id, quantity=5)],
            ),
            finalize=True,
        )
        self.day_service.save_attendance(
            AttendanceSavePayload(
                employee_id=cut_employee.id,
                selected_date=date(2026, 5, 2),
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=30)],
            ),
            finalize=True,
        )
        self._period_id_for(date(2026, 5, 2))

        tab = AttendanceReportTab(AttendanceReportService())
        QApplication.processEvents()

        self.assertEqual(tab.report_tabs.count(), 2)
        self.assertEqual(tab.report_tabs.tabText(0), "10 ngày")
        self.assertEqual(tab.report_tabs.tabText(1), "30 ngày")
        self.assertGreater(tab.table.rowCount(), 0)
        tab.month_date_edit.setDate(QDate(2026, 5, 1))
        tab.month_team_combo.setCurrentIndex(tab.month_team_combo.findData(Team.BLOW.value))
        tab.refresh_monthly_report()
        self.assertGreater(tab.month_table.rowCount(), 0)
        tab.month_team_combo.setCurrentIndex(tab.month_team_combo.findData(Team.CUT.value))
        tab.refresh_monthly_report()
        self.assertGreater(tab.month_table.rowCount(), 0)

    def _find_report_row(self, table: QTableWidget, date_label: str) -> int:
        for row in range(2, table.rowCount()):
            item = table.item(row, 0)
            if item is not None and item.text() == date_label:
                return row
        self.fail(f"report row {date_label!r} not found")

    def _model_row(self, model, date_label: str):
        for row in model.rows:
            if row.date_label == date_label:
                return row
        self.fail(f"model row {date_label!r} not found")


if __name__ == "__main__":
    unittest.main()
