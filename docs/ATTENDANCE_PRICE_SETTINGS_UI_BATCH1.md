# Attendance Price Settings UI Batch 1

## A. Files Changed

- `modules/attendance/ui/settings_tab.py`
  - Added a top-level section dropdown for Attendance price settings.
  - Moved BLOW and CUT settings into a single `QStackedWidget`.
  - Removed the visible/manual CUT `Thêm` button from the settings UI.
  - Kept product sync, linked CUT row editing, incomplete highlighting, and focus behavior.
- `tests/test_attendance_settings_ui.py`
  - Added selector and CUT add-button absence coverage.
- `tests/test_attendance_settings.py`
  - Updated existing settings UI assertions for the stacked layout and removed manual CUT add expectations.

## B. CUT Add Button Removal

The CUT `Loại bao tổ cắt` section no longer constructs or displays an `add_bag_type_button`.

CUT work items now come from linked inventory products only. Existing linked rows remain editable for:

- quota quantity;
- excess unit price;
- `Không dùng cho chấm công`.

No CUT rows are deleted and no schema or sync logic was changed.

## C. Dropdown Section Switcher

`AttendancePriceSettingsTab` now has a top-left selector labeled:

`Nhóm cài đặt`

Options:

- `Công việc tổ thổi`
- `Loại bao tổ cắt`

Default selection is `Công việc tổ thổi`.

Selecting BLOW shows only the BLOW work type table and its `Thêm` button.

Selecting CUT shows only the CUT linked product table. There is no CUT add button in this section.

## D. Layout Behavior

The two large settings sections now live in a `QStackedWidget`, so only one table is visible at a time and the selected table can use the available vertical space.

`focus_first_incomplete_cut_work(...)` now switches the selector to `Loại bao tổ cắt` before selecting and scrolling to the incomplete row.

## E. Tests / Verification

Commands run:

- `python -m unittest tests.test_attendance_settings_ui`
  - Result: 8 tests passed.
- `python -m unittest tests.test_attendance_settings`
  - Result: 12 tests passed.
- `python -m unittest tests.test_attendance_product_sync`
  - Result: 14 tests passed.
- `python -m compileall core modules tests shell`
  - Result: completed successfully.
- `python -m unittest discover -s tests -p "test*.py" -t .`
  - Result: 481 tests passed.

Notes:

- PowerShell emitted the existing local profile execution-policy warning before commands; test commands still completed.
- Existing mocked diagnostics/update-service failure logs appeared during full discovery; the suite completed successfully.

## F. Caveats / Next Recommendation

- The private `_add_bag_type` method still exists in code for backward compatibility with internal service/dialog structure, but it is no longer reachable from the UI because no CUT add button is constructed.
- A future cleanup can remove the private manual CUT add method and any now-unused dialog paths after confirming no internal tests or tooling rely on them.
