# Attendance CUT/VK To Inventory Batch 2

Batch 2 integrates real attendance saves with the Batch 1 inventory effect service.

This batch does not backfill old records automatically, does not merge databases, does not change attendance formulas, and does not change UI behavior beyond propagating service errors through the existing save path.

## A. Files Changed

- `modules/attendance/service.py`
  - Added injectable `inventory_effect_service` dependency to `AttendanceDayEntryService`.
  - Built `AttendanceInventoryEffectSnapshot` after attendance flush.
  - Called `reconcile_daily_record_effects(snapshot)` before returning save success.
  - Logged reconciliation failures with daily record context and re-raised them.
- `tests/test_attendance_inventory_integration.py`
  - Added integration coverage for DRAFT/DONE/absent/edit/remove/idempotence flows.
- `tests/test_attendance_day_entry.py`
  - Injected no-op inventory effect service for attendance-only tests.
- `tests/test_attendance_report.py`
  - Injected no-op inventory effect service for report-only tests.
- `tests/test_attendance_settings.py`
  - Injected no-op inventory effect service for settings-only tests.
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH2.md`
  - Added this implementation report.

## B. Snapshot Construction

`AttendanceDayEntryService` now builds a plain `AttendanceInventoryEffectSnapshot` from the flushed attendance record.

Snapshot fields:

- `daily_record_id = record.id`
- `employee_id = record.employee_id`
- `work_date = record.date`
- `status = record.status`
- `is_absent = record.is_absent`

CUT line fields:

- `source_line_type = CUT_LOG`
- `source_line_id = cut_log.id`
- `attendance_bag_type_id = cut_log.bag_type_id`
- `product_id = cut_log.bag_type.source_product_id`
- `quantity = cut_log.quantity`

VK line fields:

- `source_line_type = EXTRA_CUT_WORK_LOG`
- `source_line_id = extra_cut_work_log.id`
- `attendance_bag_type_id = extra_cut_work_log.bag_type_id`
- `product_id = extra_cut_work_log.bag_type.source_product_id`
- `quantity = extra_cut_work_log.quantity`

No float conversion is used.

## C. Integration Point / Call Order

Integrated in:

- `modules/attendance/service.py`
- `AttendanceDayEntryService.save_attendance(...)`

Call order:

1. Open attendance session/transaction.
2. Load/create `DailyRecord`.
3. Capture existing historical CUT/VK bag ids.
4. Clear/rebuild attendance logs.
5. Set final record status:
   - `DONE` when `finalize=True`
   - `DRAFT` when `finalize=False`
6. Flush attendance session.
7. Build inventory effect snapshot from flushed ORM rows.
8. Call `inventory_effect_service.reconcile_daily_record_effects(snapshot)`.
9. Return `AttendanceSaveResult` only after reconciliation succeeds.

The snapshot is intentionally built after `session.flush()` so `CutLog.id` and `ExtraCutWorkLog.id` are non-null.

## D. DRAFT / DONE / Absent Behavior

Implemented through the effect service reconciliation:

- New DRAFT with CUT/VK:
  - attendance record is saved;
  - no inventory stock increase;
  - no effect rows remain for that record.
- New DONE with CUT:
  - linked product stock increases by CUT quantity.
- New DONE with BLOW VK:
  - linked product stock increases by VK quantity.
- Existing DONE saved as DRAFT:
  - old effects are rolled back;
  - no new effects are applied.
- Existing DONE saved as absent:
  - old effects are rolled back;
  - no new effects are applied.

## E. Edit / Idempotence Behavior

The integration preserves Batch 1 reconciliation semantics:

- old effects are rolled back by `(source_type, source_id)`;
- latest flushed CUT/VK lines are applied;
- re-saving the same DONE record does not double count;
- editing DONE quantity up/down leaves stock equal to latest finalized quantities;
- removing CUT/VK lines rolls back removed line effects.

Old DONE records are not scanned or backfilled automatically. If a user explicitly saves/finalizes an old DONE record after this feature exists, that save creates/reconciles inventory effects for that record from that point onward.

## F. Product-Link Validation

For DONE records, `AttendanceInventoryEffectService` validates inventory applicability:

- `source_product_id` must be present;
- product must exist in the main DB;
- product unit mode must map to inventory unit type;
- source line ids must be non-null;
- duplicate source lines are rejected.

DRAFT records do not require valid product links because they apply no new inventory effect. If old effects exist, DRAFT still rolls them back.

Historical invalid BagTypes can still be re-saved by attendance validation rules where previously allowed, but DONE inventory reconciliation requires a resolvable product link and will raise a clear `ValidationError` otherwise.

## G. Error Handling / Cross-DB Caveat

If inventory reconciliation fails:

- the exception is logged with:
  - `daily_record_id`
  - `employee_id`
  - attendance date
- the exception is re-raised;
- save success is not returned.

The attendance transaction is still open while the inventory effect service is called, so an inventory validation failure prevents attendance commit in normal error paths.

Remaining caveat:

- attendance and inventory are separate SQLite databases.
- The inventory service writes to the main DB separately.
- If inventory reconciliation succeeds but the later attendance DB commit fails, a partial cross-DB mismatch is still theoretically possible.
- A future diagnostics/retry batch should detect and reconcile mismatches; this batch intentionally does not add an outbox/retry table.

## H. Tests / Verification

New integration tests cover:

- DRAFT CUT save does not update stock.
- DRAFT VK save does not update stock.
- DONE CUT save updates stock.
- DONE VK save updates stock.
- DONE CUT + VK same product aggregate correctly.
- Multiple products update correct balances.
- Decimal CUT quantity updates stock exactly.
- Decimal VK quantity updates stock exactly.
- Edit DONE quantity upward/downward updates stock to latest only.
- Re-save same DONE does not double count.
- Remove CUT line rolls back stock.
- Remove VK line rolls back stock.
- DONE to DRAFT rolls back stock.
- DONE to absent rolls back stock.
- Missing `source_product_id` on DONE raises clear error.
- Missing main product id raises clear error.
- Old DONE record without effect rows creates effects only after explicit save/finalize.
- Inventory reconciliation failure propagates to caller.
- Fake effect service injection works.
- Snapshot is built after flush with non-null CUT/VK source line ids.
- Effect rows contain attendance source metadata.

Commands run:

```powershell
python -m unittest tests.test_attendance_inventory_integration
python -m unittest tests.test_attendance_inventory_effect_service
python -m unittest tests.test_attendance_day_entry
python -m unittest tests.test_inventory_service
python -m unittest tests.test_inventory_transactions
python -m compileall core modules tests shell
python -m unittest discover -s tests -p "test*.py" -t .
```

Results:

- `tests.test_attendance_inventory_integration`: 20 tests OK.
- `tests.test_attendance_inventory_effect_service`: 21 tests OK.
- `tests.test_attendance_day_entry`: 75 tests OK.
- `tests.test_inventory_service`: 20 tests OK.
- `tests.test_inventory_transactions`: 7 tests OK.
- `compileall`: completed successfully.
- Full discovery: 448 tests OK.

Note:

- Local PowerShell continues to print a user profile execution-policy warning before commands; test commands still run and pass.

## I. Caveats / Next Batch Recommendation

Recommended next batch:

1. Add diagnostics for cross-DB mismatches:
   - DONE attendance records with no matching inventory effect rows;
   - effect rows whose source attendance record no longer matches latest quantities.
2. Add an explicit retry/reconcile service or admin diagnostic action.
3. Consider a small repair tool for cases where main DB effects exist but attendance commit failed.
4. Keep backfill manual and preview-based; do not auto-backfill historical records.
