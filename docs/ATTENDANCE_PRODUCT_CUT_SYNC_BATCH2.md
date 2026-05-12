# Attendance Product CUT Sync Batch 2

Batch 2 adds Attendance Settings UI support for product-linked CUT work items. It does not add the large Attendance tab warning popup, popup navigation, day-entry filtering, report UI changes, database merging, or formula changes.

## A. Files Changed

- `modules/attendance/settings_service.py`
- `modules/attendance/ui/settings_tab.py`
- `modules/attendance/product_sync_service.py`
- `tests/test_attendance_settings.py`
- `tests/test_attendance_settings_ui.py`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH2.md`

## B. Settings Sync Trigger

`AttendancePriceSettingsTab.reload()` now runs:

```text
AttendanceProductSyncService.sync_products_to_cut_work()
```

before loading attendance price rows.

Behavior:

- sync warnings are logged;
- a small non-blocking warning banner is shown when sync returns warnings;
- settings still loads non-conflicting rows;
- sync failures are logged as nonfatal settings-load warnings;
- no large Attendance tab popup is implemented in this batch.

## C. Product-Linked Row UI

The CUT work table now includes a fourth column:

```text
Không dùng cho chấm công
```

Displayed columns:

- name/product name;
- quota quantity;
- excess unit price;
- `Không dùng cho chấm công` checkbox.

For product-linked `BagType` rows:

- names are displayed from synced product names;
- names are read-only in the edit dialog;
- name cells are marked non-editable;
- quota quantity remains editable;
- excess unit price remains editable.

`AttendanceSettingsService.update_bag_type(...)` now rejects accidental renames of product-linked rows from Attendance Settings. Product-linked names must be changed from the inventory product list.

## D. Checkbox Behavior

The checkbox text is:

```text
Không dùng cho chấm công
```

Semantics:

- checked means the product is intentionally not used for attendance;
- unchecked means the product is intended for attendance and must be configured;
- checking sets `BagType.is_excluded_from_attendance = True`;
- unchecking sets `BagType.is_excluded_from_attendance = False`;
- excluded rows are not considered incomplete.

The checkbox can be edited from the table and from the `BagTypeDialog`.

## E. Incomplete Row Highlight

Product-linked rows are highlighted with a light red background when:

```text
is_product_linked == true
AND is_active == true
AND is_excluded_from_attendance == false
AND (quota_quantity == 0 OR excess_unit_price == 0)
```

Highlight behavior:

- unchecked + quota `0` and price `0`: highlighted;
- unchecked + quota configured and price `0`: highlighted;
- unchecked + quota `0` and price configured: highlighted;
- unchecked + quota and price configured: not highlighted;
- checked `Không dùng cho chấm công`: not highlighted.

The highlight updates after editing quota/price or toggling the checkbox because the settings tab reloads after changes.

## F. Legacy / Manual Row Handling

Inactive and legacy rows remain hidden from the active settings table by default through the existing `list_bag_types(include_inactive=False)` path.

Existing manual settings tests are isolated with a no-op product sync service so legacy manual behavior remains covered separately from product-linked sync behavior.

No legacy rows are deleted by this batch.

## G. Conflict Warning Handling

Sync warnings are handled non-blockingly.

Examples:

- duplicate active product names;
- product name conflict with existing manual `BagType.name`;
- product rename conflict with another `BagType.name`.

UI behavior:

- warnings are logged;
- a small warning label appears above the CUT work table;
- other non-conflicting rows remain editable;
- no conflict resolution UI is implemented yet.

## H. Tests / Verification

Added focused UI tests in `tests/test_attendance_settings_ui.py` for:

- settings reload runs product sync and shows linked rows;
- product-linked name is read-only in dialog;
- service rejects accidental attendance-side rename of product-linked rows;
- quota and excess price edits are preserved after sync rerun;
- checkbox checked/unchecked values persist correctly;
- incomplete red highlight appears and clears under the expected conditions;
- legacy rows are hidden from the active settings table;
- duplicate product-name warnings do not block non-conflicting rows.

Updated existing settings tests for the new checkbox column while keeping legacy/manual settings behavior covered.

Verification run:

```text
python -m unittest tests.test_attendance_product_sync
python -m unittest tests.test_attendance_settings_ui
python -m unittest tests.test_settings_backup
python -m unittest tests.test_attendance_settings
python -m unittest discover tests
python -m compileall modules tests core
```

Results:

- `tests.test_attendance_product_sync`: 13 tests passed.
- `tests.test_attendance_settings_ui`: 7 tests passed.
- `tests.test_settings_backup`: 4 tests passed.
- `tests.test_attendance_settings`: 12 tests passed.
- Full discovery: 385 tests passed.
- Compileall: completed successfully.

Expected diagnostics and update-service mocked failure logs appeared during full discovery and did not fail tests.

## I. Caveats / Next Batch Recommendation

The large Attendance tab warning popup and navigation to settings are intentionally not implemented in this batch.

Recommended Batch 3:

1. Run sync when entering the large `Chấm công` tab.
2. Show warning popup when incomplete product-linked CUT work exists.
3. Add buttons `Đi tới cài đặt` and `Để sau`.
4. Navigate to `Cài đặt > Cài đặt giá chấm công` and focus/scroll the first incomplete CUT work row.

Recommended Batch 4:

1. Filter day-entry CUT and BLOW VK lists to active, product-linked, configured, non-excluded items.
2. Preserve historical inactive/legacy rows when reloading old records.
