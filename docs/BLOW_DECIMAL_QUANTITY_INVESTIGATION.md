# BLOW Decimal Quantity Investigation

## Summary of findings

BLOW regular work currently has several integer-only assumptions. The database model stores `WorkLog.quantity` as `Integer`; DTOs and service methods type BLOW quantities as `int`; BLOW day-entry numeric controls use `SelectAllSpinBox`, which parses and formats only integers; BLOW amount calculation accepts an `int`; and monthly BLOW reports cast numeric work quantities through `int(log.quantity)`.

CUT and BLOW extra CUT/VK already have the reusable decimal pattern:

- database quantity columns use `Numeric(12, 3)`;
- DTO/input types accept `Decimal | int | str`;
- service code normalizes through `Decimal(str(value))`;
- UI quantity widgets use `SelectAllQuantityInput`;
- report quantity formatting strips insignificant trailing zeros, so `8.500` displays as `8.5` and `8.000` displays as `8`.

Tick-based BLOW work such as `Phụ găng 1 máy` and `Phụ găng 2 máy` is separated by `WorkInputType.TICK` and should remain unchanged: UI checkbox, saved quantity `1`, amount equal to fixed unit price when checked.

Existing installed `attendance.db` files need a migration if the model changes from `INTEGER` to `NUMERIC(12, 3)`. SQLite cannot alter a column type in place, so the existing rebuild-table migration pattern used for `cut_logs.quantity` and `extra_cut_work_logs.quantity` should be reused for `work_logs.quantity`.

## Relevant files/functions/classes

### SQLAlchemy model/schema

- `modules/attendance/models.py`
  - `WorkLog.quantity`: currently `Mapped[int] = mapped_column(Integer, nullable=False)`.
  - `WorkLog.__table_args__`: `ck_work_log_quantity_positive` requires `quantity >= 1`.
  - `CutLog.quantity`: reusable pattern, `Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)`.
  - `ExtraCutWorkLog.quantity`: reusable pattern, `Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)`.

### DB init/migration/preflight logic

- `modules/attendance/db.py`
  - `init_attendance_db()` runs `AttendanceBase.metadata.create_all()`, `_upgrade_attendance_schema()`, then seed.
  - `_upgrade_attendance_schema()` currently upgrades `bag_types`, `cut_logs`, and `extra_cut_work_logs`, but not `work_logs`.
  - `_rebuild_cut_logs_quantity_if_needed()` and `_rebuild_extra_cut_work_logs_quantity_if_needed()` are the existing table-rebuild pattern to copy data into a new table with `NUMERIC(12, 3)`.
  - `_column_type()` and `_table_column_info()` already support idempotent type checks.

### Repository/service/controller logic

- `modules/attendance/dto.py`
  - `WorkLogValue.quantity: int`.
  - `BlowWorkInput.quantity: int | None`.
  - `CutWorkInput.quantity: Decimal | int | str` and `ExtraCutWorkInput.quantity: Decimal | int | str` are reusable patterns.
- `modules/attendance/service.py`
  - `AttendanceDayEntryService.get_day_entry()` maps `WorkLog.quantity` into `WorkLogValue`.
  - `_apply_blow_payload()` passes BLOW quantity into `calculate_blow_work_amount()` and appends `WorkLog(quantity=quantity, ...)`.
  - `_resolve_work_quantity(input_type, quantity)` currently accepts/returns `int`, checks `quantity < 0`, returns `1` for ticks, and skips zero at caller level.
  - `_quantity_to_decimal()` is already used for CUT/VK and can be reused or generalized for BLOW numeric work.

### BLOW calculation code

- `modules/attendance/blow_work.py`
  - `calculate_blow_work_amount(input_type, quantity: int, unit_price, work_type_name) -> int`.
  - `BLOW_QUANTITY_WORK_QUOTA = 3`.
  - `is_blow_quantity_quota_work()` identifies `Thừa máy`.
  - Current formulas match the required behavior, but decimal support requires Decimal-safe math and final amount conversion to `int` where snapshots remain integer money.

### Day-entry UI widgets/validators/parsing

- `modules/attendance/ui/day_entry_tab.py`
  - `_blow_controls`: currently stores `SelectAllSpinBox` for numeric BLOW work.
  - `_build_blow_form()` creates `SelectAllSpinBox`, `setRange(0, 100000)`, and reloads `log.quantity`.
  - `_collect_payload()` reads `spinbox.value()` for BLOW numeric work and emits `BlowWorkInput`.
  - `_update_total_preview()` reads `spinbox.value()` and calls `calculate_blow_work_amount()`.
  - `_add_cut_bag_row()` and `_add_extra_cut_bag_row()` show the reusable `SelectAllQuantityInput` pattern.
- `shared/widgets/numeric_inputs.py`
  - `SelectAllSpinBox`: integer-only `int()` parser/formatter.
  - `SelectAllDecimalInput`: decimal parser/validator.
  - `SelectAllQuantityInput`: decimal quantity formatter, quantizes to 3 decimals and strips trailing zeros.

### Attendance reports formatting

- `modules/attendance/report_service.py`
  - `_work_values_for_record()` returns `log.quantity` for BLOW numeric work and formats Decimal values naturally in `_format_work_value()`. This path will work once `log.quantity` is Decimal.
  - `_monthly_values_for_record()` currently does `int(log.quantity)` for BLOW numeric work. This would truncate `8.5` to `8` and must change.
  - `_format_quantity()` already formats `Decimal | int` naturally.
  - `_format_monthly_detail_value()` delegates non-VK values to `_format_quantity()`.

### Tests likely requiring changes/additions

- `tests/test_attendance_day_entry.py`
  - `BlowWorkCalculationTestCase` currently covers integer BLOW formulas.
  - BLOW UI tests currently assert numeric BLOW controls are `SelectAllSpinBox`.
  - CUT/VK tests already prove decimal save/reload patterns.
- `tests/test_attendance_report.py`
  - BLOW report tests currently use integer quantities.
  - CUT report tests already cover natural decimal display.
  - BLOW monthly report currently expects integer summed quantities.
- `tests/test_attendance_batch1.py`
  - Init/schema test checks `cut_logs.quantity` and `extra_cut_work_logs.quantity` are NUMERIC. It should also check `work_logs.quantity`.
- Existing schema/migration tests may need a new migration-focused case that creates an old `work_logs.quantity INTEGER` table and verifies upgrade to NUMERIC while preserving rows.

## CUT/VK decimal implementation patterns to reuse

Recommended reuse points:

- Store decimal quantities as `Numeric(12, 3)` in SQLAlchemy models.
- Accept quantity inputs as `Decimal | int | str` in DTOs.
- Convert through `Decimal(str(value))`, not `float`.
- Validate non-negative quantities in service; skip zero values before creating logs.
- Use `SelectAllQuantityInput` for day-entry quantity widgets.
- Use natural report formatting through `AttendanceReportService._format_quantity()` or the shared `format_quantity()` helper.
- Keep money snapshots as `int` and round Decimal money through the existing `ROUND_HALF_UP` helper style if fractional money can occur.

## Migration/compatibility risks

A migration is required for existing installed Windows builds because existing `attendance.db` files have `work_logs.quantity INTEGER`. Updating only the model would affect new databases but would not change existing SQLite column type or constraints.

Smallest backward-compatible migration strategy:

1. Add `_rebuild_work_logs_quantity_if_needed(connection)` in `modules/attendance/db.py`.
2. In `_upgrade_attendance_schema()`, call it after the current `work_logs` table is known to exist.
3. Check `_column_type(connection, "work_logs", "quantity")`; return if it already contains `NUMERIC`.
4. Disable foreign keys temporarily, create `work_logs_new` with the same columns/constraints but `quantity NUMERIC(12, 3) NOT NULL`, copy all rows, drop old `work_logs`, rename the new table, then re-enable foreign keys.
5. Preserve the existing uniqueness and check constraints:
   - `uq_work_log_daily_work_type`;
   - `ck_work_log_quantity_positive CHECK (quantity >= 1)`;
   - unit price and amount non-negative checks;
   - foreign keys to `daily_records` and `work_types`.

SQLite limitations/risk areas:

- SQLite cannot directly alter an existing column type, so a table rebuild is required.
- Rebuilding drops indexes/triggers unless explicitly recreated. `work_logs` currently has constraints but no separate custom indexes found; still verify with `PRAGMA index_list(work_logs)` when implementing.
- `PRAGMA foreign_keys=OFF` inside a transaction can be subtle. The existing CUT/VK rebuild functions already use this approach, so BLOW should follow the same local pattern for consistency.
- SQLite type affinity is permissive. Declaring `NUMERIC(12, 3)` does not enforce scale by itself; SQLAlchemy Decimal handling and UI/service validation are the real safeguards.
- Existing integer values copy cleanly into NUMERIC and should load as `Decimal("5.000")` or equivalent SQLAlchemy Decimal values after migration.
- The positive check `quantity >= 1` means decimal values below 1 remain invalid for regular BLOW work logs. That matches current behavior if numeric BLOW work should still require at least one unit after zero is skipped. If values like `0.5` should be valid later, this check would need a separate business decision.

## Recommended implementation plan in small steps

1. Update the data contract:
   - change `WorkLog.quantity` to `Decimal` / `Numeric(12, 3)`;
   - change `WorkLogValue.quantity` to `Decimal`;
   - change `BlowWorkInput.quantity` to `Decimal | int | str | None`.

2. Add the migration:
   - implement `_rebuild_work_logs_quantity_if_needed()` by mirroring the CUT/VK rebuild style;
   - call it from `_upgrade_attendance_schema()`;
   - add focused schema/migration coverage for old INTEGER `work_logs.quantity`.

3. Make BLOW service decimal-safe:
   - update `_resolve_work_quantity()` to return `Decimal` for quantity work and `Decimal("1")` or `1` for tick work as appropriate;
   - reuse `_quantity_to_decimal()`;
   - keep zero skip behavior and negative validation;
   - keep tick behavior unchanged.

4. Make BLOW amount calculation decimal-safe:
   - accept `Decimal | int | str`;
   - for `Thừa máy`, compute `max(Decimal("0"), quantity - Decimal("3")) * unit_price`;
   - for other numeric work, compute `quantity * unit_price`;
   - convert money to integer snapshot using the same `ROUND_HALF_UP` approach used elsewhere if the product can be fractional.

5. Update BLOW day-entry UI:
   - replace only numeric BLOW `SelectAllSpinBox` controls with `SelectAllQuantityInput`;
   - leave tick work as `QCheckBox`;
   - adjust `_blow_controls` typing and tests;
   - keep natural formatting from `SelectAllQuantityInput`, so `8.5` displays as `8.5`.

6. Update reports:
   - remove `int(log.quantity)` for BLOW monthly numeric quantities;
   - sum BLOW numeric values as Decimal and format through `_format_quantity()`;
   - leave tick and VK money report behavior unchanged.

7. Run focused tests first, then broader attendance tests:
   - BLOW calculation tests;
   - day-entry save/reload/UI tests;
   - attendance report tests;
   - schema/init/migration tests;
   - then the existing attendance test subset.

## Recommended focused tests after implementation

### Calculation/service

- Numeric BLOW work with quantity `8.5` and unit price `30,000` saves amount `255,000`.
- `Thừa máy` with quantity `8.5` and unit price `80,000` saves amount `(8.5 - 3) * 80,000 = 440,000`.
- `Thừa máy` with quantity `2.5` saves amount `0`.
- Tick work with quantity `None` still saves a single `WorkLog` quantity of `1` and fixed amount equal to `unit_price`.
- Both glove tick work types selected together still fail the existing exclusivity validation.
- Old integer quantity payloads such as `5` still save and reload.

### Persistence/migration

- New database schema has `work_logs.quantity` as NUMERIC.
- Upgrade of an old `attendance.db` with `work_logs.quantity INTEGER` rebuilds to NUMERIC and preserves existing rows, amounts, unique constraint, and foreign keys.
- Saved BLOW quantity `8.5` reloads from `AttendanceDayEntryService.get_day_entry()` as Decimal-preserving data.
- Historical integer BLOW rows reload and display as `5`, not `5.0` or `5.000`.

### UI

- Numeric BLOW rows use `SelectAllQuantityInput` and accept `8.5`.
- Invalid text in the BLOW decimal input does not crash and preserves the previous valid value, matching CUT behavior.
- Tick BLOW rows remain checkboxes and are not changed to decimal inputs.
- Total preview updates correctly for `8.5` normal BLOW quantity.
- Total preview updates correctly for `8.5` `Thừa máy`.

### Reports

- 10-day BLOW report displays numeric quantity `8.5` naturally.
- Monthly BLOW report sums decimal numeric quantities, for example `8.5 + 1.25 = 9.75`.
- Monthly BLOW report does not truncate decimal quantities through `int()`.
- Tick columns still display/sum as `1`.
- VK money columns remain money-formatted and unchanged.
