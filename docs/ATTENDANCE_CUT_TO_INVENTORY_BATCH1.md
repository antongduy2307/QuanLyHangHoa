# Attendance CUT/VK To Inventory Batch 1

Batch 1 implements the main DB inventory effect foundation only. It does not integrate with `AttendanceDayEntryService.save_attendance`, does not change UI behavior, and does not backfill historical attendance records.

## A. Files Changed

- `modules/inventory/models.py`
  - Added `InventoryStockEffect`.
- `modules/attendance/inventory_effect_service.py`
  - Added snapshot DTOs and `AttendanceInventoryEffectService`.
- `tests/test_attendance_inventory_effect_service.py`
  - Added focused tests for schema, rollback/apply, idempotence, unit mapping, decimal quantities, and validation.
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH1.md`
  - Added this implementation report.

## B. Schema / Model Added

Added main DB table:

`inventory_stock_effects`

Model:

`modules.inventory.models.InventoryStockEffect`

Fields:

- `id`
- `source_type`
- `source_id`
- `source_line_type`
- `source_line_id`
- `attendance_employee_id`
- `attendance_work_date`
- `attendance_bag_type_id`
- `product_id`
- `quantity_delta`
- `unit_type`
- `movement_datetime`
- `note`
- `created_at`
- `updated_at`

Indexes / constraints:

- index: `ix_inventory_stock_effects_source` on `(source_type, source_id)`
- index: `ix_inventory_stock_effects_product_id` on `product_id`
- unique constraint: `uq_inventory_stock_effects_source_line` on `(source_type, source_id, source_line_type, source_line_id)`
- check constraints for nonblank source fields and non-negative `quantity_delta`
- FK: `product_id -> products.id`

The model intentionally stores attendance ids as plain snapshot/source fields because attendance records live in a separate SQLite database.

## C. Migration Behavior

The table is added through the existing main DB SQLAlchemy metadata path.

`core.db.init_db()` already imports inventory models and calls `Base.metadata.create_all(bind=ENGINE)`, so existing databases receive the new table idempotently without needing a fresh DB.

This batch does not alter existing inventory, sales, return, customer, or attendance tables.

## D. Service Behavior

Added:

`modules.attendance.inventory_effect_service.AttendanceInventoryEffectService`

Primary method:

`reconcile_daily_record_effects(snapshot)`

Input is a plain `AttendanceInventoryEffectSnapshot`; the service does not query the attendance DB in this batch.

Behavior:

1. Validate the snapshot identity.
2. For DONE, non-absent snapshots, validate all new CUT/VK lines before changing stock.
3. Load old `inventory_stock_effects` for:
   - `source_type = ATTENDANCE_DAILY_RECORD`
   - `source_id = snapshot.daily_record_id`
4. Roll back old effects by applying inverse stock changes.
5. Delete old effect rows.
6. If the snapshot is DRAFT or absent, commit rollback only.
7. If the snapshot is DONE and not absent, increase stock for current CUT/VK lines and insert fresh effect rows.
8. Return `AttendanceInventoryEffectResult` with rollback count, applied count, product deltas, and warnings.

Line types:

- `CUT_LOG`
- `EXTRA_CUT_WORK_LOG`

## E. Unit Mapping

Product unit mode maps to inventory unit type as follows:

- `UnitMode.BAO_KG` -> `UnitType.BAO`
- `UnitMode.BICH` -> `UnitType.BICH`

No KG conversion is applied for attendance production. Decimal quantities are passed through as `Decimal`.

## F. Idempotence Behavior

The service reconciles by attendance daily record source:

- old effects are rolled back and deleted by `(source_type, source_id)`;
- current effects are inserted from the latest snapshot.

Verified behavior:

- reconciling the same DONE snapshot twice does not double count stock;
- changing a DONE quantity upward/downward leaves stock equal to the latest quantity only;
- removing a line rolls back the old line;
- changing DONE to DRAFT rolls back old effects and applies nothing;
- changing DONE to absent rolls back old effects and applies nothing.

## G. Error Handling

Validation errors raise `ValidationError`.

Current clear failure cases:

- missing `product_id`;
- product id not found;
- negative quantity;
- unsupported source line type;
- unsupported product unit mode.

New lines are validated before old effects are rolled back, so invalid incoming snapshots leave existing stock/effect rows unchanged.

No UI messages were added in this batch.

## H. Tests / Verification

Focused tests added:

- DRAFT snapshot does not update inventory.
- DONE CUT snapshot increases product stock.
- DONE VK snapshot increases product stock.
- CUT + VK same product aggregate correctly.
- Multiple products update correct balances.
- Decimal quantity applies exactly.
- Reconcile same DONE snapshot twice is idempotent.
- DONE quantity edits update stock to latest value only.
- Remove line rolls back old line.
- DONE to DRAFT rolls back old effects.
- DONE to absent rolls back old effects.
- Missing product id raises a clear error and preserves existing effects.
- Product id not found raises a clear error.
- BAO_KG maps to BAO balance.
- BICH maps to BICH balance.
- Effect rows contain attendance source metadata.
- Table/index/unique constraint creation is idempotent.

Commands run:

```powershell
python -m unittest tests.test_attendance_inventory_effect_service
python -m unittest tests.test_inventory_service
python -m unittest tests.test_inventory_transactions
python -m compileall core modules tests shell
python -m unittest discover -s tests -p "test*.py" -t .
```

Results:

- `tests.test_attendance_inventory_effect_service`: 17 tests OK.
- `tests.test_inventory_service`: 20 tests OK.
- `tests.test_inventory_transactions`: 7 tests OK.
- `compileall`: completed successfully.
- full discovery: 424 tests OK.

Note: `.venv\Scripts\python.exe` was not usable in this local shell because Windows returned `Access is denied`, so verification used the available `python` command.

## I. Caveats / Next Batch Recommendation

This batch does not connect the service to real attendance saving yet.

Next batch should:

1. Build an attendance snapshot after `AttendanceDayEntryService.save_attendance(...)` has flushed current CUT/VK logs.
2. Call `AttendanceInventoryEffectService.reconcile_daily_record_effects(...)`.
3. Handle DONE, DRAFT, absent, edited DONE, and removed-line flows.
4. Surface inventory validation failures cleanly to the caller/UI.
5. Add cross-DB failure diagnostics because attendance and inventory are still in separate SQLite databases.
