# BLOW Decimal Quantity Implementation

## Summary of changes

- Enabled Decimal quantities for regular BLOW numeric work logs using `Numeric(12, 3)`.
- Added half-step validation for BLOW numeric work: zero is skipped, negative values are rejected, and non-`0.5` increments are rejected.
- Kept BLOW tick work unchanged: checkbox UI, stored quantity `1`, fixed unit-price amount when checked.
- Updated BLOW amount calculation to use Decimal math and integer money snapshots with `ROUND_HALF_UP`.
- Replaced BLOW numeric day-entry inputs with a half-step Decimal input while leaving tick rows as checkboxes.
- Updated BLOW monthly report aggregation so decimal quantities are not truncated.
- Added an idempotent SQLite rebuild migration for existing `work_logs.quantity INTEGER` databases.

## Files changed

- `modules/attendance/models.py`
- `modules/attendance/db.py`
- `modules/attendance/dto.py`
- `modules/attendance/service.py`
- `modules/attendance/blow_work.py`
- `modules/attendance/ui/day_entry_tab.py`
- `modules/attendance/report_service.py`
- `tests/test_attendance_day_entry.py`
- `tests/test_attendance_batch1.py`
- `tests/test_attendance_report.py`

## Migration notes

Existing installed `attendance.db` files may have `work_logs.quantity` declared as `INTEGER`. The new migration checks the column type and rebuilds `work_logs` only when needed:

- creates `work_logs_new` with `quantity NUMERIC(12, 3) NOT NULL`;
- preserves rows, primary key, foreign keys, unique constraint, and non-negative money checks;
- updates the quantity check to `quantity >= 0.5`;
- renames the rebuilt table back to `work_logs`;
- safely no-ops on repeated runs once the column is already NUMERIC.

Existing integer rows copy cleanly and continue to load as natural quantities such as `5`.

## Tests run and results

- `python -m unittest tests.test_attendance_day_entry tests.test_attendance_batch1 tests.test_attendance_report`
  - Passed: 113 tests.
- `python -m unittest discover -s tests -p "test*.py" -t .`
  - Passed: 501 tests.
- `python -m compileall core modules tests shell`
  - Passed.

## Remaining caveats

- SQLite `NUMERIC(12, 3)` uses type affinity and does not enforce scale by itself; validation is enforced in service/UI code.
- Decimal input validation is scoped to regular BLOW numeric work only. CUT/VK behavior was intentionally left unchanged.
