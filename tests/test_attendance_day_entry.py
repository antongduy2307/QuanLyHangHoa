from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QDate, QEvent, Qt
from PyQt6.QtWidgets import QApplication, QCheckBox, QDateEdit, QLabel, QPushButton, QScrollArea, QSpinBox, QTableWidget

import core.config
from core.exceptions import ValidationError
from modules.attendance.blow_work import calculate_blow_work_amount
from modules.attendance.cut_bonus import CutBonusItem, calculate_cut_employee_bonus
from modules.attendance.db import AttendanceSessionLocal, get_attendance_engine, init_attendance_db, reset_attendance_engine_cache
from modules.attendance.dto import AttendanceSavePayload, BlowWorkInput, CutWorkInput, ExtraCutWorkInput
from modules.attendance.models import BagType, CutLog, DailyRecord, DailyRecordStatus, Employee, ExtraCutWorkLog, Team, WorkInputType, WorkLog, WorkType
from modules.attendance.service import AttendanceDayEntryService, AttendanceEmployeeService
from modules.attendance.settings_service import AttendanceSettingsService
from modules.attendance.ui.day_entry_tab import AttendanceDayEntryTab
from modules.attendance.ui.page import AttendancePage
from shared.widgets.message_box import MessageBox
from shared.widgets.numeric_inputs import SelectAllQuantityInput, SelectAllSpinBox


class CutBonusCalculationTestCase(unittest.TestCase):
    def test_rule_1_below_average_quota_has_zero_bonus(self) -> None:
        bonus = calculate_cut_employee_bonus(
            [
                CutBonusItem(quantity=5, quota_quantity=15, excess_unit_price=10000),
                CutBonusItem(quantity=5, quota_quantity=20, excess_unit_price=20000),
            ]
        )

        self.assertEqual(bonus, Decimal("0"))

    def test_rule_1_exactly_average_quota_has_zero_bonus(self) -> None:
        bonus = calculate_cut_employee_bonus(
            [
                CutBonusItem(quantity=8, quota_quantity=15, excess_unit_price=10000),
                CutBonusItem(quantity=Decimal("9.5"), quota_quantity=20, excess_unit_price=20000),
            ]
        )

        self.assertEqual(bonus, Decimal("0"))

    def test_rule_2_one_bag_reaches_original_quota(self) -> None:
        bonus = calculate_cut_employee_bonus(
            [
                CutBonusItem(quantity=21, quota_quantity=20, excess_unit_price=10000),
                CutBonusItem(quantity=10, quota_quantity=15, excess_unit_price=15000),
            ]
        )

        self.assertEqual(bonus, Decimal("160000"))

    def test_rule_2_multiple_bags_one_reaches_original_quota(self) -> None:
        bonus = calculate_cut_employee_bonus(
            [
                CutBonusItem(quantity=20, quota_quantity=20, excess_unit_price=10000),
                CutBonusItem(quantity=10, quota_quantity=30, excess_unit_price=20000),
                CutBonusItem(quantity=5, quota_quantity=40, excess_unit_price=30000),
            ]
        )

        self.assertEqual(bonus, Decimal("350000"))

    def test_rule_2_multiple_bags_two_exceed_original_quota(self) -> None:
        bonus = calculate_cut_employee_bonus(
            [
                CutBonusItem(quantity=25, quota_quantity=20, excess_unit_price=10000),
                CutBonusItem(quantity=18, quota_quantity=15, excess_unit_price=15000),
                CutBonusItem(quantity=10, quota_quantity=30, excess_unit_price=5000),
            ]
        )

        self.assertEqual(bonus, Decimal("145000"))

    def test_rule_3_split_quota_when_no_bag_reaches_original_quota(self) -> None:
        bonus = calculate_cut_employee_bonus(
            [
                CutBonusItem(quantity=10, quota_quantity=15, excess_unit_price=10000),
                CutBonusItem(quantity=10, quota_quantity=20, excess_unit_price=20000),
            ]
        )

        self.assertEqual(bonus, Decimal("25000.0"))

    def test_rule_3_split_quota_with_three_bag_types(self) -> None:
        bonus = calculate_cut_employee_bonus(
            [
                CutBonusItem(quantity=7, quota_quantity=15, excess_unit_price=10000),
                CutBonusItem(quantity=7, quota_quantity=18, excess_unit_price=20000),
                CutBonusItem(quantity=7, quota_quantity=21, excess_unit_price=30000),
            ]
        )

        self.assertEqual(bonus, Decimal("40000"))

    def test_decimal_split_quota_has_no_float_artifacts(self) -> None:
        bonus = calculate_cut_employee_bonus(
            [
                CutBonusItem(quantity=6, quota_quantity=10, excess_unit_price=Decimal("0.10")),
                CutBonusItem(quantity=6, quota_quantity=11, excess_unit_price=Decimal("0.20")),
            ]
        )

        self.assertIsInstance(bonus, Decimal)
        self.assertEqual(bonus, Decimal("0.20"))

    def test_decimal_quantity_reaching_quota_uses_decimal_excess(self) -> None:
        bonus = calculate_cut_employee_bonus(
            [
                CutBonusItem(quantity=Decimal("20.5"), quota_quantity=20, excess_unit_price=10000),
            ]
        )

        self.assertEqual(bonus, Decimal("5000.0"))


class BlowWorkCalculationTestCase(unittest.TestCase):
    def test_thua_may_below_quota_has_zero_amount(self) -> None:
        amount = calculate_blow_work_amount(WorkInputType.QUANTITY, 2, 30000, "Thừa máy")

        self.assertEqual(amount, 0)

    def test_thua_may_exactly_quota_has_zero_amount(self) -> None:
        amount = calculate_blow_work_amount(WorkInputType.QUANTITY, 3, 30000, "Thừa máy")

        self.assertEqual(amount, 0)

    def test_thua_may_above_quota_uses_excess_only(self) -> None:
        amount = calculate_blow_work_amount(WorkInputType.QUANTITY, 5, 30000, "Thừa máy")

        self.assertEqual(amount, 60000)

    def test_may_nho_uses_normal_quantity_formula(self) -> None:
        amount = calculate_blow_work_amount(WorkInputType.QUANTITY, 5, 30000, "Máy nhỏ")

        self.assertEqual(amount, 150000)

    def test_may_to_uses_normal_quantity_formula(self) -> None:
        amount = calculate_blow_work_amount(WorkInputType.QUANTITY, 3, 40000, "Máy to")

        self.assertEqual(amount, 120000)

    def test_custom_quantity_work_uses_normal_quantity_formula(self) -> None:
        amount = calculate_blow_work_amount(WorkInputType.QUANTITY, 4, 10000, "Công việc mới")

        self.assertEqual(amount, 40000)

    def test_tick_work_keeps_unit_price_amount(self) -> None:
        amount = calculate_blow_work_amount(WorkInputType.TICK, 1, 20000, "PG1")

        self.assertEqual(amount, 20000)


class AttendanceDayEntryTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temp_root = Path(tempfile.mkdtemp(prefix="attendance-day-entry-"))
        self._env_patch = patch.dict(os.environ, {"LOCALAPPDATA": str(self._temp_root)}, clear=False)
        self._env_patch.start()
        core.config.get_settings.cache_clear()
        reset_attendance_engine_cache()
        init_attendance_db()
        self.employee_service = AttendanceEmployeeService()
        self.service = AttendanceDayEntryService()
        self.settings_service = AttendanceSettingsService()

    def tearDown(self) -> None:
        QApplication.closeAllWindows()
        QApplication.processEvents()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()
        get_attendance_engine().dispose()
        reset_attendance_engine_cache()
        core.config.get_settings.cache_clear()
        self._env_patch.stop()
        shutil.rmtree(self._temp_root, ignore_errors=True)

    def _work_type_id(self, name: str) -> int:
        with AttendanceSessionLocal() as session:
            return int(session.query(WorkType).filter_by(name=name).one().id)

    def _bag_type_id(self, name: str) -> int:
        with AttendanceSessionLocal() as session:
            bag_type = session.query(BagType).filter_by(name=name).one()
            bag_type.is_product_linked = True
            bag_type.source_product_id = int(bag_type.id) + 10_000
            bag_type.source_product_name_snapshot = name
            bag_type.is_excluded_from_attendance = False
            bag_type.is_legacy = False
            if Decimal(str(bag_type.quota_quantity)) <= 0:
                bag_type.quota_quantity = Decimal("10")
            if Decimal(str(bag_type.excess_unit_price)) <= 0:
                bag_type.excess_unit_price = Decimal("3500")
            session.commit()
            return int(bag_type.id)

    def _create_bag_type(
        self,
        name: str,
        *,
        quota_quantity: Decimal | int = Decimal("10"),
        excess_unit_price: Decimal | int = Decimal("3500"),
        is_active: bool = True,
        is_product_linked: bool = True,
        is_excluded_from_attendance: bool = False,
        is_legacy: bool = False,
    ) -> int:
        with AttendanceSessionLocal() as session:
            bag_type = BagType(
                name=name,
                unit_price=0,
                quota_quantity=Decimal(str(quota_quantity)),
                excess_unit_price=Decimal(str(excess_unit_price)),
                is_active=is_active,
                is_product_linked=is_product_linked,
                source_product_id=None if not is_product_linked else abs(hash(name)) % 1_000_000_000,
                source_product_name_snapshot=name if is_product_linked else None,
                is_excluded_from_attendance=is_excluded_from_attendance,
                is_legacy=is_legacy,
            )
            session.add(bag_type)
            session.commit()
            return int(bag_type.id)

    def _configure_bag_type(self, name: str, *, quota_quantity: int, excess_unit_price: int) -> int:
        bag_id = self._bag_type_id(name)
        self.settings_service.update_bag_type(
            bag_id,
            name=name,
            quota_quantity=quota_quantity,
            excess_unit_price=excess_unit_price,
            is_active=True,
        )
        with AttendanceSessionLocal() as session:
            bag_type = session.get(BagType, bag_id)
            assert bag_type is not None
            bag_type.is_product_linked = True
            bag_type.source_product_id = bag_id + 10_000
            bag_type.source_product_name_snapshot = name
            bag_type.is_excluded_from_attendance = False
            bag_type.is_legacy = False
            session.commit()
        return bag_id

    def test_cut_day_entry_available_bag_types_use_product_linked_config_filter(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Filter", team=Team.CUT)
        visible_id = self._create_bag_type("Linked configured")
        excluded_id = self._create_bag_type("Linked excluded", is_excluded_from_attendance=True)
        zero_quota_id = self._create_bag_type("Linked zero quota", quota_quantity=0, excess_unit_price=3500)
        zero_price_id = self._create_bag_type("Linked zero price", quota_quantity=10, excess_unit_price=0)
        manual_id = self._create_bag_type("Manual active", is_product_linked=False)
        legacy_id = self._create_bag_type("Legacy active", is_legacy=True)

        entry = self.service.get_day_entry(employee.id, date(2026, 5, 6))

        self.assertIn(visible_id, {bag_type.id for bag_type in entry.bag_types})
        self.assertNotIn(excluded_id, {bag_type.id for bag_type in entry.bag_types})
        self.assertNotIn(zero_quota_id, {bag_type.id for bag_type in entry.bag_types})
        self.assertNotIn(zero_price_id, {bag_type.id for bag_type in entry.bag_types})
        self.assertNotIn(manual_id, {bag_type.id for bag_type in entry.bag_types})
        self.assertNotIn(legacy_id, {bag_type.id for bag_type in entry.bag_types})

    def test_blow_extra_cut_available_bag_types_use_same_filter(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Filter", team=Team.BLOW)
        visible_id = self._create_bag_type("VK linked configured")
        excluded_id = self._create_bag_type("VK excluded", is_excluded_from_attendance=True)
        incomplete_id = self._create_bag_type("VK incomplete", quota_quantity=0, excess_unit_price=3500)

        entry = self.service.get_day_entry(employee.id, date(2026, 5, 6))

        bag_type_ids = {bag_type.id for bag_type in entry.bag_types}
        self.assertIn(visible_id, bag_type_ids)
        self.assertNotIn(excluded_id, bag_type_ids)
        self.assertNotIn(incomplete_id, bag_type_ids)

    def test_cut_search_hides_excluded_incomplete_and_manual_items(self) -> None:
        employee = self.employee_service.create_employee(name="Cut UI Filter", team=Team.CUT)
        self._create_bag_type("Search visible")
        self._create_bag_type("Search excluded", is_excluded_from_attendance=True)
        self._create_bag_type("Search incomplete", quota_quantity=10, excess_unit_price=0)
        self._create_bag_type("Search manual", is_product_linked=False)
        widget = AttendanceDayEntryTab(self.service)
        widget._current_entry = self.service.get_day_entry(employee.id, date(2026, 5, 6))

        names = {bag_type.name for bag_type in widget._available_cut_bag_types()}

        self.assertIn("Search visible", names)
        self.assertNotIn("Search excluded", names)
        self.assertNotIn("Search incomplete", names)
        self.assertNotIn("Search manual", names)

    def test_historical_cut_record_reloads_inactive_legacy_manual_bag_type_and_can_resave(self) -> None:
        employee = self.employee_service.create_employee(name="Cut History Filter", team=Team.CUT)
        bag_type_id = self._create_bag_type(
            "Old manual cut",
            is_active=True,
            is_product_linked=True,
            is_legacy=False,
        )
        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                cut_work=[CutWorkInput(bag_type_id=bag_type_id, quantity=Decimal("10.5"))],
            ),
            finalize=True,
        )
        with AttendanceSessionLocal() as session:
            bag_type = session.get(BagType, bag_type_id)
            assert bag_type is not None
            bag_type.is_active = False
            bag_type.is_product_linked = False
            bag_type.source_product_id = None
            bag_type.source_product_name_snapshot = None
            bag_type.is_legacy = True
            session.commit()

        entry = self.service.get_day_entry(employee.id, date(2026, 5, 6))
        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                cut_work=[CutWorkInput(bag_type_id=bag_type_id, quantity=Decimal("10.5"))],
            ),
            finalize=True,
        )

        self.assertIn(bag_type_id, {bag_type.id for bag_type in entry.bag_types})
        self.assertEqual(entry.cut_logs[0].quantity, Decimal("10.500"))
        self.assertGreaterEqual(result.record_id, 1)

    def test_historical_blow_extra_cut_reloads_inactive_excluded_legacy_bag_type_and_can_resave(self) -> None:
        employee = self.employee_service.create_employee(name="Blow History Filter", team=Team.BLOW)
        bag_type_id = self._create_bag_type("Old VK", quota_quantity=10, excess_unit_price=3500)
        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_type_id, quantity=Decimal("4.25"))],
            ),
            finalize=True,
        )
        with AttendanceSessionLocal() as session:
            bag_type = session.get(BagType, bag_type_id)
            assert bag_type is not None
            bag_type.is_active = False
            bag_type.is_excluded_from_attendance = True
            bag_type.is_legacy = True
            session.commit()

        entry = self.service.get_day_entry(employee.id, date(2026, 5, 6))
        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_type_id, quantity=Decimal("4.25"))],
            ),
            finalize=True,
        )

        self.assertIn(bag_type_id, {bag_type.id for bag_type in entry.bag_types})
        self.assertEqual(entry.extra_cut_work_logs[0].quantity, Decimal("4.250"))
        self.assertEqual(result.total_amount_snapshot, 14875)

    def test_decimal_quantities_save_and_reload_for_filtered_product_linked_cut_and_vk(self) -> None:
        cut_employee = self.employee_service.create_employee(name="Cut Decimal Filter", team=Team.CUT)
        blow_employee = self.employee_service.create_employee(name="Blow Decimal Filter", team=Team.BLOW)
        cut_bag_id = self._create_bag_type("Decimal cut", quota_quantity=10, excess_unit_price=5000)
        vk_bag_id = self._create_bag_type("Decimal vk", quota_quantity=10, excess_unit_price=3500)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=cut_employee.id,
                selected_date=date(2026, 5, 7),
                cut_work=[CutWorkInput(bag_type_id=cut_bag_id, quantity=Decimal("10.5"))],
            ),
            finalize=True,
        )
        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=blow_employee.id,
                selected_date=date(2026, 5, 7),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=vk_bag_id, quantity=Decimal("4.25"))],
            ),
            finalize=True,
        )

        cut_entry = self.service.get_day_entry(cut_employee.id, date(2026, 5, 7))
        blow_entry = self.service.get_day_entry(blow_employee.id, date(2026, 5, 7))

        self.assertEqual(cut_entry.cut_logs[0].quantity, Decimal("10.500"))
        self.assertEqual(blow_entry.extra_cut_work_logs[0].quantity, Decimal("4.250"))
        self.assertEqual(blow_entry.extra_cut_work_logs[0].amount_snapshot, 14875)

    def test_new_cut_save_accepts_configured_product_linked_bag_type(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Save Valid", team=Team.CUT)
        bag_type_id = self._create_bag_type("Valid cut save", quota_quantity=10, excess_unit_price=5000)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 8),
                cut_work=[CutWorkInput(bag_type_id=bag_type_id, quantity=Decimal("10.5"))],
            ),
            finalize=True,
        )

        self.assertGreaterEqual(result.record_id, 1)
        entry = self.service.get_day_entry(employee.id, date(2026, 5, 8))
        self.assertEqual(entry.cut_logs[0].quantity, Decimal("10.500"))

    def test_new_cut_save_rejects_excluded_bag_type(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Save Excluded", team=Team.CUT)
        bag_type_id = self._create_bag_type("Invalid cut excluded", is_excluded_from_attendance=True)

        with self.assertRaisesRegex(ValidationError, "Mặt hàng cắt này chưa được cấu hình"):
            self.service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee.id,
                    selected_date=date(2026, 5, 8),
                    cut_work=[CutWorkInput(bag_type_id=bag_type_id, quantity=1)],
                ),
                finalize=True,
            )

    def test_new_cut_save_rejects_zero_quota_bag_type(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Save Zero Quota", team=Team.CUT)
        bag_type_id = self._create_bag_type("Invalid cut quota", quota_quantity=0, excess_unit_price=5000)

        with self.assertRaisesRegex(ValidationError, "Mặt hàng cắt này chưa được cấu hình"):
            self.service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee.id,
                    selected_date=date(2026, 5, 8),
                    cut_work=[CutWorkInput(bag_type_id=bag_type_id, quantity=1)],
                ),
                finalize=True,
            )

    def test_new_cut_save_rejects_zero_excess_price_bag_type(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Save Zero Price", team=Team.CUT)
        bag_type_id = self._create_bag_type("Invalid cut price", quota_quantity=10, excess_unit_price=0)

        with self.assertRaisesRegex(ValidationError, "Mặt hàng cắt này chưa được cấu hình"):
            self.service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee.id,
                    selected_date=date(2026, 5, 8),
                    cut_work=[CutWorkInput(bag_type_id=bag_type_id, quantity=1)],
                ),
                finalize=True,
            )

    def test_new_cut_save_rejects_manual_non_product_linked_bag_type(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Save Manual", team=Team.CUT)
        bag_type_id = self._create_bag_type("Invalid cut manual", is_product_linked=False)

        with self.assertRaisesRegex(ValidationError, "Mặt hàng cắt này chưa được cấu hình"):
            self.service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee.id,
                    selected_date=date(2026, 5, 8),
                    cut_work=[CutWorkInput(bag_type_id=bag_type_id, quantity=1)],
                ),
                finalize=True,
            )

    def test_new_blow_extra_cut_save_uses_same_validation(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Save Invalid VK", team=Team.BLOW)
        invalid_id = self._create_bag_type("Invalid vk excluded", is_excluded_from_attendance=True)
        valid_id = self._create_bag_type("Valid vk save", quota_quantity=10, excess_unit_price=3500)

        with self.assertRaisesRegex(ValidationError, "Mặt hàng cắt này chưa được cấu hình"):
            self.service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee.id,
                    selected_date=date(2026, 5, 8),
                    extra_cut_work=[ExtraCutWorkInput(bag_type_id=invalid_id, quantity=1)],
                ),
                finalize=True,
            )

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 8),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=valid_id, quantity=Decimal("4.25"))],
            ),
            finalize=True,
        )
        self.assertEqual(result.total_amount_snapshot, 14875)

    def test_new_invalid_bag_type_added_to_existing_cut_record_is_rejected(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Existing Reject", team=Team.CUT)
        valid_id = self._create_bag_type("Existing valid cut", quota_quantity=10, excess_unit_price=5000)
        invalid_id = self._create_bag_type("New invalid cut", is_product_linked=False)
        selected_date = date(2026, 5, 8)
        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                cut_work=[CutWorkInput(bag_type_id=valid_id, quantity=1)],
            ),
            finalize=True,
        )

        with self.assertRaisesRegex(ValidationError, "Mặt hàng cắt này chưa được cấu hình"):
            self.service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee.id,
                    selected_date=selected_date,
                    cut_work=[
                        CutWorkInput(bag_type_id=valid_id, quantity=1),
                        CutWorkInput(bag_type_id=invalid_id, quantity=1),
                    ],
                ),
                finalize=True,
            )

    def test_period_bounds_for_date(self) -> None:
        self.assertEqual(self.service.period_bounds_for_date(date(2026, 5, 1)), (date(2026, 5, 1), date(2026, 5, 10)))
        self.assertEqual(self.service.period_bounds_for_date(date(2026, 5, 10)), (date(2026, 5, 1), date(2026, 5, 10)))
        self.assertEqual(self.service.period_bounds_for_date(date(2026, 5, 11)), (date(2026, 5, 11), date(2026, 5, 20)))
        self.assertEqual(self.service.period_bounds_for_date(date(2026, 5, 21)), (date(2026, 5, 21), date(2026, 5, 31)))
        self.assertEqual(self.service.period_bounds_for_date(date(2024, 2, 25)), (date(2024, 2, 21), date(2024, 2, 29)))
        self.assertEqual(self.service.period_bounds_for_date(date(2026, 2, 25)), (date(2026, 2, 21), date(2026, 2, 28)))

    def test_save_blow_draft_snapshots_total_and_logs(self) -> None:
        employee = self.employee_service.create_employee(name="Blow A", team=Team.BLOW)
        quantity_work_id = self._work_type_id("Thừa máy")
        tick_work_id = self._work_type_id("Phụ găng 1 máy")

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[
                    BlowWorkInput(work_type_id=quantity_work_id, quantity=2),
                    BlowWorkInput(work_type_id=tick_work_id, quantity=None),
                ],
            ),
            finalize=False,
        )

        self.assertEqual(result.status, DailyRecordStatus.DRAFT)
        self.assertEqual(result.total_amount_snapshot, 30000)
        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            logs = {log.work_type_id: log for log in session.query(WorkLog).filter_by(daily_record_id=record.id).all()}
            self.assertEqual(record.total_amount_snapshot, 30000)
            self.assertEqual(logs[quantity_work_id].quantity, 2)
            self.assertEqual(logs[quantity_work_id].unit_price_snapshot, 80000)
            self.assertEqual(logs[quantity_work_id].amount_snapshot, 0)
            self.assertEqual(logs[tick_work_id].quantity, 1)
            self.assertEqual(logs[tick_work_id].amount_snapshot, 30000)

    def test_thua_may_quantity_below_quota_has_zero_amount(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Qty Below", team=Team.BLOW)
        work_type_id = self._work_type_id("Thừa máy")

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[BlowWorkInput(work_type_id=work_type_id, quantity=2)],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 0)

    def test_thua_may_quantity_exactly_quota_has_zero_amount(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Qty Exact", team=Team.BLOW)
        work_type_id = self._work_type_id("Thừa máy")

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[BlowWorkInput(work_type_id=work_type_id, quantity=3)],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 0)

    def test_thua_may_quantity_above_quota_uses_excess_only(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Qty Above", team=Team.BLOW)
        work_type_id = self._work_type_id("Thừa máy")
        self.settings_service.update_work_type(work_type_id, name="Thừa máy", unit_price=30000, is_active=True)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[BlowWorkInput(work_type_id=work_type_id, quantity=5)],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 60000)

    def test_non_thua_may_quantity_work_uses_normal_quantity_formula(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Qty Normal", team=Team.BLOW)
        may_nho_id = self._work_type_id("Máy nhỏ")
        may_to_id = self._work_type_id("Máy to")

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[
                    BlowWorkInput(work_type_id=may_nho_id, quantity=5),
                    BlowWorkInput(work_type_id=may_to_id, quantity=3),
                ],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 270000)

    def test_future_custom_quantity_work_uses_normal_quantity_formula(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Qty Custom", team=Team.BLOW)
        work_type = self.settings_service.create_work_type(
            name="Công việc mới",
            input_type=WorkInputType.QUANTITY,
            unit_price=10000,
        )

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[BlowWorkInput(work_type_id=work_type.id, quantity=4)],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 40000)

    def test_save_blow_done_status_label(self) -> None:
        employee = self.employee_service.create_employee(name="Blow A", team=Team.BLOW)
        work_type_id = self._work_type_id("Máy nhỏ")

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[BlowWorkInput(work_type_id=work_type_id, quantity=1)],
            ),
            finalize=True,
        )

        self.assertEqual(result.status, DailyRecordStatus.DONE)
        self.assertEqual(self.service.record_status_label(employee.id, date(2026, 5, 6)), "Đã lưu")

    def test_blow_quantity_zero_is_ignored(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Zero", team=Team.BLOW)
        work_type_id = self._work_type_id("Máy nhỏ")

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[BlowWorkInput(work_type_id=work_type_id, quantity=0)],
            ),
            finalize=True,
        )

        self.assertEqual(result.status, DailyRecordStatus.DONE)
        self.assertEqual(result.total_amount_snapshot, 0)
        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            self.assertEqual(session.query(WorkLog).filter_by(daily_record_id=record.id, work_type_id=work_type_id).count(), 0)

    def test_glove_exclusivity_rejects_both_glove_work_types(self) -> None:
        employee = self.employee_service.create_employee(name="Blow A", team=Team.BLOW)
        glove_1_id = self._work_type_id("Phụ găng 1 máy")
        glove_2_id = self._work_type_id("Phụ găng 2 máy")

        with self.assertRaises(ValidationError):
            self.service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee.id,
                    selected_date=date(2026, 5, 6),
                    blow_work=[
                        BlowWorkInput(work_type_id=glove_1_id, quantity=None),
                        BlowWorkInput(work_type_id=glove_2_id, quantity=None),
                    ],
                ),
                finalize=False,
            )

    def test_save_cut_record_snapshots_total_and_logs(self) -> None:
        employee = self.employee_service.create_employee(name="Cut A", team=Team.CUT)
        bag_25_id = self._configure_bag_type("Bao 25kg", quota_quantity=20, excess_unit_price=10000)
        bag_50_id = self._configure_bag_type("Bao 50kg", quota_quantity=30, excess_unit_price=20000)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                cut_work=[
                    CutWorkInput(bag_type_id=bag_25_id, quantity=10),
                    CutWorkInput(bag_type_id=bag_50_id, quantity=5),
                ],
            ),
            finalize=True,
        )

        self.assertEqual(result.status, DailyRecordStatus.DONE)
        self.assertEqual(result.total_amount_snapshot, 0)
        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            logs = {log.bag_type_id: log for log in session.query(CutLog).filter_by(daily_record_id=record.id).all()}
            self.assertEqual(logs[bag_25_id].quantity, 10)
            self.assertEqual(logs[bag_25_id].quota_quantity_snapshot, 20)
            self.assertEqual(logs[bag_25_id].excess_unit_price_snapshot, 10000)
            self.assertEqual(logs[bag_25_id].amount_snapshot, 0)
            self.assertEqual(logs[bag_50_id].quota_quantity_snapshot, 30)
            self.assertEqual(logs[bag_50_id].excess_unit_price_snapshot, 20000)

        reloaded_entry = self.service.get_day_entry(employee.id, date(2026, 5, 6))
        reloaded_logs = {log.bag_type_id: log for log in reloaded_entry.cut_logs}
        self.assertEqual(reloaded_entry.record_status, DailyRecordStatus.DONE)
        self.assertEqual(reloaded_entry.total_amount_snapshot, 0)
        self.assertEqual(reloaded_logs[bag_25_id].quantity, 10)
        self.assertEqual(reloaded_logs[bag_50_id].quantity, 5)

    def test_cut_single_bag_over_quota_bonus(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Over", team=Team.CUT)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=10000)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=30)],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 50000)

    def test_cut_decimal_quantity_save_reload_and_bonus(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Decimal Save", team=Team.CUT)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=20, excess_unit_price=10000)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("20.5"))],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 5000)
        reloaded = self.service.get_day_entry(employee.id, date(2026, 5, 6))
        self.assertEqual(reloaded.cut_logs[0].quantity, Decimal("20.500"))

    def test_cut_negative_decimal_quantity_is_rejected(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Negative Decimal", team=Team.CUT)
        bag_id = self._bag_type_id("Bao 25kg")

        with self.assertRaises(ValidationError):
            self.service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee.id,
                    selected_date=date(2026, 5, 6),
                    cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("-0.5"))],
                ),
                finalize=True,
            )

    def test_cut_single_bag_exactly_quota_has_zero_bonus(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Exact", team=Team.CUT)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=10000)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=25)],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 0)

    def test_cut_single_bag_below_quota_has_zero_bonus(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Below", team=Team.CUT)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=10000)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=20)],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 0)

    def test_cut_multiple_bags_use_split_quota_rule_when_none_reaches_original_quota(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Multi", team=Team.CUT)
        bag_25_id = self._configure_bag_type("Bao 25kg", quota_quantity=20, excess_unit_price=10000)
        bag_50_id = self._configure_bag_type("Bao 50kg", quota_quantity=30, excess_unit_price=20000)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                cut_work=[
                    CutWorkInput(bag_type_id=bag_25_id, quantity=10),
                    CutWorkInput(bag_type_id=bag_50_id, quantity=20),
                ],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 100000)

    def test_cut_split_quota_preserves_decimal_intermediates(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Decimal", team=Team.CUT)
        bag_25_id = self._configure_bag_type("Bao 25kg", quota_quantity=20, excess_unit_price=10000)
        bag_50_id = self._configure_bag_type("Bao 50kg", quota_quantity=25, excess_unit_price=15000)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                cut_work=[
                    CutWorkInput(bag_type_id=bag_25_id, quantity=10),
                    CutWorkInput(bag_type_id=bag_50_id, quantity=20),
                ],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 112500)

    def test_cut_zero_quantity_is_ignored_in_average(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Zero", team=Team.CUT)
        bag_25_id = self._configure_bag_type("Bao 25kg", quota_quantity=100, excess_unit_price=999999)
        bag_50_id = self._configure_bag_type("Bao 50kg", quota_quantity=25, excess_unit_price=10000)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                cut_work=[
                    CutWorkInput(bag_type_id=bag_25_id, quantity=0),
                    CutWorkInput(bag_type_id=bag_50_id, quantity=30),
                ],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 50000)
        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            logs = session.query(CutLog).filter_by(daily_record_id=record.id).all()
            self.assertEqual([log.bag_type_id for log in logs], [bag_50_id])

    def test_absent_record_has_no_logs_and_zero_total(self) -> None:
        employee = self.employee_service.create_employee(name="Blow A", team=Team.BLOW)

        result = self.service.save_attendance(
            AttendanceSavePayload(employee_id=employee.id, selected_date=date(2026, 5, 6), is_absent=True),
            finalize=True,
        )

        self.assertTrue(result.is_absent)
        self.assertEqual(result.total_amount_snapshot, 0)
        self.assertEqual(self.service.record_status_label(employee.id, date(2026, 5, 6)), "Nghỉ")
        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            self.assertEqual(session.query(WorkLog).filter_by(daily_record_id=record.id).count(), 0)
            self.assertEqual(session.query(CutLog).filter_by(daily_record_id=record.id).count(), 0)

    def test_edit_done_record_replaces_old_logs_and_total(self) -> None:
        employee = self.employee_service.create_employee(name="Blow A", team=Team.BLOW)
        may_nho_id = self._work_type_id("Máy nhỏ")
        may_to_id = self._work_type_id("Máy to")

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[BlowWorkInput(work_type_id=may_nho_id, quantity=1)],
            ),
            finalize=True,
        )
        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[BlowWorkInput(work_type_id=may_to_id, quantity=3)],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 120000)
        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            logs = session.query(WorkLog).filter_by(daily_record_id=record.id).all()
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].work_type_id, may_to_id)
            self.assertEqual(logs[0].amount_snapshot, 120000)

    def test_employee_status_list_labels(self) -> None:
        no_record = self.employee_service.create_employee(name="No Record", team=Team.BLOW)
        draft = self.employee_service.create_employee(name="Draft", team=Team.BLOW)
        done = self.employee_service.create_employee(name="Done", team=Team.BLOW)
        absent = self.employee_service.create_employee(name="Absent", team=Team.BLOW)
        work_type_id = self._work_type_id("Máy nhỏ")
        selected_date = date(2026, 5, 6)

        self.service.save_attendance(
            AttendanceSavePayload(employee_id=draft.id, selected_date=selected_date, blow_work=[BlowWorkInput(work_type_id=work_type_id, quantity=1)]),
            finalize=False,
        )
        self.service.save_attendance(
            AttendanceSavePayload(employee_id=done.id, selected_date=selected_date, blow_work=[BlowWorkInput(work_type_id=work_type_id, quantity=1)]),
            finalize=True,
        )
        self.service.save_attendance(
            AttendanceSavePayload(employee_id=absent.id, selected_date=selected_date, is_absent=True),
            finalize=False,
        )

        statuses = {row.name: row.status_label for row in self.service.list_attendance_employees_for_date(selected_date)}

        self.assertEqual(statuses[no_record.name], "Chưa chấm")
        self.assertEqual(statuses[draft.name], "Nháp")
        self.assertEqual(statuses[done.name], "Đã lưu")
        self.assertEqual(statuses[absent.name], "Nghỉ")

    def test_blow_quantity_input_saves_without_checkbox_and_reloads(self) -> None:
        employee = self.employee_service.create_employee(name="Blow UI", team=Team.BLOW)
        may_nho_id = self._work_type_id("Máy nhỏ")
        glove_id = self._work_type_id("Phụ găng 1 máy")
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        quantity_checkbox, quantity_spinbox = tab._blow_controls[may_nho_id]
        glove_checkbox, glove_spinbox = tab._blow_controls[glove_id]
        self.assertIsNone(quantity_checkbox)
        self.assertIsInstance(quantity_spinbox, SelectAllSpinBox)
        self.assertNotIsInstance(quantity_spinbox, QSpinBox)
        self.assertIsInstance(glove_checkbox, QCheckBox)
        self.assertIsNone(glove_spinbox)

        quantity_spinbox.setValue(2)
        glove_checkbox.setChecked(True)
        self.assertEqual(tab.total_label.text(), "90,000")
        with patch.object(MessageBox, "info"), patch.object(MessageBox, "warning"), patch.object(MessageBox, "error"):
            tab._save_current(finalize=True)

        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            logs = {log.work_type_id: log for log in session.query(WorkLog).filter_by(daily_record_id=record.id).all()}
            self.assertEqual(logs[may_nho_id].quantity, 2)
            self.assertEqual(logs[glove_id].quantity, 1)
            self.assertEqual(record.total_amount_snapshot, 90000)

        tab._load_selected_employee()
        _checkbox, reloaded_quantity_spinbox = tab._blow_controls[may_nho_id]
        self.assertEqual(reloaded_quantity_spinbox.value(), 2)

    def test_blow_quantity_labels_only_show_quota_hint_for_thua_may(self) -> None:
        self.employee_service.create_employee(name="Blow Label", team=Team.BLOW)
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        labels = [label.text() for label in tab.findChildren(QLabel)]
        thua_may_label = next(text for text in labels if text.startswith("Thừa máy "))
        may_nho_label = next(text for text in labels if text.startswith("Máy nhỏ "))

        self.assertIn("khoán 3", thua_may_label)
        self.assertNotIn("khoán", may_nho_label)

    def test_blow_extra_cut_single_bag_adds_direct_amount(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Extra Single", team=Team.BLOW)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=10)],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 35000)
        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            log = session.query(ExtraCutWorkLog).filter_by(daily_record_id=record.id, bag_type_id=bag_id).one()
            self.assertEqual(log.quantity, 10)
            self.assertEqual(log.excess_unit_price_snapshot, 3500)
            self.assertEqual(log.amount_snapshot, 35000)

    def test_blow_extra_cut_decimal_quantity_adds_direct_amount_and_reloads(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Extra Decimal", team=Team.BLOW)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=Decimal("10.5"))],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 36750)
        reloaded = self.service.get_day_entry(employee.id, date(2026, 5, 6))
        self.assertEqual(reloaded.extra_cut_work_logs[0].quantity, Decimal("10.500"))

    def test_blow_extra_cut_multiple_bags_adds_direct_amounts(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Extra Multi", team=Team.BLOW)
        bag_25_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)
        bag_50_id = self._configure_bag_type("Bao 50kg", quota_quantity=30, excess_unit_price=4200)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                extra_cut_work=[
                    ExtraCutWorkInput(bag_type_id=bag_25_id, quantity=10),
                    ExtraCutWorkInput(bag_type_id=bag_50_id, quantity=5),
                ],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 56000)

    def test_blow_normal_work_and_extra_cut_total_together(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Extra Normal", team=Team.BLOW)
        glove_id = self._work_type_id("Phụ găng 1 máy")
        bag_25_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)
        bag_50_id = self._configure_bag_type("Bao 50kg", quota_quantity=30, excess_unit_price=4200)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                blow_work=[BlowWorkInput(work_type_id=glove_id, quantity=None)],
                extra_cut_work=[
                    ExtraCutWorkInput(bag_type_id=bag_25_id, quantity=10),
                    ExtraCutWorkInput(bag_type_id=bag_50_id, quantity=5),
                ],
            ),
            finalize=True,
        )

        self.assertEqual(result.total_amount_snapshot, 86000)

    def test_blow_extra_cut_snapshot_stability_after_bag_price_change(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Extra Snapshot", team=Team.BLOW)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)
        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=10)],
            ),
            finalize=True,
        )
        self.settings_service.update_bag_type(bag_id, name="Bao 25kg", quota_quantity=25, excess_unit_price=9900, is_active=True)

        reloaded_entry = self.service.get_day_entry(employee.id, date(2026, 5, 6))
        self.assertEqual(reloaded_entry.total_amount_snapshot, 35000)
        self.assertEqual(reloaded_entry.extra_cut_work_logs[0].excess_unit_price_snapshot, 3500)

    def test_blow_extra_cut_reload_ui_and_unchecked_clears_rows(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Extra Reload", team=Team.BLOW)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)
        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=10)],
            ),
            finalize=True,
        )
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        assert tab.extra_cut_checkbox is not None
        assert tab.extra_cut_table is not None
        self.assertTrue(tab.extra_cut_checkbox.isChecked())
        self.assertEqual(tab.extra_cut_table.rowCount(), 1)
        self.assertEqual(tab._extra_cut_controls[bag_id].value(), 10)
        self.assertIsInstance(tab.form_scroll_area, QScrollArea)
        self.assertTrue(tab.form_scroll_area.widgetResizable())
        self.assertFalse(tab.extra_cut_group.isHidden())
        self.assertLessEqual(tab.extra_cut_table.maximumHeight(), 220)

        tab.extra_cut_checkbox.setChecked(False)
        with patch.object(MessageBox, "info"), patch.object(MessageBox, "warning"), patch.object(MessageBox, "error"):
            tab._save_current(finalize=True)
        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            self.assertEqual(session.query(ExtraCutWorkLog).filter_by(daily_record_id=record.id).count(), 0)
            self.assertEqual(record.total_amount_snapshot, 0)

    def test_blow_extra_cut_section_hides_while_absent_and_restores(self) -> None:
        self.employee_service.create_employee(name="Blow Extra Absent UI", team=Team.BLOW)
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        assert tab.extra_cut_checkbox is not None
        assert tab.extra_cut_group is not None
        tab.extra_cut_checkbox.setChecked(True)
        self.assertFalse(tab.extra_cut_group.isHidden())

        tab.absent_checkbox.setChecked(True)
        self.assertTrue(tab.extra_cut_checkbox.isEnabled() is False)
        self.assertTrue(tab.extra_cut_group.isHidden())

        tab.absent_checkbox.setChecked(False)
        self.assertTrue(tab.extra_cut_checkbox.isEnabled())
        self.assertFalse(tab.extra_cut_group.isHidden())

    def test_blow_extra_cut_table_expands_for_selected_rows_only(self) -> None:
        self.employee_service.create_employee(name="Blow Extra Height", team=Team.BLOW)
        bag_25_id = self._bag_type_id("Bao 25kg")
        bag_50_id = self._bag_type_id("Bao 50kg")
        bag_100_id = self._create_bag_type("Bao height test", quota_quantity=10, excess_unit_price=1000)
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        assert tab.extra_cut_checkbox is not None
        assert tab.extra_cut_table is not None
        tab.extra_cut_checkbox.setChecked(True)
        initial_height = tab.extra_cut_table.height()

        tab._add_extra_cut_bag_by_id(bag_25_id)
        one_row_height = tab.extra_cut_table.height()
        tab._add_extra_cut_bag_by_id(bag_50_id)
        two_row_height = tab.extra_cut_table.height()
        tab._add_extra_cut_bag_by_id(bag_100_id)
        three_row_height = tab.extra_cut_table.height()

        self.assertGreaterEqual(one_row_height, initial_height)
        self.assertGreater(two_row_height, one_row_height)
        self.assertGreater(three_row_height, two_row_height)
        self.assertEqual(tab.extra_cut_table.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        tab._remove_extra_cut_bag_row(bag_100_id)
        self.assertEqual(tab.extra_cut_table.height(), two_row_height)

    def test_blow_absent_saves_no_extra_cut_rows(self) -> None:
        employee = self.employee_service.create_employee(name="Blow Extra Absent", team=Team.BLOW)
        bag_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=3500)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=date(2026, 5, 6),
                is_absent=True,
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=10)],
            ),
            finalize=True,
        )

        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            self.assertEqual(record.total_amount_snapshot, 0)
            self.assertEqual(session.query(ExtraCutWorkLog).filter_by(daily_record_id=record.id).count(), 0)

    def test_cut_form_starts_with_empty_selected_table_for_new_record(self) -> None:
        employee = self.employee_service.create_employee(name="Cut UI", team=Team.CUT)
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        self.assertIsNotNone(tab.cut_search_input)
        self.assertEqual(tab.cut_search_input.placeholderText(), "Tìm loại bao")
        self.assertIsNotNone(tab.cut_table)
        self.assertEqual(tab.cut_table.rowCount(), 0)
        self.assertEqual(tab._cut_controls, {})

    def test_cut_search_adds_bag_to_selected_table_with_editable_quantity(self) -> None:
        self.employee_service.create_employee(name="Cut Add", team=Team.CUT)
        bag_25_id = self._bag_type_id("Bao 25kg")
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        assert tab.cut_search_input is not None
        assert tab.cut_table is not None
        tab.cut_search_input.setText("25kg")
        tab._add_best_cut_bag_match()

        self.assertEqual(tab.cut_table.rowCount(), 1)
        self.assertEqual(self._cut_table_bag_ids(tab), [bag_25_id])
        quantity_input = self._cut_quantity_input(tab, bag_25_id)
        self.assertIsInstance(quantity_input, SelectAllQuantityInput)
        self.assertNotIsInstance(quantity_input, QSpinBox)
        self.assertEqual(quantity_input.value(), 1)
        quantity_input.setValue(Decimal("7.5"))
        self.assertEqual(tab._collect_payload().cut_work[0].quantity, Decimal("7.5"))
        quantity_input.clear()
        self.assertEqual(quantity_input.value(), 0)
        quantity_input.setValue(7)
        self.assertLessEqual(tab.cut_table.columnWidth(1), 140)
        self.assertLessEqual(tab.cut_table.columnWidth(2), 90)
        self.assertGreater(tab.cut_table.columnWidth(0), tab.cut_table.columnWidth(1))
        self.assertGreaterEqual(tab.cut_table.rowHeight(0), 56)
        self.assertEqual(quantity_input.maximumHeight(), 34)
        delete_button = self._cut_delete_button(tab, bag_25_id)
        self.assertEqual(delete_button.maximumHeight(), 34)
        self.assertLessEqual(delete_button.width(), 90)

    def test_cut_quantity_input_accepts_decimal_and_invalid_text_does_not_crash(self) -> None:
        self.employee_service.create_employee(name="Cut Decimal UI", team=Team.CUT)
        bag_25_id = self._bag_type_id("Bao 25kg")
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        tab._add_cut_bag_by_id(bag_25_id)
        quantity_input = self._cut_quantity_input(tab, bag_25_id)
        quantity_input.setText("10.5")
        self.assertEqual(quantity_input.value(), Decimal("10.5"))
        quantity_input.setText("invalid")
        self.assertEqual(quantity_input.value(), Decimal("10.5"))

    def test_cut_duplicate_add_focuses_existing_row_without_duplicate(self) -> None:
        self.employee_service.create_employee(name="Cut Duplicate", team=Team.CUT)
        bag_25_id = self._bag_type_id("Bao 25kg")
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        assert tab.cut_search_input is not None
        tab.cut_search_input.setText("25kg")
        tab._add_best_cut_bag_match()
        self._cut_quantity_input(tab, bag_25_id).setValue(7)
        tab.cut_search_input.setText("25kg")
        tab._add_best_cut_bag_match()

        self.assertEqual(tab.cut_table.rowCount(), 1)
        self.assertEqual(self._cut_quantity_input(tab, bag_25_id).value(), 7)
        self.assertEqual(tab.cut_table.currentRow(), 0)

    def test_cut_delete_row_removes_it_from_save_payload(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Delete", team=Team.CUT)
        bag_25_id = self._bag_type_id("Bao 25kg")
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        tab._add_cut_bag_by_id(bag_25_id)
        self._cut_quantity_input(tab, bag_25_id).setValue(10)
        self._cut_delete_button(tab, bag_25_id).click()

        self.assertEqual(tab.cut_table.rowCount(), 0)
        with patch.object(MessageBox, "info"), patch.object(MessageBox, "warning"), patch.object(MessageBox, "error"):
            tab._save_current(finalize=True)
        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(employee_id=employee.id, date=date(2026, 5, 6)).one()
            self.assertEqual(session.query(CutLog).filter_by(daily_record_id=record.id).count(), 0)

    def test_cut_save_reload_selected_table_values_only(self) -> None:
        self.employee_service.create_employee(name="Cut Reload", team=Team.CUT)
        bag_25_id = self._bag_type_id("Bao 25kg")
        bag_50_id = self._bag_type_id("Bao 50kg")
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        tab._add_cut_bag_by_id(bag_25_id)
        tab._add_cut_bag_by_id(bag_50_id)
        self._cut_quantity_input(tab, bag_25_id).setValue(10)
        self._cut_quantity_input(tab, bag_50_id).setValue(5)
        with patch.object(MessageBox, "info"), patch.object(MessageBox, "warning"), patch.object(MessageBox, "error"):
            tab._save_current(finalize=True)
        tab._load_selected_employee()

        self.assertEqual(set(self._cut_table_bag_ids(tab)), {bag_25_id, bag_50_id})
        self.assertEqual(self._cut_quantity_input(tab, bag_25_id).value(), 10)
        self.assertEqual(self._cut_quantity_input(tab, bag_50_id).value(), 5)

    def test_cut_inactive_historical_bag_still_loads_in_selected_table(self) -> None:
        employee = self.employee_service.create_employee(name="Cut Inactive History", team=Team.CUT)
        bag_25_id = self._bag_type_id("Bao 25kg")
        selected_date = date(2026, 5, 6)
        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee.id,
                selected_date=selected_date,
                cut_work=[CutWorkInput(bag_type_id=bag_25_id, quantity=10)],
            ),
            finalize=True,
        )
        self.settings_service.set_bag_type_active(bag_25_id, False)

        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        self.assertEqual(self._cut_table_bag_ids(tab), [bag_25_id])
        self.assertEqual(self._cut_quantity_input(tab, bag_25_id).value(), 10)

    def test_cut_total_preview_updates_after_quantity_change_and_delete(self) -> None:
        self.employee_service.create_employee(name="Cut Preview", team=Team.CUT)
        bag_25_id = self._configure_bag_type("Bao 25kg", quota_quantity=25, excess_unit_price=10000)
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        tab._add_cut_bag_by_id(bag_25_id)
        self._cut_quantity_input(tab, bag_25_id).setValue(30)
        self.assertEqual(tab.total_label.text(), "50,000")
        self._cut_delete_button(tab, bag_25_id).click()
        self.assertEqual(tab.total_label.text(), "0")

    def test_cut_selected_table_payload_preserves_formula_regression(self) -> None:
        self.employee_service.create_employee(name="Cut Formula UI", team=Team.CUT)
        bag_25_id = self._configure_bag_type("Bao 25kg", quota_quantity=20, excess_unit_price=10000)
        bag_50_id = self._configure_bag_type("Bao 50kg", quota_quantity=30, excess_unit_price=20000)
        tab = AttendanceDayEntryTab(self.service)
        tab.date_edit.setDate(QDate(2026, 5, 6))
        tab.employee_table.selectRow(0)
        QApplication.processEvents()

        tab._add_cut_bag_by_id(bag_25_id)
        tab._add_cut_bag_by_id(bag_50_id)
        self._cut_quantity_input(tab, bag_25_id).setValue(10)
        self._cut_quantity_input(tab, bag_50_id).setValue(20)

        self.assertEqual(tab.total_label.text(), "100,000")
        with patch.object(MessageBox, "info"), patch.object(MessageBox, "warning"), patch.object(MessageBox, "error"):
            tab._save_current(finalize=True)
        with AttendanceSessionLocal() as session:
            record = session.query(DailyRecord).filter_by(date=date(2026, 5, 6)).one()
            self.assertEqual(record.total_amount_snapshot, 100000)

    def test_attendance_page_has_real_day_entry_tab(self) -> None:
        page = AttendancePage()
        day_tab = page.findChild(AttendanceDayEntryTab)

        self.assertIsNotNone(day_tab)
        self.assertIsNotNone(page.findChild(QDateEdit))
        self.assertIsNotNone(page.findChild(QTableWidget))
        button_texts = {button.text() for button in page.findChildren(QPushButton)}
        self.assertTrue({"Lưu nháp", "Chốt ngày", "Làm mới form"}.issubset(button_texts))

    def test_employee_signal_refreshes_day_entry_and_preserves_selected_date(self) -> None:
        page = AttendancePage()
        page.day_entry_tab.date_edit.setDate(QDate(2026, 5, 6))

        page.employee_tab._service.create_employee(name="Realtime A", team=Team.BLOW)
        page.employee_tab.employees_changed.emit()

        self.assertEqual(page.day_entry_tab.selected_date(), date(2026, 5, 6))
        names = self._day_entry_table_names(page.day_entry_tab)
        self.assertEqual(names.count("Realtime A"), 1)

        page.employee_tab.employees_changed.emit()
        names_after_second_refresh = self._day_entry_table_names(page.day_entry_tab)
        self.assertEqual(names_after_second_refresh.count("Realtime A"), 1)

    def test_switching_to_day_entry_tab_refreshes_if_signal_was_missed(self) -> None:
        page = AttendancePage()
        page.employee_tab._service.create_employee(name="Switch A", team=Team.BLOW)

        page.tabs.setCurrentWidget(page.employee_tab)
        page.tabs.setCurrentWidget(page.day_entry_tab)

        self.assertIn("Switch A", self._day_entry_table_names(page.day_entry_tab))

    def test_employee_edit_and_deactivate_are_reflected_in_day_entry(self) -> None:
        page = AttendancePage()
        employee = page.employee_tab._service.create_employee(name="Original", team=Team.BLOW)
        page.employee_tab.employees_changed.emit()
        self.assertIn("Original", self._day_entry_table_names(page.day_entry_tab))

        page.employee_tab._service.update_employee(employee.id, name="Updated", team=Team.CUT, is_active=True)
        page.employee_tab.employees_changed.emit()
        names = self._day_entry_table_names(page.day_entry_tab)
        self.assertIn("Updated", names)
        self.assertNotIn("Original", names)
        row = names.index("Updated")
        self.assertEqual(page.day_entry_tab.employee_table.item(row, 1).text(), "Tổ cắt")

        page.employee_tab._service.update_employee(employee.id, name="Updated", team=Team.CUT, is_active=False)
        page.employee_tab.employees_changed.emit()
        self.assertNotIn("Updated", self._day_entry_table_names(page.day_entry_tab))

    def _day_entry_table_names(self, day_tab: AttendanceDayEntryTab) -> list[str]:
        return [
            day_tab.employee_table.item(row, 0).text()
            for row in range(day_tab.employee_table.rowCount())
            if day_tab.employee_table.item(row, 0) is not None
        ]

    def _cut_table_bag_ids(self, tab: AttendanceDayEntryTab) -> list[int]:
        assert tab.cut_table is not None
        return [
            int(tab.cut_table.item(row, 0).data(Qt.ItemDataRole.UserRole))
            for row in range(tab.cut_table.rowCount())
            if tab.cut_table.item(row, 0) is not None
        ]

    def _cut_quantity_input(self, tab: AttendanceDayEntryTab, bag_type_id: int) -> SelectAllQuantityInput:
        assert tab.cut_table is not None
        row = tab._cut_bag_row(bag_type_id)
        assert row is not None
        quantity_input = tab.cut_table.cellWidget(row, 1)
        assert isinstance(quantity_input, SelectAllQuantityInput)
        return quantity_input

    def _cut_delete_button(self, tab: AttendanceDayEntryTab, bag_type_id: int) -> QPushButton:
        assert tab.cut_table is not None
        row = tab._cut_bag_row(bag_type_id)
        assert row is not None
        button = tab.cut_table.cellWidget(row, 2)
        assert isinstance(button, QPushButton)
        return button


if __name__ == "__main__":
    unittest.main()
