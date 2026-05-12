# Attendance Product CUT Sync Batch 4

Batch 4 adds day-entry filtering for CUT work selection. It does not change reports, formulas, schema, product/inventory logic, or unrelated sales/customer/order modules.

## A. Files Changed

- `modules/attendance/dto.py`
- `modules/attendance/repository.py`
- `modules/attendance/service.py`
- `modules/attendance/ui/day_entry_tab.py`
- `tests/test_attendance_day_entry.py`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH4.md`

## B. Day-Entry Filtering Rule

New CUT work selection/search now includes only `BagType` rows matching:

```text
is_active == true
AND is_product_linked == true
AND is_excluded_from_attendance == false
AND is_legacy == false
AND quota_quantity > 0
AND excess_unit_price > 0
```

The repository applies this rule in `AttendanceDayEntryRepository.list_bag_types_for_entry(...)`.

The UI also applies the same rule in `AttendanceDayEntryTab._available_cut_bag_types(...)` so historical rows included for reload do not appear in new search suggestions.

## C. CUT Employee Behavior

For CUT employees:

- configured product-linked CUT work appears in new search/add flows;
- excluded rows are hidden;
- incomplete quota rows are hidden;
- incomplete price rows are hidden;
- manual/non-product-linked rows are hidden;
- legacy rows are hidden;
- searches for hidden rows return no result and do not crash.

CUT formula behavior is unchanged.

## D. BLOW VK Behavior

BLOW extra CUT / VK uses the same filtered `BagType` list.

Configured product-linked rows are visible. Excluded, incomplete, inactive, manual, and legacy rows are hidden from new VK selection.

VK calculation remains unchanged:

```text
amount = quantity * excess_unit_price_snapshot
```

No CUT employee tiered formula is applied to VK.

## E. Historical Reload Behavior

Existing saved record ids are still included through the existing `include_ids` path.

This preserves reload/edit display for old rows even when their current `BagType` is:

- inactive;
- legacy/manual;
- excluded from attendance;
- incomplete;
- product-linked but later deactivated.

`AttendanceDayEntryService.save_attendance(...)` now allows unchanged historical inactive CUT/VK bag rows to be saved again when those ids were already present in the loaded record. This avoids breaking old record editing while keeping new selection filtered in the UI.

## F. Decimal Quantity Preservation

Decimal quantity support remains unchanged.

Verified cases:

- CUT quantity `10.5` saves/reloads as Decimal.
- BLOW VK quantity `4.25` saves/reloads as Decimal.
- VK amount for `4.25 * 3,500` remains `14,875`.

No int casts were added to CUT/VK quantities.

## G. Tests / Verification

Updated `tests/test_attendance_day_entry.py` to cover:

- CUT available list includes configured product-linked rows;
- CUT hides excluded rows;
- CUT hides zero-quota rows;
- CUT hides zero-price rows;
- CUT hides manual/legacy rows;
- BLOW VK uses the same filter;
- CUT search hides excluded/incomplete/manual rows;
- historical CUT record reloads inactive legacy manual rows;
- historical BLOW VK record reloads inactive/excluded/legacy rows;
- historical inactive CUT/VK rows can be saved again without crashing;
- decimal CUT and VK quantities still save and reload correctly.

Verification run:

```text
python -m unittest tests.test_attendance_product_sync
python -m unittest tests.test_attendance_settings_ui
python -m unittest tests.test_app_window_attendance_sync
python -m unittest tests.test_attendance_day_entry
python -m unittest discover tests
python -m compileall modules tests core shell
```

Results:

- `tests.test_attendance_product_sync`: 13 tests passed.
- `tests.test_attendance_settings_ui`: 7 tests passed.
- `tests.test_app_window_attendance_sync`: 9 tests passed.
- `tests.test_attendance_day_entry`: 68 tests passed.
- Full discovery: 400 tests passed.
- Compileall: completed successfully.

Expected diagnostics and update-service mocked failure logs appeared during full discovery and did not fail tests.

## H. Caveats / Next Batch Recommendation

The service still permits direct programmatic saves for active incomplete/excluded product-linked rows if a caller manually constructs such a payload. Batch 4 intentionally limits enforcement to day-entry selection/search and historical inactive-row compatibility.

Recommended next batch:

1. Decide whether save-time service validation should also reject new active excluded/incomplete product-linked rows, while still allowing historical rows.
2. Add product-change event integration so sync can run immediately after inventory create/rename/deactivate instead of only on Attendance/Settings entry.
3. Consider stricter historical name snapshots if old reports must preserve pre-rename product names exactly.
