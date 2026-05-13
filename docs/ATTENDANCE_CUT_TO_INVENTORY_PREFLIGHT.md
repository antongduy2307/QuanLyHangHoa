# Attendance CUT/VK To Inventory Preflight

This is a preflight audit and hardening pass before integrating inventory effects into `AttendanceDayEntryService.save_attendance(...)`.

No attendance save integration, UI behavior, backfill, formula, sales/return/customer/order behavior, or database merge work was done.

## A. Files Inspected

- `modules/inventory/models.py`
- `modules/attendance/inventory_effect_service.py`
- `tests/test_attendance_inventory_effect_service.py`
- `core/db.py`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH1.md`

## B. Current source_line_id Behavior

Before this preflight hardening:

1. `InventoryStockEffect.source_line_id` was nullable in `modules/inventory/models.py`.
2. `AttendanceInventoryEffectLine.source_line_id` was typed as `int | None`.
3. `AttendanceInventoryEffectService` did not explicitly validate `source_line_id`.
4. `reconcile_daily_record_effects(...)` could insert an effect row with `source_line_id = NULL`.
5. The unique constraint on `(source_type, source_id, source_line_type, source_line_id)` would not reliably protect duplicate lines if `source_line_id` were NULL because SQLite treats NULL values as distinct for unique constraints.
6. Rollback already primarily used `(source_type, source_id)`, which is correct for attendance edits where logs are cleared/recreated.
7. Old effects were deleted and rolled back by daily record source before new effects were inserted.
8. Existing idempotence tests passed mostly because rollback by source was correct; they did not prove line-level duplicate protection when `source_line_id` was missing.

## C. Risks Found

Primary risk:

- A future Batch 2 integration bug could build a snapshot before flushing the attendance session, producing `CutLog.id` / `ExtraCutWorkLog.id` as `None`.

Consequences before hardening:

- The service could insert `inventory_stock_effects.source_line_id = NULL`.
- SQLite's unique constraint would not prevent multiple NULL source-line rows.
- Duplicate line effects in the same snapshot could become a low-level database error or, if NULL, bypass line-level uniqueness.

## D. Hardening Changes Made

Files changed:

- `modules/inventory/models.py`
- `modules/attendance/inventory_effect_service.py`
- `tests/test_attendance_inventory_effect_service.py`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_PREFLIGHT.md`

Model hardening:

- `InventoryStockEffect.source_line_id` is now `nullable=False` for newly created schemas.
- The unique constraint remains:
  - `(source_type, source_id, source_line_type, source_line_id)`

Service hardening:

- `AttendanceInventoryEffectLine.source_line_id` is typed as `int`.
- `AttendanceInventoryEffectService` rejects `source_line_id is None` with `ValidationError`.
- Duplicate `(source_line_type, source_line_id)` pairs in the same snapshot are rejected with `ValidationError`.
- Unsupported `source_line_type` values are rejected with `ValidationError`.
- Validation happens before old effects are rolled back, so invalid incoming snapshots leave existing stock/effect rows unchanged.

Migration note:

- Existing SQLite databases that already created the Batch 1 table with a nullable column will not be altered automatically by `create_all()`.
- This is acceptable for preflight because the service now guarantees it will not insert NULL `source_line_id`.
- A future dedicated migration can rebuild/validate the table if production data exists before the NOT NULL model change ships.

## E. Source Line Validation

Allowed line types:

- `CUT_LOG`
- `EXTRA_CUT_WORK_LOG`

Rejected conditions:

- missing `source_line_id`;
- duplicate `(source_line_type, source_line_id)` in the same snapshot;
- unsupported source line type;
- missing product id;
- negative quantity;
- product id not found.

Clear error examples:

- `Thiếu mã dòng nguồn tồn kho từ chấm công.`
- `Dòng nguồn tồn kho từ chấm công bị trùng.`
- `Loại dòng chấm công không hợp lệ để cập nhật tồn kho.`

`source_type` remains fixed as:

- `ATTENDANCE_DAILY_RECORD`

## F. Integration Readiness Notes For Batch 2

Batch 2 must build the inventory snapshot only after attendance logs have database ids.

Required call order:

1. Save or rebuild the attendance `DailyRecord` and its logs.
2. Set final `record.status`.
3. Flush the attendance session.
4. Build `AttendanceInventoryEffectSnapshot` from the flushed ORM objects:
   - `record.id`
   - `record.employee_id`
   - `record.date`
   - `record.status`
   - `record.is_absent`
   - each `CutLog.id`
   - each `ExtraCutWorkLog.id`
   - each line `bag_type_id`
   - each `BagType.source_product_id`
   - each line `quantity`
5. Call `AttendanceInventoryEffectService.reconcile_daily_record_effects(snapshot)`.

Do not build this snapshot before `session.flush()`. If a future integration does that, this preflight validation will fail fast with a clear `ValidationError` instead of inserting weak effect rows.

## G. Idempotence / Rollback Confirmation

Confirmed behavior:

- Reconciles by daily record source: `(source_type, source_id)`.
- Old effects are rolled back and deleted before new effects are inserted.
- Same DONE snapshot twice does not double count.
- A DONE edit with the same `source_id` but different `source_line_id` still works because rollback is by daily record source.
- DONE to DRAFT rolls back old effects and applies nothing.
- DONE to absent rolls back old effects and applies nothing.
- Missing source line ids are rejected before rollback/apply.
- Duplicate source lines in the same snapshot are rejected before stock changes.

This preserves the intended design for real attendance edits, where log rows are cleared/recreated and line ids can change across saves.

## H. Tests / Verification

New or strengthened tests:

- missing `source_line_id` is rejected and preserves existing effects;
- duplicate source line in the same snapshot is rejected before stock changes;
- unsupported `source_line_type` is rejected;
- edited DONE snapshot with different source line ids still reconciles by daily record source;
- schema inspection verifies `source_line_id` is not nullable for newly created schemas.

Commands run:

```powershell
python -m unittest tests.test_attendance_inventory_effect_service
python -m unittest tests.test_inventory_service
python -m unittest tests.test_inventory_transactions
python -m compileall core modules tests shell
python -m unittest discover -s tests -p "test*.py" -t .
```

Results:

- `tests.test_attendance_inventory_effect_service`: 21 tests OK.
- `tests.test_inventory_service`: 20 tests OK.
- `tests.test_inventory_transactions`: 7 tests OK.
- `compileall`: completed successfully.
- Full unittest discovery: 428 tests OK.

Note:

- Local PowerShell still reports the user profile execution-policy warning before commands; it does not affect test results.

## I. Caveats

- Existing local databases that already created `inventory_stock_effects.source_line_id` as nullable will not be structurally changed by this preflight. Service-level validation prevents NULL inserts through the supported path.
- Batch 2 still needs careful cross-DB error handling because attendance and inventory remain separate SQLite databases.
- This preflight does not apply inventory effects from real attendance saves yet.
