# Attendance CUT/VK To Inventory Batch 3

Batch 3 adds cross-DB diagnostics and explicit retry/reconcile support for Attendance CUT/VK inventory effects.

This batch does not auto-backfill old records, does not auto-reconcile on startup, does not change normal save behavior, and does not add UI.

## A. Files Changed

- `modules/attendance/inventory_diagnostic_service.py`
  - Added diagnostic DTOs, issue types, read-only scan behavior, snapshot rebuild, and explicit reconcile method.
- `tests/test_attendance_inventory_diagnostics.py`
  - Added focused tests for missing/stale/mismatch detection and manual reconcile behavior.
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH3.md`
  - Added this implementation report.

## B. Diagnostic Service Behavior

Added service:

`modules.attendance.inventory_diagnostic_service.AttendanceInventoryDiagnosticService`

Main methods:

- `list_issues() -> list[AttendanceInventoryDiagnosticIssue]`
- `build_snapshot_for_daily_record(daily_record_id) -> AttendanceInventoryEffectSnapshot`
- `reconcile_daily_record(daily_record_id) -> AttendanceInventoryEffectResult`

`list_issues()` is read-only. It compares:

- current attendance `DailyRecord` / `CutLog` / `ExtraCutWorkLog` rows in `attendance.db`
- current `inventory_stock_effects` rows in the main DB

It does not mutate stock, insert effect rows, delete effect rows, or backfill anything.

`reconcile_daily_record(...)` is explicit/manual. It rebuilds a current attendance snapshot and delegates to `AttendanceInventoryEffectService.reconcile_daily_record_effects(snapshot)`.

## C. Issue Types

Added enum:

`AttendanceInventoryIssueType`

Values:

- `MISSING_EFFECTS_FOR_DONE_RECORD`
- `STALE_EFFECTS_FOR_DRAFT_OR_ABSENT_RECORD`
- `STALE_EFFECTS_FOR_MISSING_DAILY_RECORD`
- `QUANTITY_MISMATCH`
- `PRODUCT_MISMATCH`
- `MISSING_PRODUCT_LINK`
- `MISSING_MAIN_PRODUCT`

Issue DTO:

`AttendanceInventoryDiagnosticIssue`

Fields:

- `issue_type`
- `severity`
- `daily_record_id`
- `employee_id`
- `work_date`
- `message`
- `expected_lines_summary`
- `actual_effects_summary`

## D. Snapshot Rebuild Behavior

`build_snapshot_for_daily_record(daily_record_id)`:

1. Loads `DailyRecord` from attendance DB.
2. Loads `CutLog.bag_type`.
3. Loads `ExtraCutWorkLog.bag_type`.
4. Builds `AttendanceInventoryEffectSnapshot` with:
   - record id
   - employee id
   - work date
   - status
   - absent flag
   - CUT line ids, bag type ids, product ids, Decimal quantities
   - VK line ids, bag type ids, product ids, Decimal quantities

If the daily record is missing, it raises `NotFoundError`.

This helper supports DONE, DRAFT, and absent records.

## E. Missing / Stale / Mismatch Detection

Missing effects:

- DONE, non-absent records with CUT/VK lines should have effects.
- If no effects exist, the service reports `MISSING_EFFECTS_FOR_DONE_RECORD`.
- The message notes that this may be a historical pre-integration record or failed sync.

Stale effects:

- Effects whose `source_id` has no attendance `DailyRecord` produce `STALE_EFFECTS_FOR_MISSING_DAILY_RECORD`.
- Effects for DRAFT records produce `STALE_EFFECTS_FOR_DRAFT_OR_ABSENT_RECORD`.
- Effects for absent records produce `STALE_EFFECTS_FOR_DRAFT_OR_ABSENT_RECORD`.
- Effects for DONE records with no current CUT/VK production are treated as stale inactive production.

Mismatch detection:

- Expected effects are aggregated by `(product_id, unit_type)`.
- Actual `inventory_stock_effects` are aggregated by `(product_id, unit_type)`.
- Aggregate comparison avoids false positives when attendance edit flows recreate log rows and line ids change.
- Product set differences report `PRODUCT_MISMATCH`.
- Same product/unit with different quantity reports `QUANTITY_MISMATCH`.

Product/link issues:

- A production line with no `BagType.source_product_id` reports `MISSING_PRODUCT_LINK`.
- A production line whose `source_product_id` does not exist in the main DB reports `MISSING_MAIN_PRODUCT`.

## F. Reconcile / Retry Behavior

`reconcile_daily_record(daily_record_id)`:

1. Builds the current snapshot from attendance DB.
2. Calls `AttendanceInventoryEffectService.reconcile_daily_record_effects(snapshot)`.
3. Returns the effect-service result.

Expected behavior:

- DONE records apply latest effects.
- DRAFT records roll back old effects and apply none.
- Absent records roll back old effects and apply none.
- Missing daily records raise `NotFoundError`; no automatic missing-source cleanup is performed.

No bulk reconcile method was added. No startup/background reconciliation was added.

## G. What Is Intentionally Not Automatic

This batch intentionally does not:

- auto-backfill old historical DONE records;
- auto-run diagnostics at app startup;
- auto-run diagnostics when entering Attendance;
- auto-reconcile after diagnostic scan;
- delete or roll back effects whose source attendance record is missing;
- add an outbox/retry table;
- add complex UI.

For missing-source effects, automatic repair is ambiguous because the attendance source row is gone. The diagnostic reports the problem; a future explicit cleanup method can be added if needed.

## H. Tests / Verification

Added tests for:

- correct DONE effects produce no issues;
- DONE CUT/VK lines with no effects report `MISSING_EFFECTS_FOR_DONE_RECORD`;
- wrong quantity reports `QUANTITY_MISMATCH`;
- wrong product reports `PRODUCT_MISMATCH`;
- DRAFT record with effects reports stale effects;
- absent record with effects reports stale effects;
- missing daily record source reports stale missing-source effects;
- explicit reconcile fixes missing effects;
- explicit reconcile fixes quantity mismatch;
- explicit reconcile rolls back effects for DRAFT records;
- explicit reconcile rolls back effects for absent records;
- decimal quantities compare exactly;
- missing product link reports issue and reconcile raises clearly;
- missing main product reports issue and reconcile raises clearly;
- diagnostic scan does not auto-backfill or mutate stock;
- snapshot rebuild includes CUT and VK lines;
- missing daily record reconcile raises without cleanup.

Commands run:

```powershell
python -m unittest tests.test_attendance_inventory_diagnostics
python -m unittest tests.test_attendance_inventory_integration
python -m unittest tests.test_attendance_inventory_effect_service
python -m compileall core modules tests shell
python -m unittest discover -s tests -p "test*.py" -t .
```

Results:

- `tests.test_attendance_inventory_diagnostics`: 17 tests OK.
- `tests.test_attendance_inventory_integration`: 20 tests OK.
- `tests.test_attendance_inventory_effect_service`: 21 tests OK.
- `compileall`: completed successfully.
- Full discovery: 465 tests OK.

Note:

- Local PowerShell still prints the user profile execution-policy warning before commands; test commands still run and pass.

## I. Caveats / Next Recommendation

Caveats:

- Diagnostics are service-level only; no UI entry point exists yet.
- Missing-source cleanup is intentionally not implemented because deleting or reversing effects without the attendance source record is an explicit admin repair decision.
- The aggregate comparison is intentionally daily-record-level rather than strict line-id matching, because attendance edits can clear/recreate log rows and change line ids.

Recommended next batch:

1. Add a small admin/diagnostics surface that calls `list_issues()` and displays issues.
2. Add an explicit per-record "reconcile" action for selected issues.
3. Optionally add an explicit missing-source rollback method with strong confirmation and tests.
4. Keep historical backfill manual and preview-based.
