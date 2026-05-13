from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import UnitMode, UnitType
from core.exceptions import ValidationError
import modules.customer.models  # noqa: F401
from modules.attendance.inventory_effect_service import (
    ATTENDANCE_DAILY_RECORD_SOURCE_TYPE,
    CUT_LOG_SOURCE_LINE_TYPE,
    EXTRA_CUT_WORK_LOG_SOURCE_LINE_TYPE,
    AttendanceInventoryEffectLine,
    AttendanceInventoryEffectService,
    AttendanceInventoryEffectSnapshot,
)
from modules.attendance.models import DailyRecordStatus
from modules.inventory.models import InventoryStockEffect, Product
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
import modules.orders.models  # noqa: F401
import modules.returns.models  # noqa: F401
import modules.sales.models  # noqa: F401


_DEFAULT_PRODUCT = object()


class AttendanceInventoryEffectServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.repository = InventoryRepository(self.Session)
        self.inventory_service = InventoryService(self.repository)
        self.effect_service = AttendanceInventoryEffectService(self.Session)
        self.bao_product_id = self._create_product("BAO-1", UnitMode.BAO_KG)
        self.bich_product_id = self._create_product("BICH-1", UnitMode.BICH)
        self.repository.session.commit()

    def tearDown(self) -> None:
        self.repository.session.close()
        self.engine.dispose()

    def _create_product(self, code: str, unit_mode: UnitMode) -> int:
        product = Product(product_code_base=code, product_name=code, unit_mode=unit_mode)
        self.repository.session.add(product)
        self.repository.session.flush()
        return product.id

    def _snapshot(
        self,
        *,
        status: DailyRecordStatus | str = DailyRecordStatus.DONE,
        is_absent: bool = False,
        daily_record_id: int = 100,
        cut_lines: list[AttendanceInventoryEffectLine] | None = None,
        extra_cut_lines: list[AttendanceInventoryEffectLine] | None = None,
    ) -> AttendanceInventoryEffectSnapshot:
        return AttendanceInventoryEffectSnapshot(
            daily_record_id=daily_record_id,
            employee_id=5,
            work_date=date(2026, 5, 13),
            status=status,
            is_absent=is_absent,
            cut_lines=tuple(cut_lines or []),
            extra_cut_lines=tuple(extra_cut_lines or []),
        )

    def _cut_line(
        self,
        *,
        product_id: int | None | object = _DEFAULT_PRODUCT,
        quantity: Decimal | int | str = Decimal("1"),
        line_id: int | None = 10,
        bag_type_id: int = 20,
    ) -> AttendanceInventoryEffectLine:
        return AttendanceInventoryEffectLine(
            source_line_type=CUT_LOG_SOURCE_LINE_TYPE,
            source_line_id=line_id,
            attendance_bag_type_id=bag_type_id,
            product_id=self.bao_product_id if product_id is _DEFAULT_PRODUCT else product_id,
            quantity=quantity,
        )

    def _vk_line(
        self,
        *,
        product_id: int | None | object = _DEFAULT_PRODUCT,
        quantity: Decimal | int | str = Decimal("1"),
        line_id: int | None = 30,
        bag_type_id: int = 40,
    ) -> AttendanceInventoryEffectLine:
        return AttendanceInventoryEffectLine(
            source_line_type=EXTRA_CUT_WORK_LOG_SOURCE_LINE_TYPE,
            source_line_id=line_id,
            attendance_bag_type_id=bag_type_id,
            product_id=self.bich_product_id if product_id is _DEFAULT_PRODUCT else product_id,
            quantity=quantity,
        )

    def _quantity(self, product_id: int, unit_type: UnitType) -> Decimal:
        return self.inventory_service.get_available_quantity(product_id, unit_type)

    def _effects(self) -> list[InventoryStockEffect]:
        return list(self.repository.session.scalars(select(InventoryStockEffect).order_by(InventoryStockEffect.id.asc())))

    def test_draft_snapshot_does_not_update_inventory(self) -> None:
        result = self.effect_service.reconcile_daily_record_effects(
            self._snapshot(status=DailyRecordStatus.DRAFT, cut_lines=[self._cut_line(quantity=Decimal("5"))])
        )

        self.assertEqual(result.applied_count, 0)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self._effects(), [])

    def test_done_cut_snapshot_increases_product_stock(self) -> None:
        result = self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("5"))])
        )

        self.assertEqual(result.applied_count, 1)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("5"))

    def test_done_vk_snapshot_increases_product_stock(self) -> None:
        result = self.effect_service.reconcile_daily_record_effects(
            self._snapshot(extra_cut_lines=[self._vk_line(quantity=Decimal("4"))])
        )

        self.assertEqual(result.applied_count, 1)
        self.assertEqual(self._quantity(self.bich_product_id, UnitType.BICH), Decimal("4"))

    def test_cut_and_vk_same_product_aggregate_correctly(self) -> None:
        result = self.effect_service.reconcile_daily_record_effects(
            self._snapshot(
                cut_lines=[self._cut_line(product_id=self.bao_product_id, quantity=Decimal("2"), line_id=1)],
                extra_cut_lines=[self._vk_line(product_id=self.bao_product_id, quantity=Decimal("3"), line_id=2)],
            )
        )

        self.assertEqual(result.applied_count, 2)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("5"))
        self.assertEqual(result.product_deltas[0].quantity_delta, Decimal("5"))

    def test_multiple_products_update_correct_balances(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(
                cut_lines=[self._cut_line(product_id=self.bao_product_id, quantity=Decimal("2"))],
                extra_cut_lines=[self._vk_line(product_id=self.bich_product_id, quantity=Decimal("7"))],
            )
        )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("2"))
        self.assertEqual(self._quantity(self.bich_product_id, UnitType.BICH), Decimal("7"))

    def test_decimal_quantity_applies_exactly(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("10.5"))])
        )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("10.5"))

    def test_reconcile_same_done_snapshot_twice_is_idempotent(self) -> None:
        snapshot = self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("5"))])

        self.effect_service.reconcile_daily_record_effects(snapshot)
        result = self.effect_service.reconcile_daily_record_effects(snapshot)

        self.assertEqual(result.rolled_back_count, 1)
        self.assertEqual(result.applied_count, 1)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("5"))
        self.assertEqual(len(self._effects()), 1)

    def test_edit_done_quantity_upward_and_downward_uses_latest_quantity_only(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("5"))])
        )
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("8"))])
        )
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("8"))

        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("3"))])
        )
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("3"))

    def test_edit_done_with_different_source_line_ids_still_reconciles_by_daily_record_source(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("5"), line_id=10)])
        )

        result = self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("8"), line_id=99)])
        )

        self.assertEqual(result.rolled_back_count, 1)
        self.assertEqual(result.applied_count, 1)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("8"))
        effects = self._effects()
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].source_line_id, 99)

    def test_remove_line_rolls_back_old_line(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("5"))])
        )

        self.effect_service.reconcile_daily_record_effects(self._snapshot(cut_lines=[]))

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self._effects(), [])

    def test_done_to_draft_rolls_back_all_old_effects(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("5"))])
        )

        result = self.effect_service.reconcile_daily_record_effects(self._snapshot(status=DailyRecordStatus.DRAFT))

        self.assertEqual(result.rolled_back_count, 1)
        self.assertEqual(result.applied_count, 0)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))

    def test_done_to_absent_rolls_back_all_old_effects(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("5"))])
        )

        result = self.effect_service.reconcile_daily_record_effects(self._snapshot(is_absent=True))

        self.assertEqual(result.rolled_back_count, 1)
        self.assertEqual(result.applied_count, 0)
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))

    def test_missing_product_id_raises_clear_error_and_preserves_existing_effect(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("5"))])
        )

        with self.assertRaisesRegex(ValidationError, "chưa liên kết hàng hóa"):
            self.effect_service.reconcile_daily_record_effects(
                self._snapshot(cut_lines=[self._cut_line(product_id=None, quantity=Decimal("9"))])
            )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("5"))
        self.assertEqual(len(self._effects()), 1)

    def test_missing_source_line_id_raises_clear_error_and_preserves_existing_effect(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("5"))])
        )

        with self.assertRaisesRegex(ValidationError, "Thiếu mã dòng nguồn"):
            self.effect_service.reconcile_daily_record_effects(
                self._snapshot(cut_lines=[self._cut_line(quantity=Decimal("9"), line_id=None)])
            )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("5"))
        self.assertEqual(len(self._effects()), 1)

    def test_duplicate_source_line_in_same_snapshot_is_rejected_before_stock_changes(self) -> None:
        with self.assertRaisesRegex(ValidationError, "bị trùng"):
            self.effect_service.reconcile_daily_record_effects(
                self._snapshot(
                    cut_lines=[
                        self._cut_line(product_id=self.bao_product_id, quantity=Decimal("2"), line_id=10),
                        self._cut_line(product_id=self.bao_product_id, quantity=Decimal("3"), line_id=10),
                    ]
                )
            )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self._effects(), [])

    def test_unsupported_source_line_type_is_rejected(self) -> None:
        bad_line = AttendanceInventoryEffectLine(
            source_line_type="BAD_LINE",
            source_line_id=88,
            attendance_bag_type_id=20,
            product_id=self.bao_product_id,
            quantity=Decimal("1"),
        )

        with self.assertRaisesRegex(ValidationError, "không hợp lệ"):
            self.effect_service.reconcile_daily_record_effects(self._snapshot(cut_lines=[bad_line]))

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self._effects(), [])

    def test_product_id_not_found_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Không tìm thấy hàng hóa"):
            self.effect_service.reconcile_daily_record_effects(
                self._snapshot(cut_lines=[self._cut_line(product_id=9999)])
            )

    def test_bao_kg_product_maps_to_bao_balance(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(product_id=self.bao_product_id, quantity=Decimal("2.25"))])
        )

        self.assertEqual(self._quantity(self.bao_product_id, UnitType.BAO), Decimal("2.25"))
        self.assertEqual(self._quantity(self.bao_product_id, UnitType.KG), Decimal("56.25"))

    def test_bich_product_maps_to_bich_balance(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(cut_lines=[self._cut_line(product_id=self.bich_product_id, quantity=Decimal("6"))])
        )

        self.assertEqual(self._quantity(self.bich_product_id, UnitType.BICH), Decimal("6"))

    def test_effect_rows_contain_attendance_source_metadata(self) -> None:
        self.effect_service.reconcile_daily_record_effects(
            self._snapshot(
                cut_lines=[self._cut_line(product_id=self.bao_product_id, quantity=Decimal("2"), line_id=101)],
                extra_cut_lines=[self._vk_line(product_id=self.bich_product_id, quantity=Decimal("3"), line_id=202)],
            )
        )

        effects = self._effects()
        self.assertEqual(len(effects), 2)
        self.assertEqual(effects[0].source_type, ATTENDANCE_DAILY_RECORD_SOURCE_TYPE)
        self.assertEqual(effects[0].source_id, 100)
        self.assertEqual(effects[0].source_line_type, CUT_LOG_SOURCE_LINE_TYPE)
        self.assertEqual(effects[0].source_line_id, 101)
        self.assertEqual(effects[0].product_id, self.bao_product_id)
        self.assertEqual(effects[0].quantity_delta, Decimal("2"))
        self.assertEqual(effects[1].source_line_type, EXTRA_CUT_WORK_LOG_SOURCE_LINE_TYPE)
        self.assertEqual(effects[1].source_line_id, 202)
        self.assertEqual(effects[1].product_id, self.bich_product_id)
        self.assertEqual(effects[1].quantity_delta, Decimal("3"))

    def test_inventory_stock_effect_schema_is_idempotent_and_indexed(self) -> None:
        Base.metadata.create_all(self.engine)
        inspector = inspect(self.engine)

        self.assertIn("inventory_stock_effects", inspector.get_table_names())
        indexes = {index["name"] for index in inspector.get_indexes("inventory_stock_effects")}
        unique_constraints = {
            constraint["name"] for constraint in inspector.get_unique_constraints("inventory_stock_effects")
        }
        self.assertIn("ix_inventory_stock_effects_source", indexes)
        self.assertIn("ix_inventory_stock_effects_product_id", indexes)
        self.assertIn("uq_inventory_stock_effects_source_line", unique_constraints)
        columns = {column["name"]: column for column in inspector.get_columns("inventory_stock_effects")}
        self.assertFalse(columns["source_line_id"]["nullable"])


if __name__ == "__main__":
    unittest.main()
