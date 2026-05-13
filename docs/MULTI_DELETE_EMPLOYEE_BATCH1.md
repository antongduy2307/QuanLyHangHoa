# Multi-Delete Employee Batch 1

## A. Files Changed

- `shared/widgets/table_selection_mode.py`
- `modules/attendance/ui/employee_tab.py`
- `tests/test_attendance_employee_management.py`
- `docs/MULTI_DELETE_EMPLOYEE_BATCH1.md`

## B. Shared Helper Behavior

Added `TableSelectionModeController` for `QTableWidget`.

Behavior:

- Inserts a checkbox column at column 0 when selection mode starts.
- Keeps row identity by stable row id from an existing data column's `Qt.UserRole`, not by row index.
- Toggles row selection through checkbox clicks or row clicks while active.
- Tracks selected ids and reports them through `selected_ids()`.
- Calls an optional selection-changed callback with the current selected ids.
- Removes the checkbox column and clears selection on exit.
- Provides `refresh_after_table_render()` for future tables that need to reapply checkbox state after a rerender.

The helper is UI-only and does not contain delete business rules.

## C. Employee Tab UI Behavior

`EmployeeManagementTab` now uses explicit delete selection mode.

Normal mode:

- `Thêm`, `Sửa`, and `Xóa` remain the visible controls.
- `Xóa` enters selection mode when the employee table has rows.
- `Sửa` still depends on the current row selection.
- Add/edit/search/inactive-filter behavior remains unchanged outside selection mode.

Delete selection mode:

- A checkbox column appears on the left, shifting employee data columns right.
- `Thêm`, `Sửa`, and normal `Xóa` are hidden.
- `Xóa đã chọn`, `Hủy`, and `Đã chọn: N` are shown.
- The confirm button is disabled until at least one employee is selected.
- Double-click edit is ignored while selection mode is active.

## D. Delete/Deactivate Summary Behavior

Batch delete keeps the existing service rule by calling:

`AttendanceEmployeeService.delete_or_deactivate_employee(employee_id)`

once per selected employee.

Result summary:

- Counts employees hard-deleted with no history.
- Counts employees deactivated because they have attendance history.
- Continues after an individual failure and includes a failed count plus first error details.
- Emits `employees_changed` when at least one selected employee was processed successfully.

No direct SQL bulk delete was added.

## E. Search/Filter Behavior in Selection Mode

Changing search text or the inactive-employee filter exits selection mode and clears the selected ids before reloading rows.

This avoids hidden selected employees after a filter change.

## F. Tests/Verification

Added coverage in `tests/test_attendance_employee_management.py` for:

- employee tab construction through existing tests;
- delete button entering selection mode;
- checkbox column appearing;
- selected count starting at zero and updating after a checkbox is checked;
- cancel exiting selection mode and clearing selection;
- selected employees being passed through existing service delete/deactivate behavior;
- mixed hard-delete/deactivate result handling;
- per-employee failure handling without aborting the whole batch;
- `employees_changed` emission after successful batch changes;
- search/filter changes exiting selection mode.

Verification run:

- `python -m unittest tests.test_attendance_employee_management` - passed, 13 tests.
- `python -m unittest discover -s tests -p "test*.py" -t .` - passed, 485 tests.
- `python -m compileall core modules tests shell` - passed.

## G. Caveats / Next Recommendation

- This batch only applies the shared selection-mode helper to Attendance employees.
- Inventory/Hàng hóa and Lịch sử remain unchanged.
- The next safe batch is Inventory/Hàng hóa, with a preview summary for hard-delete vs deactivate.
- Lịch sử should remain deferred until transaction ordering, debt rollback, and partial-failure semantics are designed.
