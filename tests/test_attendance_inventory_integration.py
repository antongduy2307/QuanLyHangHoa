from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import UnitMode, UnitType
from core.exceptions import ValidationError
import modules.customer.models  # noqa: F401
from modules.attendance.db import AttendanceBase
from modules.attendance.dto import AttendanceSavePayload, CutWorkInput, ExtraCutWorkInput
from modules.attendance.inventory_effect_service import (
    ATTENDANCE_DAILY_RECORD_SOURCE_TYPE,
    CUT_LOG_SOURCE_LINE_TYPE,
    EXTRA_CUT_WORK_LOG_SOURCE_LINE_TYPE,
    AttendanceInventoryEffectService,
)
from modules.attendance.models import BagType, CutLog, DailyRecord, Employee, ExtraCutWorkLog, Team
from modules.attendance.service import AttendanceDayEntryService
from modules.inventory.models import InventoryStockEffect, Product
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
import modules.orders.models  # noqa: F401
import modules.returns.models  # noqa: F401
import modules.sales.models  # noqa: F401


class _FailingInventoryEffectService:
    def reconcile_daily_record_effects(self, snapshot):
        self.snapshot = snapshot
        raise RuntimeError("inventory reconcile failed")


class _CapturingInventoryEffectService:
    def __init__(self) -> None:
        self.snapshots = []

    def reconcile_daily_record_effects(self, snapshot):
        self.snapshots.append(snapshot)
        return None


class AttendanceInventoryIntegrationTestCase(unittest.TestCase):
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
        self.service = AttendanceDayEntryService(
            session_factory=self.AttendanceSession,
            inventory_effect_service=self.effect_service,
        )
        self.bao_product_id = self._create_product("BAO-PROD", UnitMode.BAO_KG)
        self.second_bao_product_id = self._create_product("BAO-PROD-2", UnitMode.BAO_KG)
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

    def _create_employee(self, name: str, team: Team) -> int:
        with self.AttendanceSession() as session:
            employee = Employee(name=name, team=team, is_active=True)
            session.add(employee)
            session.commit()
            return int(employee.id)

    def _create_bag_type(
        self,
        name: str,
        *,
        product_id: int | None,
        quota_quantity: Decimal | int = Decimal("10"),
        excess_unit_price: Decimal | int = Decimal("3500"),
    ) -> int:
        with self.AttendanceSession() as session:
            bag_type = BagType(
                name=name,
                unit_price=0,
                quota_quantity=Decimal(str(quota_quantity)),
                excess_unit_price=Decimal(str(excess_unit_price)),
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

    def _quantity(self, product_id: int, unit_type: UnitType) -> Decimal:
        return self.inventory_service.get_available_quantity(product_id, unit_type)

    def _effects(self) -> list[InventoryStockEffect]:
        with self.MainSession() as session:
            return list(session.scalars(select(InventoryStockEffect).order_by(InventoryStockEffect.id.asc())).all())

    def test_draft_cut_save_does_not_update_stock(self) -> None:
        employee_id = self._create_employee("Cut Draft", Team.CUT)
        bag_id = self._create_bag_type("Cut draft bag", product_id=self.bao_product_id)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_id,
                selected_date=date(2026, 5, 13),
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("5"))],
            ),
            finalize=False,
        )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self._effects(), [])

    def test_draft_vk_save_does_not_update_stock(self) -> None:
        employee_id = self._create_employee("Blow Draft", Team.BLOW)
        bag_id = self._create_bag_type("VK draft bag", product_id=self.bich_product_id)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_id,
                selected_date=date(2026, 5, 13),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=Decimal("4"))],
            ),
            finalize=False,
        )

        self.assertEqual(self._quantity(self.bich_product_id, UnitType.BICH), Decimal("0"))
        self.assertEqual(self._effects(), [])

    def test_done_cut_save_updates_stock(self) -> None:
        employee_id = self._create_employee("Cut Done", Team.CUT)
        bag_id = self._create_bag_type("Cut done bag", product_id=self.bao_product_id)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_id,
                selected_date=date(2026, 5, 13),
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("5"))],
            ),
            finalize=True,
        )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("5"))

    def test_done_vk_save_updates_stock(self) -> None:
        employee_id = self._create_employee("Blow Done", Team.BLOW)
        bag_id = self._create_bag_type("VK done bag", product_id=self.bich_product_id)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_id,
                selected_date=date(2026, 5, 13),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=Decimal("4"))],
            ),
            finalize=True,
        )

        self.assertEqual(self._quantity(self.bich_product_id, UnitType.BICH), Decimal("4"))

    def test_done_cut_and_vk_same_product_aggregate_correctly(self) -> None:
        cut_employee_id = self._create_employee("Cut Same Product", Team.CUT)
        blow_employee_id = self._create_employee("Blow Same Product", Team.BLOW)
        cut_bag_id = self._create_bag_type("Cut same product bag", product_id=self.bao_product_id)
        vk_bag_id = self._create_bag_type("VK same product bag", product_id=self.bao_product_id)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=cut_employee_id,
                selected_date=date(2026, 5, 13),
                cut_work=[CutWorkInput(bag_type_id=cut_bag_id, quantity=Decimal("2"))],
            ),
            finalize=True,
        )
        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=blow_employee_id,
                selected_date=date(2026, 5, 13),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=vk_bag_id, quantity=Decimal("3"))],
            ),
            finalize=True,
        )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("5"))

    def test_multiple_products_update_correct_balances(self) -> None:
        cut_employee_id = self._create_employee("Cut Multi", Team.CUT)
        blow_employee_id = self._create_employee("Blow Multi", Team.BLOW)
        first_bag_id = self._create_bag_type("First product", product_id=self.bao_product_id)
        second_bag_id = self._create_bag_type("Second product", product_id=self.second_bao_product_id)
        bich_bag_id = self._create_bag_type("Bich product", product_id=self.bich_product_id)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=cut_employee_id,
                selected_date=date(2026, 5, 13),
                cut_work=[
                    CutWorkInput(bag_type_id=first_bag_id, quantity=Decimal("2")),
                    CutWorkInput(bag_type_id=second_bag_id, quantity=Decimal("3")),
                ],
            ),
            finalize=True,
        )
        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=blow_employee_id,
                selected_date=date(2026, 5, 13),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bich_bag_id, quantity=Decimal("4"))],
            ),
            finalize=True,
        )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("2"))
        self.assertEqual(self._quantity(self.second_bao_product_id, UnitType.BAO), Decimal("3"))
        self.assertEqual(self._quantity(self.bich_product_id, UnitType.BICH), Decimal("4"))

    def test_decimal_cut_quantity_updates_stock_exactly(self) -> None:
        employee_id = self._create_employee("Cut Decimal", Team.CUT)
        bag_id = self._create_bag_type("Cut decimal bag", product_id=self.bao_product_id)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_id,
                selected_date=date(2026, 5, 13),
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("10.5"))],
            ),
            finalize=True,
        )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("10.5"))

    def test_decimal_vk_quantity_updates_stock_exactly(self) -> None:
        employee_id = self._create_employee("VK Decimal", Team.BLOW)
        bag_id = self._create_bag_type("VK decimal bag", product_id=self.bich_product_id)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_id,
                selected_date=date(2026, 5, 13),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=Decimal("4.25"))],
            ),
            finalize=True,
        )

        self.assertEqual(self._quantity(self.bich_product_id, UnitType.BICH), Decimal("4.25"))

    def test_edit_done_quantity_upward_and_downward_updates_stock_to_latest_only(self) -> None:
        employee_id = self._create_employee("Cut Edit", Team.CUT)
        bag_id = self._create_bag_type("Cut edit bag", product_id=self.bao_product_id)
        selected_date = date(2026, 5, 13)

        for quantity in (Decimal("5"), Decimal("8"), Decimal("3")):
            self.service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee_id,
                    selected_date=selected_date,
                    cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=quantity)],
                ),
                finalize=True,
            )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("3"))
        self.assertEqual(len(self._effects()), 1)

    def test_resave_same_done_does_not_double_count(self) -> None:
        employee_id = self._create_employee("Cut Idempotent", Team.CUT)
        bag_id = self._create_bag_type("Cut idempotent bag", product_id=self.bao_product_id)
        payload = AttendanceSavePayload(
            employee_id=employee_id,
            selected_date=date(2026, 5, 13),
            cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("5"))],
        )

        self.service.save_attendance(payload, finalize=True)
        self.service.save_attendance(payload, finalize=True)

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("5"))
        self.assertEqual(len(self._effects()), 1)

    def test_remove_cut_line_rolls_back_stock(self) -> None:
        employee_id = self._create_employee("Cut Remove", Team.CUT)
        bag_id = self._create_bag_type("Cut remove bag", product_id=self.bao_product_id)
        selected_date = date(2026, 5, 13)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_id,
                selected_date=selected_date,
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("5"))],
            ),
            finalize=True,
        )
        self.service.save_attendance(
            AttendanceSavePayload(employee_id=employee_id, selected_date=selected_date, cut_work=[]),
            finalize=True,
        )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self._effects(), [])

    def test_remove_vk_line_rolls_back_stock(self) -> None:
        employee_id = self._create_employee("VK Remove", Team.BLOW)
        bag_id = self._create_bag_type("VK remove bag", product_id=self.bich_product_id)
        selected_date = date(2026, 5, 13)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_id,
                selected_date=selected_date,
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=bag_id, quantity=Decimal("4"))],
            ),
            finalize=True,
        )
        self.service.save_attendance(
            AttendanceSavePayload(employee_id=employee_id, selected_date=selected_date, extra_cut_work=[]),
            finalize=True,
        )

        self.assertEqual(self._quantity(self.bich_product_id, UnitType.BICH), Decimal("0"))
        self.assertEqual(self._effects(), [])

    def test_done_to_draft_rolls_back_stock(self) -> None:
        employee_id = self._create_employee("Cut Done Draft", Team.CUT)
        bag_id = self._create_bag_type("Cut done draft bag", product_id=self.bao_product_id)
        selected_date = date(2026, 5, 13)
        payload = AttendanceSavePayload(
            employee_id=employee_id,
            selected_date=selected_date,
            cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("5"))],
        )

        self.service.save_attendance(payload, finalize=True)
        self.service.save_attendance(payload, finalize=False)

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self._effects(), [])

    def test_done_to_absent_rolls_back_stock(self) -> None:
        employee_id = self._create_employee("Cut Done Absent", Team.CUT)
        bag_id = self._create_bag_type("Cut done absent bag", product_id=self.bao_product_id)
        selected_date = date(2026, 5, 13)

        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_id,
                selected_date=selected_date,
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("5"))],
            ),
            finalize=True,
        )
        self.service.save_attendance(
            AttendanceSavePayload(employee_id=employee_id, selected_date=selected_date, is_absent=True),
            finalize=True,
        )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self._effects(), [])

    def test_missing_source_product_id_on_done_raises_clear_error(self) -> None:
        employee_id = self._create_employee("Cut Missing Link", Team.CUT)
        bag_id = self._create_bag_type("Cut missing link bag", product_id=None)

        with self.assertRaisesRegex(ValidationError, "chưa liên kết hàng hóa"):
            self.service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee_id,
                    selected_date=date(2026, 5, 13),
                    cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("5"))],
                ),
                finalize=True,
            )

    def test_missing_product_id_on_done_raises_clear_error(self) -> None:
        employee_id = self._create_employee("Cut Missing Product", Team.CUT)
        bag_id = self._create_bag_type("Cut missing product bag", product_id=9999)

        with self.assertRaisesRegex(ValidationError, "Không tìm thấy hàng hóa"):
            self.service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee_id,
                    selected_date=date(2026, 5, 13),
                    cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("5"))],
                ),
                finalize=True,
            )

    def test_old_done_record_without_effect_rows_creates_effects_after_explicit_save(self) -> None:
        employee_id = self._create_employee("Old Done", Team.CUT)
        bag_id = self._create_bag_type("Old done bag", product_id=self.bao_product_id)
        selected_date = date(2026, 5, 13)
        with self.AttendanceSession() as session:
            period = self.service.ensure_period_for_date(selected_date)
            record = DailyRecord(
                employee_id=employee_id,
                date=selected_date,
                period_id=period.id,
                status="done",
                is_absent=False,
                total_amount_snapshot=0,
            )
            session.add(record)
            session.flush()
            session.add(
                CutLog(
                    daily_record_id=record.id,
                    bag_type_id=bag_id,
                    quantity=Decimal("5"),
                    unit_price_snapshot=0,
                    quota_quantity_snapshot=Decimal("10"),
                    excess_unit_price_snapshot=Decimal("3500"),
                    amount_snapshot=0,
                )
            )
            session.commit()

        self.assertEqual(self._effects(), [])
        self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_id,
                selected_date=selected_date,
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("5"))],
            ),
            finalize=True,
        )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("5"))
        self.assertEqual(len(self._effects()), 1)

    def test_inventory_reconciliation_failure_propagates_to_caller(self) -> None:
        failing_service = _FailingInventoryEffectService()
        service = AttendanceDayEntryService(
            session_factory=self.AttendanceSession,
            inventory_effect_service=failing_service,
        )
        employee_id = self._create_employee("Cut Failure", Team.CUT)
        bag_id = self._create_bag_type("Cut failure bag", product_id=self.bao_product_id)

        with self.assertRaisesRegex(RuntimeError, "inventory reconcile failed"):
            service.save_attendance(
                AttendanceSavePayload(
                    employee_id=employee_id,
                    selected_date=date(2026, 5, 13),
                    cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("5"))],
                ),
                finalize=True,
            )

    def test_fake_effect_service_injection_receives_flushed_source_line_ids(self) -> None:
        fake_service = _CapturingInventoryEffectService()
        service = AttendanceDayEntryService(
            session_factory=self.AttendanceSession,
            inventory_effect_service=fake_service,
        )
        cut_employee_id = self._create_employee("Cut Snapshot", Team.CUT)
        blow_employee_id = self._create_employee("Blow Snapshot", Team.BLOW)
        cut_bag_id = self._create_bag_type("Cut snapshot bag", product_id=self.bao_product_id)
        vk_bag_id = self._create_bag_type("VK snapshot bag", product_id=self.bich_product_id)

        service.save_attendance(
            AttendanceSavePayload(
                employee_id=cut_employee_id,
                selected_date=date(2026, 5, 13),
                cut_work=[CutWorkInput(bag_type_id=cut_bag_id, quantity=Decimal("5"))],
            ),
            finalize=True,
        )
        service.save_attendance(
            AttendanceSavePayload(
                employee_id=blow_employee_id,
                selected_date=date(2026, 5, 13),
                extra_cut_work=[ExtraCutWorkInput(bag_type_id=vk_bag_id, quantity=Decimal("4"))],
            ),
            finalize=True,
        )

        cut_snapshot = fake_service.snapshots[0]
        vk_snapshot = fake_service.snapshots[1]
        self.assertIsNotNone(cut_snapshot.cut_lines[0].source_line_id)
        self.assertGreater(cut_snapshot.cut_lines[0].source_line_id, 0)
        self.assertEqual(cut_snapshot.cut_lines[0].source_line_type, CUT_LOG_SOURCE_LINE_TYPE)
        self.assertIsNotNone(vk_snapshot.extra_cut_lines[0].source_line_id)
        self.assertGreater(vk_snapshot.extra_cut_lines[0].source_line_id, 0)
        self.assertEqual(vk_snapshot.extra_cut_lines[0].source_line_type, EXTRA_CUT_WORK_LOG_SOURCE_LINE_TYPE)

    def test_effect_rows_contain_attendance_source_metadata(self) -> None:
        employee_id = self._create_employee("Cut Effect Metadata", Team.CUT)
        bag_id = self._create_bag_type("Cut effect metadata bag", product_id=self.bao_product_id)

        result = self.service.save_attendance(
            AttendanceSavePayload(
                employee_id=employee_id,
                selected_date=date(2026, 5, 13),
                cut_work=[CutWorkInput(bag_type_id=bag_id, quantity=Decimal("5"))],
            ),
            finalize=True,
        )

        effects = self._effects()
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].source_type, ATTENDANCE_DAILY_RECORD_SOURCE_TYPE)
        self.assertEqual(effects[0].source_id, result.record_id)
        self.assertEqual(effects[0].source_line_type, CUT_LOG_SOURCE_LINE_TYPE)
        self.assertEqual(effects[0].attendance_bag_type_id, bag_id)
        self.assertEqual(effects[0].product_id, self.bao_product_id)
        self.assertEqual(effects[0].quantity_delta, Decimal("5"))


if __name__ == "__main__":
    unittest.main()
