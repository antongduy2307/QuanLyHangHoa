from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import UnitMode, UnitType
from core.exceptions import NotFoundError, ValidationError
import modules.customer.models  # noqa: F401
from modules.attendance.db import AttendanceBase
from modules.attendance.inventory_diagnostic_service import (
    AttendanceInventoryDiagnosticService,
    AttendanceInventoryIssueType,
)
from modules.attendance.inventory_effect_service import (
    ATTENDANCE_DAILY_RECORD_SOURCE_TYPE,
    CUT_LOG_SOURCE_LINE_TYPE,
    EXTRA_CUT_WORK_LOG_SOURCE_LINE_TYPE,
    AttendanceInventoryEffectService,
)
from modules.attendance.models import BagType, CutLog, DailyRecord, DailyRecordStatus, Employee, ExtraCutWorkLog, Period, Team
from modules.inventory.models import InventoryStockEffect, Product
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
import modules.orders.models  # noqa: F401
import modules.returns.models  # noqa: F401
import modules.sales.models  # noqa: F401


class AttendanceInventoryDiagnosticsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.main_engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.main_engine)
        self.MainSession = sessionmaker(bind=self.main_engine, expire_on_commit=False, autoflush=False)
        self.main_repository = InventoryRepository(self.MainSession)
        self.inventory_service = InventoryService(self.main_repository)

        self.attendance_engine = create_engine("sqlite+pysqlite:///:memory:")
        AttendanceBase.metadata.create_all(self.attendance_engine)
        self.AttendanceSession = sessionmaker(bind=self.attendance_engine, expire_on_commit=False, autoflush=False)

        self.effect_service = AttendanceInventoryEffectService(self.MainSession)
        self.diagnostic_service = AttendanceInventoryDiagnosticService(
            attendance_session_factory=self.AttendanceSession,
            main_session_factory=self.MainSession,
            effect_service=self.effect_service,
        )
        self.bao_product_id = self._create_product("BAO-PROD", UnitMode.BAO_KG)
        self.second_product_id = self._create_product("BAO-PROD-2", UnitMode.BAO_KG)
        self.bich_product_id = self._create_product("BICH-PROD", UnitMode.BICH)

    def tearDown(self) -> None:
        self.main_repository.session.close()
        self.main_engine.dispose()
        self.attendance_engine.dispose()

    def _create_product(self, code: str, unit_mode: UnitMode) -> int:
        with self.MainSession() as session:
            product = Product(product_code_base=code, product_name=code, unit_mode=unit_mode)
            session.add(product)
            session.commit()
            return int(product.id)

    def _create_bag_type(self, name: str, product_id: int | None) -> int:
        with self.AttendanceSession() as session:
            bag_type = BagType(
                name=name,
                unit_price=0,
                quota_quantity=Decimal("10"),
                excess_unit_price=Decimal("3500"),
                is_active=True,
                is_product_linked=True,
                source_product_id=product_id,
                source_product_name_snapshot=name,
                is_excluded_from_attendance=False,
                is_legacy=False,
            )
            session.add(bag_type)
            session.commit()
            return int(bag_type.id)

    def _create_employee(self, name: str, team: Team) -> int:
        with self.AttendanceSession() as session:
            employee = Employee(name=name, team=team, is_active=True)
            session.add(employee)
            session.commit()
            return int(employee.id)

    def _create_period(self, selected_date: date) -> int:
        with self.AttendanceSession() as session:
            existing = session.scalar(
                select(Period).where(Period.start_date == selected_date, Period.end_date == selected_date)
            )
            if existing is not None:
                return int(existing.id)
            period = Period(start_date=selected_date, end_date=selected_date)
            session.add(period)
            session.commit()
            return int(period.id)

    def _create_record(
        self,
        *,
        team: Team = Team.CUT,
        status: DailyRecordStatus = DailyRecordStatus.DONE,
        is_absent: bool = False,
        cut_lines: list[tuple[int, Decimal]] | None = None,
        extra_cut_lines: list[tuple[int, Decimal]] | None = None,
    ) -> int:
        employee_id = self._create_employee(f"Employee {team.value} {id(cut_lines)} {id(extra_cut_lines)}", team)
        selected_date = date(2026, 5, 13)
        period_id = self._create_period(selected_date)
        with self.AttendanceSession() as session:
            record = DailyRecord(
                employee_id=employee_id,
                date=selected_date,
                period_id=period_id,
                is_absent=is_absent,
                status=status,
                total_amount_snapshot=0,
            )
            session.add(record)
            session.flush()
            for bag_type_id, quantity in cut_lines or []:
                session.add(
                    CutLog(
                        daily_record_id=record.id,
                        bag_type_id=bag_type_id,
                        quantity=quantity,
                        unit_price_snapshot=0,
                        quota_quantity_snapshot=Decimal("10"),
                        excess_unit_price_snapshot=Decimal("3500"),
                        amount_snapshot=0,
                    )
                )
            for bag_type_id, quantity in extra_cut_lines or []:
                session.add(
                    ExtraCutWorkLog(
                        daily_record_id=record.id,
                        bag_type_id=bag_type_id,
                        quantity=quantity,
                        excess_unit_price_snapshot=Decimal("3500"),
                        amount_snapshot=0,
                    )
                )
            session.commit()
            return int(record.id)

    def _effect_count(self) -> int:
        with self.MainSession() as session:
            return int(session.scalar(select(InventoryStockEffect.id).limit(1)) is not None)

    def _effects_for(self, record_id: int) -> list[InventoryStockEffect]:
        with self.MainSession() as session:
            return list(
                session.scalars(
                    select(InventoryStockEffect)
                    .where(
                        InventoryStockEffect.source_type == ATTENDANCE_DAILY_RECORD_SOURCE_TYPE,
                        InventoryStockEffect.source_id == record_id,
                    )
                    .order_by(InventoryStockEffect.id.asc())
                ).all()
            )

    def _quantity(self, product_id: int, unit_type: UnitType) -> Decimal:
        return self.inventory_service.get_available_quantity(product_id, unit_type)

    def _insert_effect(
        self,
        *,
        record_id: int,
        product_id: int,
        quantity: Decimal,
        unit_type: UnitType = UnitType.BAO,
        line_type: str = CUT_LOG_SOURCE_LINE_TYPE,
        line_id: int = 500,
        apply_stock: bool = False,
    ) -> None:
        with self.MainSession() as session:
            with session.begin():
                if apply_stock:
                    inventory_service = InventoryService(InventoryRepository(self.MainSession))
                    inventory_service.use_session(session)
                    inventory_service.increase_stock(product_id, quantity, unit_type)
                session.add(
                    InventoryStockEffect(
                        source_type=ATTENDANCE_DAILY_RECORD_SOURCE_TYPE,
                        source_id=record_id,
                        source_line_type=line_type,
                        source_line_id=line_id,
                        attendance_employee_id=1,
                        attendance_work_date=date(2026, 5, 13),
                        attendance_bag_type_id=1,
                        product_id=product_id,
                        quantity_delta=quantity,
                        unit_type=unit_type,
                        movement_datetime=datetime(2026, 5, 13),
                        note="test",
                    )
                )

    def _issue_types(self) -> list[AttendanceInventoryIssueType]:
        return [issue.issue_type for issue in self.diagnostic_service.list_issues()]

    def test_done_record_with_correct_effects_produces_no_issues(self) -> None:
        bag_id = self._create_bag_type("Correct bag", self.bao_product_id)
        record_id = self._create_record(cut_lines=[(bag_id, Decimal("5"))])
        self.diagnostic_service.reconcile_daily_record(record_id)

        self.assertEqual(self.diagnostic_service.list_issues(), [])

    def test_done_record_with_cut_vk_lines_and_no_effects_reports_missing(self) -> None:
        cut_bag_id = self._create_bag_type("Missing cut", self.bao_product_id)
        vk_bag_id = self._create_bag_type("Missing vk", self.bich_product_id)
        self._create_record(
            team=Team.BLOW,
            extra_cut_lines=[(vk_bag_id, Decimal("4"))],
        )
        self._create_record(cut_lines=[(cut_bag_id, Decimal("5"))])

        self.assertIn(AttendanceInventoryIssueType.MISSING_EFFECTS_FOR_DONE_RECORD, self._issue_types())

    def test_wrong_quantity_effect_reports_quantity_mismatch(self) -> None:
        bag_id = self._create_bag_type("Wrong quantity", self.bao_product_id)
        record_id = self._create_record(cut_lines=[(bag_id, Decimal("5"))])
        self._insert_effect(record_id=record_id, product_id=self.bao_product_id, quantity=Decimal("4"))

        issues = self.diagnostic_service.list_issues()

        self.assertEqual(issues[0].issue_type, AttendanceInventoryIssueType.QUANTITY_MISMATCH)

    def test_wrong_product_effect_reports_product_mismatch(self) -> None:
        bag_id = self._create_bag_type("Wrong product", self.bao_product_id)
        record_id = self._create_record(cut_lines=[(bag_id, Decimal("5"))])
        self._insert_effect(record_id=record_id, product_id=self.second_product_id, quantity=Decimal("5"))

        issues = self.diagnostic_service.list_issues()

        self.assertEqual(issues[0].issue_type, AttendanceInventoryIssueType.PRODUCT_MISMATCH)

    def test_draft_record_with_stale_effect_reports_stale(self) -> None:
        bag_id = self._create_bag_type("Draft stale", self.bao_product_id)
        record_id = self._create_record(status=DailyRecordStatus.DRAFT, cut_lines=[(bag_id, Decimal("5"))])
        self._insert_effect(record_id=record_id, product_id=self.bao_product_id, quantity=Decimal("5"))

        self.assertIn(AttendanceInventoryIssueType.STALE_EFFECTS_FOR_DRAFT_OR_ABSENT_RECORD, self._issue_types())

    def test_absent_record_with_stale_effect_reports_stale(self) -> None:
        record_id = self._create_record(status=DailyRecordStatus.DONE, is_absent=True)
        self._insert_effect(record_id=record_id, product_id=self.bao_product_id, quantity=Decimal("5"))

        self.assertIn(AttendanceInventoryIssueType.STALE_EFFECTS_FOR_DRAFT_OR_ABSENT_RECORD, self._issue_types())

    def test_missing_daily_record_source_reports_stale_missing_source(self) -> None:
        self._insert_effect(record_id=999, product_id=self.bao_product_id, quantity=Decimal("5"))

        self.assertIn(AttendanceInventoryIssueType.STALE_EFFECTS_FOR_MISSING_DAILY_RECORD, self._issue_types())

    def test_reconcile_daily_record_fixes_missing_effects_for_done(self) -> None:
        bag_id = self._create_bag_type("Fix missing", self.bao_product_id)
        record_id = self._create_record(cut_lines=[(bag_id, Decimal("5"))])

        result = self.diagnostic_service.reconcile_daily_record(record_id)

        self.assertEqual(result.applied_count, 1)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("5"))
        self.assertEqual(self.diagnostic_service.list_issues(), [])

    def test_reconcile_daily_record_fixes_quantity_mismatch_for_edited_done(self) -> None:
        bag_id = self._create_bag_type("Fix mismatch", self.bao_product_id)
        record_id = self._create_record(cut_lines=[(bag_id, Decimal("8"))])
        self._insert_effect(record_id=record_id, product_id=self.bao_product_id, quantity=Decimal("5"), apply_stock=True)

        result = self.diagnostic_service.reconcile_daily_record(record_id)

        self.assertEqual(result.rolled_back_count, 1)
        self.assertEqual(result.applied_count, 1)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("8"))
        self.assertEqual(self.diagnostic_service.list_issues(), [])

    def test_reconcile_daily_record_rolls_back_effects_for_draft(self) -> None:
        bag_id = self._create_bag_type("Fix draft", self.bao_product_id)
        record_id = self._create_record(status=DailyRecordStatus.DRAFT, cut_lines=[(bag_id, Decimal("5"))])
        self._insert_effect(record_id=record_id, product_id=self.bao_product_id, quantity=Decimal("5"), apply_stock=True)

        result = self.diagnostic_service.reconcile_daily_record(record_id)

        self.assertEqual(result.rolled_back_count, 1)
        self.assertEqual(result.applied_count, 0)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self.diagnostic_service.list_issues(), [])

    def test_reconcile_daily_record_rolls_back_effects_for_absent(self) -> None:
        record_id = self._create_record(status=DailyRecordStatus.DONE, is_absent=True)
        self._insert_effect(record_id=record_id, product_id=self.bao_product_id, quantity=Decimal("5"), apply_stock=True)

        result = self.diagnostic_service.reconcile_daily_record(record_id)

        self.assertEqual(result.rolled_back_count, 1)
        self.assertEqual(result.applied_count, 0)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self.diagnostic_service.list_issues(), [])

    def test_decimal_quantities_compare_exactly(self) -> None:
        bag_id = self._create_bag_type("Decimal diagnostics", self.bao_product_id)
        record_id = self._create_record(cut_lines=[(bag_id, Decimal("10.5"))])
        self._insert_effect(record_id=record_id, product_id=self.bao_product_id, quantity=Decimal("10.500"))

        self.assertEqual(self.diagnostic_service.list_issues(), [])

    def test_missing_product_link_reports_issue_and_reconcile_raises(self) -> None:
        bag_id = self._create_bag_type("Missing link diagnostics", None)
        record_id = self._create_record(cut_lines=[(bag_id, Decimal("5"))])

        issues = self.diagnostic_service.list_issues()

        self.assertEqual(issues[0].issue_type, AttendanceInventoryIssueType.MISSING_PRODUCT_LINK)
        with self.assertRaisesRegex(ValidationError, "chưa liên kết hàng hóa"):
            self.diagnostic_service.reconcile_daily_record(record_id)

    def test_missing_main_product_reports_issue_and_reconcile_raises(self) -> None:
        bag_id = self._create_bag_type("Missing main product diagnostics", 9999)
        record_id = self._create_record(cut_lines=[(bag_id, Decimal("5"))])

        issues = self.diagnostic_service.list_issues()

        self.assertEqual(issues[0].issue_type, AttendanceInventoryIssueType.MISSING_MAIN_PRODUCT)
        with self.assertRaisesRegex(ValidationError, "Không tìm thấy hàng hóa"):
            self.diagnostic_service.reconcile_daily_record(record_id)

    def test_diagnostic_scan_does_not_auto_backfill_or_mutate_stock(self) -> None:
        bag_id = self._create_bag_type("Read only diagnostics", self.bao_product_id)
        self._create_record(cut_lines=[(bag_id, Decimal("5"))])

        issues = self.diagnostic_service.list_issues()

        self.assertEqual(issues[0].issue_type, AttendanceInventoryIssueType.MISSING_EFFECTS_FOR_DONE_RECORD)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self._effects_for_any_source(), [])

    def test_build_snapshot_for_daily_record_includes_cut_and_vk_lines(self) -> None:
        cut_bag_id = self._create_bag_type("Snapshot cut", self.bao_product_id)
        vk_bag_id = self._create_bag_type("Snapshot vk", self.bich_product_id)
        record_id = self._create_record(
            team=Team.BLOW,
            extra_cut_lines=[(vk_bag_id, Decimal("4.25"))],
        )
        cut_record_id = self._create_record(cut_lines=[(cut_bag_id, Decimal("10.5"))])

        vk_snapshot = self.diagnostic_service.build_snapshot_for_daily_record(record_id)
        cut_snapshot = self.diagnostic_service.build_snapshot_for_daily_record(cut_record_id)

        self.assertEqual(vk_snapshot.extra_cut_lines[0].product_id, self.bich_product_id)
        self.assertEqual(vk_snapshot.extra_cut_lines[0].quantity, Decimal("4.250"))
        self.assertEqual(cut_snapshot.cut_lines[0].product_id, self.bao_product_id)
        self.assertEqual(cut_snapshot.cut_lines[0].quantity, Decimal("10.500"))

    def test_reconcile_missing_daily_record_raises_without_cleanup(self) -> None:
        self._insert_effect(record_id=999, product_id=self.bao_product_id, quantity=Decimal("5"))

        with self.assertRaises(NotFoundError):
            self.diagnostic_service.reconcile_daily_record(999)

        self.assertEqual(len(self._effects_for(999)), 1)

    def _effects_for_any_source(self) -> list[InventoryStockEffect]:
        with self.MainSession() as session:
            return list(session.scalars(select(InventoryStockEffect)).all())


if __name__ == "__main__":
    unittest.main()
