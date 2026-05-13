# Attendance CUT/VK to Inventory Batch 4

## A. Files Changed

- `modules/settings/ui/page.py`
  - Added `AttendanceInventoryDiagnosticsPanel` under the Settings general tab.
  - Added explicit scan, issue display, selected-record reconcile, and refresh behavior.
  - Kept diagnostics service construction lazy to avoid import cycles during app logging/bootstrap.
- `tests/test_attendance_inventory_diagnostics_ui.py`
  - Added focused offscreen PyQt tests for the admin diagnostics panel.

## B. UI Location

The diagnostics surface was added to the existing Settings page under `Cài đặt chung` as a grouped admin section:

`Kiểm tra tồn kho từ chấm công`

This keeps the tool in an admin/maintenance area instead of the normal attendance entry workflow.

## C. Scan Behavior

The panel exposes:

- `Kiểm tra đồng bộ tồn kho chấm công`
- `Làm mới`

Both actions call `AttendanceInventoryDiagnosticService.list_issues()`.

The scan is read-only. It does not call reconcile, insert effect rows, update stock, delete stale effects, or backfill historical records.

When no issues are found, the panel shows:

`Không phát hiện lệch tồn kho từ chấm công.`

## D. Issue Display

Issues are shown in a table with:

- `Ngày`
- `Nhân viên`
- `Loại lỗi`
- `Mức độ`
- `Mô tả`
- `Dữ liệu mong đợi`
- `Dữ liệu hiện tại`

Issue type labels are mapped to Vietnamese:

- `MISSING_EFFECTS_FOR_DONE_RECORD`: `Thiếu cập nhật tồn kho`
- `STALE_EFFECTS_FOR_DRAFT_OR_ABSENT_RECORD`: `Tồn kho còn hiệu lực cho bản ghi không còn chốt`
- `STALE_EFFECTS_FOR_MISSING_DAILY_RECORD`: `Hiệu lực tồn kho không còn bản ghi chấm công`
- `QUANTITY_MISMATCH`: `Lệch số lượng`
- `PRODUCT_MISMATCH`: `Lệch mã hàng`
- `MISSING_PRODUCT_LINK`: `Thiếu liên kết hàng hóa`
- `MISSING_MAIN_PRODUCT`: `Không tìm thấy hàng hóa`

Severity is displayed as plain text.

## E. Reconcile Behavior

The selected-row action is:

`Đồng bộ lại bản ghi này`

For issues with a valid `daily_record_id`, the panel asks confirmation:

`Bạn có chắc muốn đồng bộ lại tồn kho cho bản ghi chấm công này không?`

On confirmation, it calls:

`AttendanceInventoryDiagnosticService.reconcile_daily_record(daily_record_id)`

On success, it shows a success message and refreshes the issue list.

On failure, it shows a user-facing error and leaves the issue list available.

## F. Missing-Source Behavior

For `STALE_EFFECTS_FOR_MISSING_DAILY_RECORD`, the reconcile button is disabled.

The UI does not attempt missing-source cleanup, deletion, or rollback. That remains intentionally out of scope until an explicit cleanup design is requested.

## G. Safety Guarantees

- No automatic backfill.
- No automatic reconcile on startup.
- No automatic reconcile when entering Attendance.
- No bulk reconcile action.
- Scan is read-only.
- Repair is selected-record-only and confirmation-gated.
- No change to attendance formulas.
- No change to `save_attendance` flow.
- No change to sales, returns, customers, or orders.

## H. Tests / Verification

Commands run:

- `python -m unittest tests.test_attendance_inventory_diagnostics_ui`
  - Result: 9 tests passed.
- `python -m unittest tests.test_attendance_inventory_diagnostics`
  - Result: 17 tests passed.
- `python -m unittest tests.test_settings_backup`
  - Result: 4 tests passed.
- `python -m compileall core modules tests shell`
  - Result: completed successfully.
- `python -m unittest discover -s tests -p "test*.py" -t .`
  - Result: 474 tests passed.

Notes:

- PowerShell emitted the existing local profile execution-policy warning before commands; the Python test and compile commands still completed.
- Existing update-service mocked failure logs appeared during full discovery; the suite completed successfully.

## I. Caveats / Next Recommendation

- There is still no missing-source cleanup action. That should remain a separate explicit admin operation if needed.
- There is no bulk reconcile action. Keeping repair selected-record-only is safer for V1.
- A future batch could add an admin-only export of diagnostic issues or a dedicated maintenance guide section, but runtime behavior is complete for this batch.
