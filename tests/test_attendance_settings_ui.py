from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QCheckBox, QDialog, QTableWidget

import core.config
import core.db
from core.enums import UnitMode
from core.exceptions import ValidationError
from modules.attendance.db import AttendanceSessionLocal, get_attendance_engine, init_attendance_db, reset_attendance_engine_cache
from modules.attendance.models import BagType, CutLog, DailyRecord, DailyRecordStatus, Employee, Period, Team
from modules.attendance.settings_service import AttendanceSettingsService
from modules.attendance.ui.settings_tab import AttendancePriceSettingsTab, BagTypeDialog, BagTypeFormValue
from modules.inventory.models import Product


class _SignalStub:
    def connect(self, _callback) -> None:
        return


class AttendanceProductSettingsUiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temp_root = Path(tempfile.mkdtemp(prefix="attendance-settings-ui-"))
        self._env_patch = patch.dict(os.environ, {"LOCALAPPDATA": str(self._temp_root)}, clear=False)
        self._env_patch.start()
        core.config.get_settings.cache_clear()
        core.db.reset_engine_cache()
        reset_attendance_engine_cache()
        core.db.init_db()
        init_attendance_db()
        self.settings_service = AttendanceSettingsService()

    def tearDown(self) -> None:
        QApplication.closeAllWindows()
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

    def _bag_type_for_product(self, product_id: int) -> BagType:
        with AttendanceSessionLocal() as session:
            return session.query(BagType).filter_by(source_product_id=product_id).one()

    def _set_bag_type_config(
        self,
        product_id: int,
        *,
        quota_quantity: Decimal | int,
        excess_unit_price: Decimal | int,
        excluded: bool = False,
    ) -> None:
        with AttendanceSessionLocal() as session:
            bag_type = session.query(BagType).filter_by(source_product_id=product_id).one()
            bag_type.quota_quantity = Decimal(str(quota_quantity))
            bag_type.excess_unit_price = Decimal(str(excess_unit_price))
            bag_type.is_excluded_from_attendance = excluded
            session.commit()

    def _create_manual_bag_history(self, name: str) -> int:
        with AttendanceSessionLocal() as session:
            bag_type = BagType(
                name=name,
                unit_price=0,
                quota_quantity=Decimal("0"),
                excess_unit_price=Decimal("0"),
                is_active=True,
            )
            employee = Employee(name=f"Cut {name}", team=Team.CUT, is_active=True)
            period = Period(start_date=date(2026, 5, 1), end_date=date(2026, 5, 10), locked=False)
            session.add_all([bag_type, employee, period])
            session.flush()
            record = DailyRecord(
                employee_id=employee.id,
                date=date(2026, 5, 1),
                period_id=period.id,
                status=DailyRecordStatus.DONE,
                total_amount_snapshot=0,
            )
            session.add(record)
            session.flush()
            session.add(
                CutLog(
                    daily_record_id=record.id,
                    bag_type_id=bag_type.id,
                    quantity=Decimal("1"),
                    unit_price_snapshot=0,
                    quota_quantity_snapshot=Decimal("0"),
                    excess_unit_price_snapshot=Decimal("0"),
                    amount_snapshot=0,
                )
            )
            session.commit()
            return int(bag_type.id)

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

    def test_settings_reload_runs_product_sync_and_shows_linked_bag_type(self) -> None:
        product_id = self._create_product("P-SET-1", "Bao settings linked")

        tab = AttendancePriceSettingsTab(AttendanceSettingsService())

        self.assertIn("Bao settings linked", self._table_column_values(tab.bag_type_table, 0))
        bag_type = self._bag_type_for_product(product_id)
        self.assertTrue(bag_type.is_product_linked)

    def test_product_linked_name_is_read_only_in_dialog_and_service_rejects_attendance_rename(self) -> None:
        product_id = self._create_product("P-SET-2", "Bao read only")
        AttendancePriceSettingsTab(AttendanceSettingsService())
        bag_type = self._bag_type_for_product(product_id)

        dialog = BagTypeDialog(bag_type=bag_type)

        self.assertTrue(dialog.name_edit.isReadOnly())
        with self.assertRaises(ValidationError):
            self.settings_service.update_bag_type(
                bag_type.id,
                name="Bao renamed from settings",
                quota_quantity=10,
                excess_unit_price=5000,
                is_active=True,
            )

    def test_quota_price_edit_preserved_after_sync_rerun(self) -> None:
        product_id = self._create_product("P-SET-3", "Bao editable")
        tab = AttendancePriceSettingsTab(AttendanceSettingsService())
        row = self._find_row(tab.bag_type_table, "Bao editable")
        tab.bag_type_table.selectRow(row)

        class FakeBagTypeDialog:
            def __init__(self, *_args, **_kwargs) -> None:
                self.deactivate_requested = _SignalStub()

            def exec(self) -> QDialog.DialogCode:
                return QDialog.DialogCode.Accepted

            def value(self) -> BagTypeFormValue:
                return BagTypeFormValue(
                    name="Bao editable",
                    quota_quantity=12,
                    excess_unit_price=5500,
                    is_excluded_from_attendance=False,
                )

        with patch("modules.attendance.ui.settings_tab.BagTypeDialog", FakeBagTypeDialog):
            tab._edit_bag_type()
        tab.reload()

        bag_type = self._bag_type_for_product(product_id)
        self.assertEqual(bag_type.quota_quantity, Decimal("12.00"))
        self.assertEqual(bag_type.excess_unit_price, Decimal("5500.00"))
        self.assertFalse(bag_type.is_excluded_from_attendance)

    def test_checkbox_semantics_set_and_unset_exclusion(self) -> None:
        product_id = self._create_product("P-SET-4", "Bao checkbox")
        tab = AttendancePriceSettingsTab(AttendanceSettingsService())
        row = self._find_row(tab.bag_type_table, "Bao checkbox")
        holder = tab.bag_type_table.cellWidget(row, 3)
        checkbox = holder.findChild(QCheckBox)
        assert checkbox is not None
        self.assertFalse(checkbox.isChecked())

        checkbox.setChecked(True)
        self.assertTrue(self._bag_type_for_product(product_id).is_excluded_from_attendance)
        row = self._find_row(tab.bag_type_table, "Bao checkbox")
        holder = tab.bag_type_table.cellWidget(row, 3)
        checkbox = holder.findChild(QCheckBox)
        assert checkbox is not None
        checkbox.setChecked(False)

        self.assertFalse(self._bag_type_for_product(product_id).is_excluded_from_attendance)

    def test_incomplete_highlight_updates_for_configured_and_excluded_rows(self) -> None:
        incomplete_id = self._create_product("P-SET-5", "Bao incomplete")
        configured_id = self._create_product("P-SET-6", "Bao configured")
        excluded_id = self._create_product("P-SET-7", "Bao excluded")
        tab = AttendancePriceSettingsTab(AttendanceSettingsService())
        self._set_bag_type_config(configured_id, quota_quantity=10, excess_unit_price=5000)
        self._set_bag_type_config(excluded_id, quota_quantity=0, excess_unit_price=0, excluded=True)
        tab.reload()

        incomplete_row = self._find_row(tab.bag_type_table, "Bao incomplete")
        configured_row = self._find_row(tab.bag_type_table, "Bao configured")
        excluded_row = self._find_row(tab.bag_type_table, "Bao excluded")

        self.assertEqual(tab.bag_type_table.item(incomplete_row, 0).background().color(), QColor(255, 235, 235))
        self.assertNotEqual(tab.bag_type_table.item(configured_row, 0).background().color(), QColor(255, 235, 235))
        self.assertNotEqual(tab.bag_type_table.item(excluded_row, 0).background().color(), QColor(255, 235, 235))
        self.assertEqual({item.source_product_id for item in tab._product_sync_service.list_incomplete_cut_work_items()}, {incomplete_id})

    def test_legacy_rows_are_hidden_from_active_settings_table(self) -> None:
        manual_id = self._create_manual_bag_history("Manual legacy settings")
        self._create_product("P-SET-8", "Bao normal")

        tab = AttendancePriceSettingsTab(AttendanceSettingsService())

        self.assertNotIn("Manual legacy settings", self._table_column_values(tab.bag_type_table, 0))
        with AttendanceSessionLocal() as session:
            manual = session.get(BagType, manual_id)
            self.assertIsNotNone(manual)
            assert manual is not None
            self.assertFalse(manual.is_active)
            self.assertTrue(manual.is_legacy)

    def test_sync_warnings_show_banner_without_blocking_non_conflicting_rows(self) -> None:
        self._create_product("P-SET-9", "Bao duplicate")
        self._create_product("P-SET-10", "Bao duplicate")
        self._create_product("P-SET-11", "Bao non conflict")

        tab = AttendancePriceSettingsTab(AttendanceSettingsService())

        self.assertFalse(tab.sync_warning_label.isHidden())
        self.assertTrue(tab.sync_warning_label.text())
        self.assertIn("Bao non conflict", self._table_column_values(tab.bag_type_table, 0))
        self.assertNotIn("Bao duplicate", self._table_column_values(tab.bag_type_table, 0))


if __name__ == "__main__":
    unittest.main()
