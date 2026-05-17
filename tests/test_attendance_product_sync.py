from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, inspect, select

import core.config
import core.db
from core.enums import UnitMode
from modules.attendance.db import (
    AttendanceSessionLocal,
    get_attendance_engine,
    init_attendance_db,
    reset_attendance_engine_cache,
)
from modules.attendance.models import (
    BagType,
    CutLog,
    DailyRecord,
    DailyRecordStatus,
    Employee,
    ExtraCutWorkLog,
    Period,
    Team,
)
from modules.attendance.product_sync_service import AttendanceProductSyncService
from modules.inventory.models import Product


class AttendanceProductSyncTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_root = Path(tempfile.mkdtemp(prefix="attendance-product-sync-"))
        self._env_patch = patch.dict(os.environ, {"LOCALAPPDATA": str(self._temp_root)}, clear=False)
        self._env_patch.start()
        core.config.get_settings.cache_clear()
        core.db.reset_engine_cache()
        reset_attendance_engine_cache()
        core.db.init_db()
        init_attendance_db()
        self.service = AttendanceProductSyncService()

    def tearDown(self) -> None:
        get_attendance_engine().dispose()
        reset_attendance_engine_cache()
        core.config.get_settings.cache_clear()
        self._env_patch.stop()
        core.db.reset_engine_cache()
        shutil.rmtree(self._temp_root, ignore_errors=True)

    def _create_product(self, code: str, name: str, *, is_active: bool = True) -> int:
        with core.db.SessionFactory() as session:
            product = Product(
                product_code_base=code,
                product_name=name,
                unit_mode=UnitMode.BAO_KG,
                is_active=is_active,
            )
            session.add(product)
            session.commit()
            return int(product.id)

    def _linked_bag_type(self, source_product_id: int) -> BagType:
        with AttendanceSessionLocal() as session:
            return session.scalars(select(BagType).where(BagType.source_product_id == source_product_id)).one()

    def _manual_bag_type(self, name: str, *, is_active: bool = True) -> int:
        with AttendanceSessionLocal() as session:
            bag_type = BagType(
                name=name,
                unit_price=0,
                quota_quantity=Decimal("0"),
                excess_unit_price=Decimal("0"),
                is_active=is_active,
            )
            session.add(bag_type)
            session.commit()
            return int(bag_type.id)

    def _create_cut_history(self, bag_type_id: int) -> int:
        with AttendanceSessionLocal() as session:
            employee = Employee(name=f"Cut history {bag_type_id}", team=Team.CUT, is_active=True)
            period = Period(start_date=date(2026, 5, 1), end_date=date(2026, 5, 10), locked=False)
            session.add_all([employee, period])
            session.flush()
            record = DailyRecord(
                employee_id=employee.id,
                date=date(2026, 5, 3),
                period_id=period.id,
                status=DailyRecordStatus.DONE,
                total_amount_snapshot=0,
            )
            session.add(record)
            session.flush()
            log = CutLog(
                daily_record_id=record.id,
                bag_type_id=bag_type_id,
                quantity=Decimal("1"),
                unit_price_snapshot=0,
                quota_quantity_snapshot=Decimal("0"),
                excess_unit_price_snapshot=Decimal("0"),
                amount_snapshot=0,
            )
            session.add(log)
            session.commit()
            return int(log.id)

    def _create_extra_cut_history(self, bag_type_id: int) -> int:
        with AttendanceSessionLocal() as session:
            employee = Employee(name=f"Blow history {bag_type_id}", team=Team.BLOW, is_active=True)
            period = Period(start_date=date(2026, 5, 1), end_date=date(2026, 5, 10), locked=False)
            session.add_all([employee, period])
            session.flush()
            record = DailyRecord(
                employee_id=employee.id,
                date=date(2026, 5, 4),
                period_id=period.id,
                status=DailyRecordStatus.DONE,
                total_amount_snapshot=0,
            )
            session.add(record)
            session.flush()
            log = ExtraCutWorkLog(
                daily_record_id=record.id,
                bag_type_id=bag_type_id,
                quantity=Decimal("1"),
                excess_unit_price_snapshot=Decimal("0"),
                amount_snapshot=0,
            )
            session.add(log)
            session.commit()
            return int(log.id)

    def test_schema_migration_adds_columns_idempotently_and_preserves_rows(self) -> None:
        with AttendanceSessionLocal() as session:
            before_count = session.query(BagType).count()

        init_attendance_db()
        init_attendance_db()

        inspector = inspect(get_attendance_engine())
        columns = {column["name"] for column in inspector.get_columns("bag_types")}
        self.assertTrue(
            {
                "is_product_linked",
                "source_product_id",
                "source_product_name_snapshot",
                "is_excluded_from_attendance",
                "is_legacy",
            }.issubset(columns)
        )
        indexes = {index["name"] for index in inspector.get_indexes("bag_types")}
        self.assertIn("ix_bag_types_source_product_id_unique", indexes)
        with AttendanceSessionLocal() as session:
            self.assertEqual(session.query(BagType).count(), before_count)

    def test_initial_sync_creates_linked_bag_type_with_attendance_defaults(self) -> None:
        product_id = self._create_product("P001", "Bao sync")

        result = self.service.sync_products_to_cut_work()

        self.assertEqual(result.created_count, 1)
        self.assertFalse(result.warnings)
        bag_type = self._linked_bag_type(product_id)
        self.assertEqual(bag_type.name, "Bao sync")
        self.assertEqual(bag_type.quota_quantity, Decimal("0.00"))
        self.assertEqual(bag_type.excess_unit_price, Decimal("0.00"))
        self.assertTrue(bag_type.is_active)
        self.assertTrue(bag_type.is_product_linked)
        self.assertEqual(bag_type.source_product_id, product_id)
        self.assertEqual(bag_type.source_product_name_snapshot, "Bao sync")
        self.assertFalse(bag_type.is_excluded_from_attendance)
        self.assertFalse(bag_type.is_legacy)
        self.assertEqual([item.source_product_id for item in result.incomplete_items], [product_id])

    def test_sync_preserves_attendance_config_and_exclusion(self) -> None:
        product_id = self._create_product("P002", "Bao configured")
        self.service.sync_products_to_cut_work()
        with AttendanceSessionLocal() as session:
            bag_type = session.scalars(select(BagType).where(BagType.source_product_id == product_id)).one()
            bag_type.quota_quantity = Decimal("18.5")
            bag_type.excess_unit_price = Decimal("3500")
            bag_type.is_excluded_from_attendance = True
            session.commit()

        result = self.service.sync_products_to_cut_work()

        bag_type = self._linked_bag_type(product_id)
        self.assertEqual(bag_type.quota_quantity, Decimal("18.50"))
        self.assertEqual(bag_type.excess_unit_price, Decimal("3500.00"))
        self.assertTrue(bag_type.is_excluded_from_attendance)
        self.assertEqual(result.incomplete_items, [])

    def test_product_rename_updates_linked_name_and_snapshot_only(self) -> None:
        product_id = self._create_product("P003", "Bao old")
        self.service.sync_products_to_cut_work()
        with AttendanceSessionLocal() as session:
            bag_type = session.scalars(select(BagType).where(BagType.source_product_id == product_id)).one()
            bag_type.quota_quantity = Decimal("12.5")
            bag_type.excess_unit_price = Decimal("4200")
            bag_type.is_excluded_from_attendance = True
            session.commit()
        with core.db.SessionFactory() as session:
            product = session.get(Product, product_id)
            assert product is not None
            product.product_name = "Bao new"
            session.commit()

        result = self.service.sync_products_to_cut_work()

        self.assertEqual(result.updated_count, 1)
        bag_type = self._linked_bag_type(product_id)
        self.assertEqual(bag_type.name, "Bao new")
        self.assertEqual(bag_type.source_product_name_snapshot, "Bao new")
        self.assertEqual(bag_type.quota_quantity, Decimal("12.50"))
        self.assertEqual(bag_type.excess_unit_price, Decimal("4200.00"))
        self.assertTrue(bag_type.is_excluded_from_attendance)

    def test_inactive_product_deactivates_linked_bag_type_and_marks_legacy_when_history_exists(self) -> None:
        product_id = self._create_product("P004", "Bao inactive")
        self.service.sync_products_to_cut_work()
        bag_type = self._linked_bag_type(product_id)
        log_id = self._create_cut_history(int(bag_type.id))
        with core.db.SessionFactory() as session:
            product = session.get(Product, product_id)
            assert product is not None
            product.is_active = False
            session.commit()

        result = self.service.sync_products_to_cut_work()

        self.assertEqual(result.deactivated_count, 1)
        self.assertEqual(result.legacy_count, 1)
        bag_type = self._linked_bag_type(product_id)
        self.assertFalse(bag_type.is_active)
        self.assertTrue(bag_type.is_legacy)
        with AttendanceSessionLocal() as session:
            self.assertIsNotNone(session.get(CutLog, log_id))

    def test_reactivated_product_reactivates_existing_linked_bag_type(self) -> None:
        product_id = self._create_product("P004R", "Bao reactivated")
        self.service.sync_products_to_cut_work()
        bag_type = self._linked_bag_type(product_id)
        self._create_cut_history(int(bag_type.id))
        with core.db.SessionFactory() as session:
            product = session.get(Product, product_id)
            assert product is not None
            product.is_active = False
            session.commit()
        self.service.sync_products_to_cut_work()

        with core.db.SessionFactory() as session:
            product = session.get(Product, product_id)
            assert product is not None
            product.is_active = True
            session.commit()
        result = self.service.sync_products_to_cut_work()

        self.assertEqual(result.updated_count, 1)
        bag_type = self._linked_bag_type(product_id)
        self.assertTrue(bag_type.is_active)
        self.assertFalse(bag_type.is_legacy)

    def test_missing_product_deactivates_and_marks_linked_bag_type_legacy_without_deleting(self) -> None:
        product_id = self._create_product("P005", "Bao deleted")
        self.service.sync_products_to_cut_work()
        with core.db.SessionFactory() as session:
            product = session.get(Product, product_id)
            assert product is not None
            session.delete(product)
            session.commit()

        result = self.service.sync_products_to_cut_work()

        self.assertEqual(result.deactivated_count, 1)
        self.assertEqual(result.legacy_count, 1)
        bag_type = self._linked_bag_type(product_id)
        self.assertFalse(bag_type.is_active)
        self.assertTrue(bag_type.is_legacy)

    def test_manual_bag_type_with_cut_history_is_marked_legacy_inactive_and_preserved(self) -> None:
        bag_type_id = self._manual_bag_type("Manual with cut")
        log_id = self._create_cut_history(bag_type_id)

        result = self.service.sync_products_to_cut_work()

        self.assertEqual(result.legacy_count, 1)
        with AttendanceSessionLocal() as session:
            bag_type = session.get(BagType, bag_type_id)
            self.assertIsNotNone(bag_type)
            assert bag_type is not None
            self.assertFalse(bag_type.is_active)
            self.assertTrue(bag_type.is_legacy)
            self.assertIsNotNone(session.get(CutLog, log_id))

    def test_manual_bag_type_with_extra_cut_history_is_marked_legacy_inactive_and_preserved(self) -> None:
        bag_type_id = self._manual_bag_type("Manual with vk")
        log_id = self._create_extra_cut_history(bag_type_id)

        result = self.service.sync_products_to_cut_work()

        self.assertEqual(result.legacy_count, 1)
        with AttendanceSessionLocal() as session:
            bag_type = session.get(BagType, bag_type_id)
            self.assertIsNotNone(bag_type)
            assert bag_type is not None
            self.assertFalse(bag_type.is_active)
            self.assertTrue(bag_type.is_legacy)
            self.assertIsNotNone(session.get(ExtraCutWorkLog, log_id))

    def test_manual_bag_type_without_history_is_deactivated_not_deleted(self) -> None:
        bag_type_id = self._manual_bag_type("Manual without history")

        result = self.service.sync_products_to_cut_work()

        self.assertGreaterEqual(result.deactivated_count, 1)
        with AttendanceSessionLocal() as session:
            bag_type = session.get(BagType, bag_type_id)
            self.assertIsNotNone(bag_type)
            assert bag_type is not None
            self.assertFalse(bag_type.is_active)
            self.assertFalse(bag_type.is_legacy)

    def test_incomplete_detection_respects_quota_price_and_exclusion(self) -> None:
        product_a = self._create_product("P006", "Bao none")
        product_b = self._create_product("P007", "Bao quota only")
        product_c = self._create_product("P008", "Bao price only")
        product_d = self._create_product("P009", "Bao complete")
        product_e = self._create_product("P010", "Bao excluded")
        self.service.sync_products_to_cut_work()
        with AttendanceSessionLocal() as session:
            rows = {
                row.source_product_id: row
                for row in session.scalars(
                    select(BagType).where(BagType.source_product_id.in_([product_a, product_b, product_c, product_d, product_e]))
                )
            }
            rows[product_b].quota_quantity = Decimal("10")
            rows[product_c].excess_unit_price = Decimal("3500")
            rows[product_d].quota_quantity = Decimal("0.5")
            rows[product_d].excess_unit_price = Decimal("3500")
            rows[product_e].is_excluded_from_attendance = True
            session.commit()

        incomplete = self.service.list_incomplete_cut_work_items()

        self.assertEqual({item.source_product_id for item in incomplete}, {product_a, product_b, product_c})

    def test_duplicate_active_product_names_return_warning_and_skip_ambiguous_rows(self) -> None:
        first_id = self._create_product("P011", "Bao duplicate")
        second_id = self._create_product("P012", "Bao duplicate")

        result = self.service.sync_products_to_cut_work()

        self.assertTrue(any("Duplicate active product name" in warning for warning in result.warnings))
        with AttendanceSessionLocal() as session:
            linked_count = session.scalar(
                select(func.count(BagType.id)).where(BagType.source_product_id.in_([first_id, second_id]))
            )
        self.assertEqual(linked_count, 0)

    def test_manual_name_conflict_returns_warning_without_overwriting_row(self) -> None:
        product_id = self._create_product("P013", "Bao conflict")
        manual_id = self._manual_bag_type("Bao conflict")

        result = self.service.sync_products_to_cut_work()

        self.assertTrue(any("conflicts with existing attendance CUT work item" in warning for warning in result.warnings))
        with AttendanceSessionLocal() as session:
            self.assertIsNone(session.scalar(select(BagType.id).where(BagType.source_product_id == product_id)))
            manual = session.get(BagType, manual_id)
            self.assertIsNotNone(manual)
            assert manual is not None
            self.assertEqual(manual.name, "Bao conflict")

    def test_product_rename_conflict_returns_warning_without_overwriting_row(self) -> None:
        product_id = self._create_product("P014", "Bao rename old")
        self._manual_bag_type("Bao rename conflict")
        self.service.sync_products_to_cut_work()
        with core.db.SessionFactory() as session:
            product = session.get(Product, product_id)
            assert product is not None
            product.product_name = "Bao rename conflict"
            session.commit()

        result = self.service.sync_products_to_cut_work()

        self.assertTrue(any("Product rename conflicts" in warning for warning in result.warnings))
        bag_type = self._linked_bag_type(product_id)
        self.assertEqual(bag_type.name, "Bao rename old")


if __name__ == "__main__":
    unittest.main()
