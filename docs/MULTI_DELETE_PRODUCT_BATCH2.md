# Multi-Delete Product Batch 2

## A. Files Changed

- `modules/inventory/ui/product_list_view.py`
- `tests/test_product_search_ui.py`
- `docs/MULTI_DELETE_PRODUCT_BATCH2.md`

## B. Product Selection Mode Behavior

`ProductListView` now reuses `shared.widgets.table_selection_mode.TableSelectionModeController`.

Normal mode:

- Product search, suggestion selection, create, edit, receipt, adjustment, refresh, and inactive filter remain available.
- `Xóa` enters explicit delete selection mode instead of immediately deleting the current row.

Selection mode:

- A checkbox column is inserted at the left of the product table.
- Existing product columns shift right.
- `Xóa đã chọn`, `Hủy`, and `Đã chọn: N` are shown.
- Create/edit/receipt/adjustment/delete normal controls are hidden while selecting.
- Double-click edit is ignored while selection mode is active.
- The selected count updates as checkboxes are toggled.

## C. Pre-Confirm Delete/Deactivate Summary

Before deleting anything, the UI calls:

`InventoryController.get_delete_mode(product_id)`

for each selected product id.

The confirmation explains:

- total selected products;
- how many products have no history and will be hard-deleted;
- how many products have history and will be deactivated;
- first several selected product names;
- any products whose delete mode could not be determined.

No product is deleted before this confirmation.

## D. Delete Execution / Result Summary

After confirmation, the UI calls:

`InventoryController.delete_product(product_id)`

once per selected product id. It does not use bulk SQL and does not duplicate product delete rules in the UI.

The result summary reports:

- hard-deleted count;
- deactivated count;
- failed count plus first error details.

If one product fails, the UI continues processing the remaining selected products and then shows a partial-failure warning.

## E. Filter/Search Behavior

For V1, any search text or include-inactive filter change exits delete selection mode and clears selected ids before rerendering.

This avoids hidden selected products after filtering.

## F. Attendance Sync Impact

The product UI does not manually update attendance `BagType` rows.

Product deletion/deactivation remains handled by the existing inventory service/controller. Existing `AttendanceProductSyncService` will pick up inactive/deleted products on the next attendance sync trigger, such as opening Attendance or Attendance price settings.

## G. Tests/Verification

Added product UI tests in `tests/test_product_search_ui.py` for:

- product list construction through existing tests;
- delete button entering selection mode;
- checkbox column display;
- selected count updates;
- cancel exits selection mode;
- preview summary calling `get_delete_mode(...)` for selected ids;
- mixed hard-delete/deactivate summary;
- confirmed delete calling `delete_product(...)` for selected ids;
- partial failure summary without crashing;
- search/filter change exiting selection mode.

Verification run:

- `python -m unittest tests.test_inventory_service` - passed, 25 tests.
- `python -m unittest tests.test_product_search_ui` - passed, 8 tests.
- `python -m unittest tests.test_attendance_product_sync` - passed, 14 tests.
- `python -m unittest discover -s tests -p "test*.py" -t .` - passed, 489 tests.
- `python -m compileall core modules tests shell` - passed.

## H. Caveats / Next Recommendation

- This batch does not add multi-delete to `Lịch sử`.
- Sales/history deletion remains deferred because invoice, return, and debt-payment rows have stock/debt rollback ordering risks.
- A future history batch should design atomicity, ordering, and partial-failure behavior before implementation.
