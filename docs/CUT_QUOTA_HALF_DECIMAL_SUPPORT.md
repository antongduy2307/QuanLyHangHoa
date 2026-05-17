# CUT Quota Half-Decimal Support

## A. Files changed

- `modules/attendance/settings_service.py`
- `modules/attendance/ui/settings_tab.py`
- `tests/test_attendance_settings.py`
- `tests/test_attendance_settings_ui.py`
- `tests/test_attendance_product_sync.py`
- `tests/test_attendance_day_entry.py`
- `docs/CUT_QUOTA_HALF_DECIMAL_SUPPORT.md`

## B. Current quota storage/validation findings

- `BagType.quota_quantity` is stored as `Numeric(12, 2)`, so values such as `18.5` are already supported by the database.
- `CutLog.quota_quantity_snapshot` is also `Numeric(12, 2)`, so saved CUT records can snapshot decimal quotas.
- CUT quantities are stored separately as `Numeric(12, 3)` and were not changed.
- The settings service previously accepted any non-negative Decimal quota, including invalid values such as `18.25` or `2.7`.
- The settings dialog previously used `QSpinBox` and loaded existing quotas with `int(...)`, which truncated decimal quotas such as `18.5` to `18`.
- `calculate_cut_employee_bonus` already uses `Decimal` and supports decimal quotas without using float.

## C. Half-step decimal validation rule

CUT bag/product-linked `quota_quantity` now validates through the settings service:

- Must be greater than or equal to `0`.
- Must be an integer or `.5` half-step.
- Validation uses `Decimal` only.
- A quota is valid when `quota * Decimal("2")` is an integral value.
- Invalid half-step values raise:
  `Số lượng khoán của tổ cắt chỉ được nhập số nguyên hoặc .5.`

Examples:

- Accepted: `0`, `0.5`, `1`, `1.5`, `18`, `18.5`
- Rejected: `0.1`, `2.7`, `3.9`, `18.25`

## D. UI input behavior

- The CUT bag quota field in Attendance price settings is now a compact `QLineEdit`, not a `QSpinBox`.
- Users can type values like `18.5`.
- Existing values are normalized for display:
  - `18.00` displays as `18`
  - `18.50` displays as `18.5`
  - `0.00` displays as `0`
- Invalid text or invalid decimal steps are handled by service validation on save and shown through the existing settings error dialog path.

## E. Service/repository behavior

- Create/update BagType paths now preserve quota values as Decimal-compatible input instead of casting to int.
- No schema migration was needed.
- `excess_unit_price`, `unit_price` compatibility mirroring, and `is_excluded_from_attendance` behavior were not changed.
- Product sync still creates new linked CUT work rows with quota `0` and does not overwrite configured quotas during later syncs.

## F. CUT bonus calculation impact

- The CUT tiered bonus calculation was not changed.
- Decimal quotas such as `18.5` participate in the existing tiered logic exactly as Decimal values.
- Intermediate quota and amount calculations remain Decimal-based with no float conversion.
- Final `DailyRecord.total_amount_snapshot` storage still follows the existing app rule: final Decimal money is quantized to integer VND with `ROUND_HALF_UP` when saved.

## G. Tests/verification

Verified:

- CUT quota `18` and `18.5` can be saved and reloaded.
- CUT quota `18.25`, `2.7`, and negative values are rejected.
- The settings dialog displays `18` and `18.5` without truncation.
- Product-linked sync preserves decimal quota values.
- CUT day-entry filtering treats quota `0.5` as configured and quota `0` as incomplete.
- CUT bonus calculation accepts decimal quota and preserves existing multi-code Decimal behavior.

Commands run:

- `python -m unittest tests.test_attendance_settings tests.test_attendance_settings_ui tests.test_attendance_product_sync tests.test_attendance_day_entry tests.test_attendance_report`
- `python -m unittest discover -s tests -p "test*.py" -t .`
- `python -m compileall core modules tests shell`

All commands passed.

## H. Caveats

- This change only applies to CUT BagType quota settings.
- BLOW formulas, VK extra CUT formula, inventory effect logic, and product sync schema were intentionally not changed.
- The UI field allows typing before final validation so users receive the existing friendly save-time validation message instead of having input silently blocked or rounded.
