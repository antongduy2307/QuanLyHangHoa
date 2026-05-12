# Attendance Product CUT Sync - Batch 5

## A. Files Changed

- `modules/attendance/service.py`
  - Added save-time validation for newly submitted CUT `CutLog` bag types.
  - Added the same validation for BLOW extra CUT / VK `ExtraCutWorkLog` bag types.
  - Preserved existing-record bag type ids before replacing logs so historical records remain editable.
- `tests/test_attendance_day_entry.py`
  - Added focused save-time validation coverage for valid, excluded, incomplete, manual, historical, existing-record, and decimal quantity cases.
  - Updated BagType test helpers so fixture rows used for new saves are product-linked and configured unless a test is explicitly validating rejection.
- `tests/test_attendance_report.py`
  - Updated report fixtures that save new CUT/VK rows so seeded BagTypes are marked as configured product-linked rows under the Batch 5 service contract.
- `tests/test_attendance_settings.py`
  - Updated settings fixtures that save new CUT rows so seeded BagTypes are marked as configured product-linked rows under the Batch 5 service contract.
  - Adjusted the inactive historical BagType test to create history from a valid configured row before deactivating it.
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH5.md`
  - This implementation report.

## B. Save-Time Validation Rule

New CUT employee rows and BLOW extra CUT / VK rows are now accepted only when their `BagType` is valid for new attendance use:

- `is_active == true`
- `is_product_linked == true`
- `is_excluded_from_attendance == false`
- `is_legacy == false`
- `quota_quantity > 0`
- `excess_unit_price > 0`

The validation is in `AttendanceDayEntryService`, so direct service calls cannot bypass the day-entry UI filtering introduced in Batch 4.

This applies to:

- CUT employee `cut_work` payload rows.
- BLOW employee `extra_cut_work` / VK payload rows.

No attendance formulas were changed.

## C. Historical Compatibility Behavior

Before replacing a saved record's logs, the service now captures:

- existing CUT `bag_type_id` values from the original record.
- existing BLOW VK `bag_type_id` values from the original record.

If a submitted bag type id already existed in that original record, the service allows it to be saved again even when the current BagType is now inactive, legacy, excluded, manual, or incomplete.

This preserves historical record editing:

- Old CUT rows can reload and resave.
- Old BLOW VK rows can reload and resave.
- Decimal quantities remain supported.

Newly adding a different invalid BagType to an existing record is still rejected.

## D. Error Message Behavior

Invalid new CUT/VK rows raise the existing `ValidationError` type with this Vietnamese user-facing message:

`Mặt hàng cắt này chưa được cấu hình hoặc đã bị loại khỏi chấm công. Vui lòng kiểm tra Cài đặt giá chấm công.`

The service rejects invalid input before creating logs, so users get a controlled validation error rather than a low-level database error.

## E. Tests / Verification

Focused tests added or updated cover:

- New CUT save accepts a configured product-linked BagType.
- New CUT save rejects excluded BagTypes.
- New CUT save rejects zero quota.
- New CUT save rejects zero excess price.
- New CUT save rejects manual/non-product-linked BagTypes.
- New BLOW VK save uses the same validation rule.
- Historical CUT records with now-invalid BagTypes can be saved again.
- Historical BLOW VK records with now-invalid BagTypes can be saved again.
- Newly adding an invalid BagType to an existing record is rejected.
- Decimal CUT and VK quantities still save and reload for valid configured items.

Verification commands run:

- `python -m unittest tests.test_attendance_report` - passed, 23 tests.
- `python -m unittest tests.test_attendance_settings` - passed, 12 tests.
- `python -m unittest tests.test_attendance_day_entry` - passed, 75 tests.
- `python -m unittest tests.test_attendance_product_sync` - passed, 13 tests.
- `python -m unittest discover tests` - passed, 407 tests.
- `python -m compileall modules tests core shell` - passed with exit code 0.

Notes from verification:

- Full discovery still prints expected mocked diagnostics/update-service log output, including the known mocked `missing final exe` update failure trace.
- `compileall` reported transient test temp directories that could not be listed after cleanup, but exited successfully with code 0.

## F. Caveats / Next Recommendation

Batch 5 intentionally does not change:

- day-entry UI filtering
- settings UI
- popup behavior
- reports
- attendance formulas
- schema
- product/inventory logic

Recommended next batch:

- Add a small integration check around UI submit error handling if the UI currently surfaces `ValidationError` inconsistently for direct payload edge cases.
- Keep the current service validation as the source of truth for new CUT/VK BagType eligibility.
