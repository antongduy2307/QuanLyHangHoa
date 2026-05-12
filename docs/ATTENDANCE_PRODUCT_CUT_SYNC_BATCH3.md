# Attendance Product CUT Sync Batch 3

Batch 3 adds the large `Chấm công` tab-entry sync and incomplete CUT work warning flow. It does not add day-entry filtering, report UI changes, formula changes, schema changes, or product/inventory business-logic changes.

## A. Files Changed

- `shell/app_window.py`
- `modules/settings/ui/page.py`
- `modules/attendance/ui/settings_tab.py`
- `tests/test_app_window_attendance_sync.py`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH3.md`

## B. Attendance Tab-Entry Sync Behavior

`AppWindow` now tracks large-tab changes through the main `NavigationTabs.currentChanged` signal.

When the user enters the large `Chấm công` tab:

1. `AttendanceProductSyncService.sync_products_to_cut_work()` runs.
2. Sync warnings are logged.
3. Sync failures are logged nonfatally.
4. The Attendance tab remains open even if sync fails.
5. The warning popup is evaluated only for incomplete product-linked CUT work returned by the sync result.

The hook is on the shell-level tab, so it does not run when switching internal Attendance subtabs.

## C. Popup Condition / Content / Buttons

Popup condition:

```text
is_product_linked == true
AND is_active == true
AND is_excluded_from_attendance == false
AND (quota_quantity == 0 OR excess_unit_price == 0)
```

No popup appears when:

- no product-linked CUT work rows are incomplete;
- all unconfigured rows are checked `Không dùng cho chấm công`;
- no products exist;
- only legacy/manual inactive rows exist.

Popup title:

```text
Thiếu cấu hình việc cắt
```

Popup body explains:

- some products were synced into CUT work but are missing quota or excess unit price;
- the user should configure quota and excess price;
- or tick `Không dùng cho chấm công` if the product is not used for attendance;
- the first few incomplete item names are listed.

Buttons:

- `Đi tới cài đặt`
- `Để sau`

`Để sau` closes the popup and leaves the user on the Attendance tab.

## D. Navigation To Settings Behavior

When the user clicks `Đi tới cài đặt`:

1. `AppWindow` switches the large tab to `Cài đặt`.
2. `SettingsPage.open_attendance_price_settings(first_incomplete_id)` opens the `Cài đặt giá chấm công` subtab.
3. `AttendancePriceSettingsTab.focus_first_incomplete_cut_work(...)` reloads settings, selects the first incomplete row, scrolls it into view, and focuses the CUT work table.

The red highlight from Batch 2 remains visible after navigation.

## E. Popup Frequency Behavior

V1 frequency:

- show when entering the large Attendance tab and incomplete rows exist;
- do not show repeatedly while the user remains in the same large Attendance tab;
- show again after the user leaves Attendance and re-enters while rows remain incomplete;
- no persistent “do not show again” setting was added.

## F. Conflict / Sync-Failure Handling

Sync warnings, such as duplicate product names, are logged and remain nonfatal.

Sync failures are logged and do not block the Attendance tab from opening.

Conflict resolution UI is intentionally not implemented in this batch. The Settings warning banner from Batch 2 remains the place where sync warnings surface in the settings area.

## G. Tests / Verification

Added `tests/test_app_window_attendance_sync.py` covering:

- entering Attendance runs product sync;
- incomplete linked rows show popup;
- configured rows do not show popup;
- excluded rows do not show popup;
- `Để sau` keeps the user on Attendance;
- `Đi tới cài đặt` switches to Settings and passes the incomplete row id;
- duplicate tab-change while already in Attendance does not repeat the popup;
- leaving and re-entering Attendance can show the popup again;
- sync failure does not crash or block the tab.

Verification run:

```text
python -m unittest tests.test_attendance_product_sync
python -m unittest tests.test_attendance_settings_ui
python -m unittest tests.test_app_window_attendance_sync
python -m unittest discover tests
python -m compileall modules tests core shell
```

Results:

- `tests.test_attendance_product_sync`: 13 tests passed.
- `tests.test_attendance_settings_ui`: 7 tests passed.
- `tests.test_app_window_attendance_sync`: 9 tests passed.
- Full discovery: 394 tests passed.
- Compileall: completed successfully.

Expected diagnostics and update-service mocked failure logs appeared during full discovery and did not fail tests.

## H. Caveats / Next Batch Recommendation

Day-entry filtering is still intentionally unchanged. Incomplete product-linked CUT work can still appear in day-entry until the next batch changes the available list.

Recommended Batch 4:

1. Filter CUT employee and BLOW VK day-entry lists to active, product-linked, configured, non-excluded rows.
2. Preserve historical inactive/legacy rows when reloading old records.
3. Add tests for new-record selection, old-record reload, excluded rows, incomplete rows, and decimal quantity behavior.
