# Multi-Delete UI Investigation

## A. Files Inspected

### Inventory / Hàng hóa

- `modules/inventory/ui/product_list_view.py`
  - `ProductListView`
  - `_delete_product()`
  - `_selected_product_id()`
  - `_render_rows(...)`
- `modules/inventory/controller.py`
  - `InventoryController.get_delete_mode(...)`
  - `InventoryController.delete_product(...)`
- `modules/inventory/service.py`
  - `InventoryService.get_delete_mode(...)`
  - `InventoryService.delete_product(...)`
  - `InventoryService._has_product_history(...)`
- `tests/test_inventory_service.py`
  - product hard-delete, soft-deactivate, inactive-list, reactivation behavior
- `tests/test_product_search_ui.py`
  - inventory product list UI construction/search behavior

### Sales / Lịch sử

- `shell/history_page.py`
  - `HistoryPage`
  - creates `TransactionHistoryView`, `InvoiceListView`, `ReturnListView`, `DebtPaymentListView`
  - `reload_all_views()`
  - `open_transaction_detail(...)`
- `modules/sales/ui/transaction_history_view.py`
  - `TransactionHistoryView`
  - `_delete_transaction()`
  - `_selected_transaction()`
- `modules/sales/ui/invoice_list_view.py`
  - invoice history/list delete path
- `modules/returns/ui/return_list_view.py`
  - return history/list delete path
- `modules/customer/ui/debt_payment_list_view.py`
  - debt payment delete path
- `modules/sales/controller.py`
  - `SalesController.delete_invoice(...)`
- `modules/sales/service.py`
  - `SalesService.delete_invoice(...)`
  - `_rollback_invoice_effects(...)`
- `modules/returns/controller.py`
  - `ReturnController.delete_return_invoice(...)`
- `modules/returns/service.py`
  - `ReturnService.delete_return_invoice(...)`
  - `_rollback_return_effects(...)`
- `modules/customer/controller.py`
  - `CustomerController.delete_debt_payment(...)`
- `modules/customer/service.py`
  - `CustomerService.delete_debt_payment(...)`
  - `remove_reference_balance_effect(...)`
- `tests/test_history_delete_actions.py`
  - current single-row delete routing tests
- `tests/test_sales_service.py`
  - invoice delete rollback coverage
- `tests/test_return_service.py`
  - return delete rollback coverage
- `tests/test_customer_service.py`
  - debt payment delete rollback coverage

### Attendance / Nhân viên

- `modules/attendance/ui/employee_tab.py`
  - `EmployeeManagementTab`
  - `_delete_selected_employee()`
  - `_selected_employee()`
  - `_render_table()`
- `modules/attendance/service.py`
  - `AttendanceEmployeeService.delete_or_deactivate_employee(...)`
- `modules/attendance/repository.py`
  - `delete_employee(...)`
  - `count_daily_records(...)`
- `tests/test_attendance_employee_management.py`
  - employee hard-delete/soft-deactivate behavior

### Shared Table Infrastructure

- `shared/widgets/table_helpers.py`
  - `configure_table_widget(...)`
  - table selection behavior, no-edit behavior, resize persistence controller

## B. Current Delete Behavior Per Module

### 1. Inventory / Hàng hóa

Current UI:

- File: `modules/inventory/ui/product_list_view.py`
- Class: `ProductListView`
- Delete button: local `delete_button = QPushButton("Xóa")`
- Handler: `_delete_product()`
- Selection source: `_selected_product_id()` reads the selected table row's first-column `UserRole`.

Current flow:

1. User selects one product row.
2. UI calls `InventoryController.get_delete_mode(product_id)`.
3. UI shows one confirmation message:
   - hard delete: `Hàng hóa chưa phát sinh giao dịch. Xóa vĩnh viễn?`
   - deactivate: `Hàng hóa đã phát sinh giao dịch/chứng từ kho. Sẽ chuyển sang ngừng sử dụng thay vì xóa vĩnh viễn. Tiếp tục?`
4. UI calls `InventoryController.delete_product(product_id)`.
5. Service either hard-deletes or sets `Product.is_active = False`.

Service semantics:

- `InventoryService.get_delete_mode(product_id)` returns:
  - `hard_delete` if `_has_product_history(...)` is false.
  - `deactivate` if `_has_product_history(...)` is true.
- `InventoryService.delete_product(product_id)`:
  - hard-deletes products without history.
  - deactivates products with invoice, return, receipt, or adjustment history.

Tests:

- `tests/test_inventory_service.py`
  - `test_delete_unused_product_hard_deletes`
  - `test_delete_product_with_receipt_history_sets_inactive_false`
  - `test_delete_product_with_invoice_history_sets_inactive_false_and_keeps_snapshot`
  - `test_inactive_product_no_longer_appears_in_active_queries`

### 2. Sales / Lịch sử

Current shell:

- File: `shell/history_page.py`
- Class: `HistoryPage`
- The large `Lịch sử` page contains four subtabs:
  - `TransactionHistoryView`: `Lịch sử giao dịch`
  - `InvoiceListView`: invoice list
  - `ReturnListView`: `Lịch sử trả hàng`
  - `DebtPaymentListView`: debt payments

Current transaction history UI:

- File: `modules/sales/ui/transaction_history_view.py`
- Class: `TransactionHistoryView`
- Delete button: local `delete_button = QPushButton("Xóa")`
- Handler: `_delete_transaction()`
- Selection source: `_selected_transaction()` reads `(transaction_type, transaction_id)` from first-column `UserRole`.

Current flow in `TransactionHistoryView._delete_transaction()`:

1. User selects one transaction row.
2. UI confirms: `Xóa {type} đã chọn?`
3. Routing depends on transaction type:
   - `INVOICE`: `SalesController.delete_invoice(transaction_id)`
   - `RETURN`: constructs `ReturnController(SessionFactory)` and calls `delete_return_invoice(transaction_id)`
   - `DEBT_PAYMENT`: constructs `CustomerController(SessionFactory)` and calls `delete_debt_payment(transaction_id)`
4. On success: `MessageBox.info(..., "Đã xóa giao dịch.")`
5. Calls `_handle_history_changed()` to refresh all linked views.

Business effects:

- `SalesService.delete_invoice(...)`
  - calls `_rollback_invoice_effects(invoice)`
  - restores stock and customer ledger effects
  - deletes the invoice row
- `ReturnService.delete_return_invoice(...)`
  - calls `_rollback_return_effects(return_invoice)`
  - restores inventory/customer effects
  - deletes the return invoice row
- `CustomerService.delete_debt_payment(...)`
  - validates selected ledger is a true standalone debt payment
  - removes all balance effects for the payment reference
  - recomputes later customer balances

Tests:

- `tests/test_history_delete_actions.py`
  - verifies single-row transaction delete routes to the correct controller.
  - verifies return and debt list views have delete actions.
- `tests/test_sales_service.py`
  - invoice delete rollback and atomicity tests.
- `tests/test_return_service.py`
  - return delete rollback tests.
- `tests/test_customer_service.py`
  - debt payment delete rollback/recompute tests.

Assessment:

`Lịch sử` delete is safe only as a carefully ordered, per-record service operation. Batch delete is high-risk because each row may alter stock, customer debt, generated debt payment rows, and downstream balance snapshots.

### 3. Attendance / Nhân viên

Current UI:

- File: `modules/attendance/ui/employee_tab.py`
- Class: `EmployeeManagementTab`
- Delete button: `self.delete_button = QPushButton("Xóa")`
- Handler: `_delete_selected_employee()`
- Selection source: `_selected_employee()` from current table row.

Current flow:

1. User selects one employee row.
2. UI confirms:
   - `Bạn có chắc muốn xóa nhân viên '{employee.name}' không?`
3. UI calls `AttendanceEmployeeService.delete_or_deactivate_employee(employee.id)`.
4. Service either:
   - hard-deletes employee with no daily records.
   - sets `employee.is_active = False` if history exists.

Service semantics:

- `AttendanceEmployeeService.delete_or_deactivate_employee(employee_id)`:
  - checks `AttendanceRepository.count_daily_records(...)`.
  - deletes employee with no history.
  - deactivates employee with history.
  - returns `EmployeeDeleteResult(employee_id, employee_name, deleted_without_history)`.

Tests:

- `tests/test_attendance_employee_management.py`
  - `test_delete_employee_without_history_hard_deletes`
  - `test_delete_employee_with_history_deactivates`
  - UI presence test through `AttendancePage`

## C. Risks

### 1. Batch Deleting Products With History

Risks:

- Mixed action types in one selection: some products hard-delete, others deactivate.
- Product rows may be linked to attendance `BagType.source_product_id`.
- Hard-deleting unused products is safe only if service history detection is complete.
- Users need a confirmation summary showing how many selected rows will be permanently deleted vs deactivated.

Mitigation:

- Keep calling `InventoryService.delete_product(...)` per product.
- Before final confirmation, call `get_delete_mode(...)` per selected id and summarize:
  - `X sản phẩm sẽ bị xóa vĩnh viễn`
  - `Y sản phẩm sẽ chuyển sang ngừng sử dụng`
- Do not create a bulk SQL delete.

### 2. Batch Deleting Invoices / Returns / History Entries

Risks:

- Invoices alter stock and customer debt.
- Returns alter stock and customer credit/refund behavior.
- Debt payments alter customer balance ledgers and require later snapshot recompute.
- Mixed transaction types in one table means multiple controllers/services and different rollback rules.
- Ordering matters if selected transactions belong to the same customer or same product timeline.
- Partial failure can leave earlier selected rows deleted while later rows fail unless a single main DB transaction is designed across all selected operations.
- Existing `TransactionHistoryView` creates separate controllers for return and debt payment delete, making a cross-type transaction boundary nontrivial.

Recommendation:

- Defer `Lịch sử` multi-delete from V1.
- Implement only after a separate high-risk design batch that defines:
  - transaction ordering;
  - same-customer balance recompute behavior;
  - cross-type rollback/atomicity strategy;
  - partial success UX;
  - service-level bulk delete or shared-session orchestration.

### 3. Batch Deleting Attendance Employees With History

Risks:

- Mixed action types: no-history employees hard-delete, history employees deactivate.
- Deactivating many employees affects day-entry employee lists.
- Existing reports should still include historical records.

Mitigation:

- This is the safest first target.
- Keep service-level `delete_or_deactivate_employee(...)` per employee.
- Confirmation summary can show selected count and first few names.
- Result summary can show hard-deleted vs deactivated counts.

### 4. UI Accidental Deletion Risk

Risks:

- Multi-select checkboxes make it easy to delete more than intended.
- Row double-click edit conflicts with selection mode.
- Existing single selection state could remain active and confuse users.

Mitigation:

- Use explicit selection mode.
- Change the delete button into a mode entry button, not immediate delete.
- Require checkbox selection plus explicit `Xóa đã chọn`.
- Disable edit/double-click in selection mode or make double-click only toggle checkbox.
- Always show selected count.
- Always confirm with count and sample names.

### 5. Partial Success / Error Handling

Risks:

- Per-row service calls can fail halfway through.
- Full atomicity may be unnecessary for products/employees but important for history.

Mitigation for V1:

- Products/employees: allow partial success, collect results, then show summary:
  - hard-deleted count;
  - deactivated count;
  - failed count and first few error messages.
- History: defer until atomicity is designed.

### 6. Preserve Service-Level Rules

Do not move delete rules into UI. UI should only:

- collect selected ids;
- show a preview/summary;
- call the existing module service/controller methods;
- display results.

## D. Recommended Reusable UI Pattern

### Recommended Option: Add a Checkbox Column to Existing `QTableWidget`

This best matches the current codebase because the target tables are `QTableWidget`, not model-backed `QTableView` with custom proxy models.

Behavior:

1. User clicks a mode button, for example:
   - normal: `Xóa`
   - selection mode: show `Xóa đã chọn`, `Hủy`, and selected count.
2. Table enters delete selection mode.
3. A checkbox column is inserted or shown at column 0.
4. Existing data columns shift right automatically.
5. Each visible row gets a checkbox item/cell.
6. Normal edit/double-click actions are disabled or repurposed while in selection mode.
7. User selects multiple rows.
8. Selected count updates:
   - `Đã chọn: N`
9. User clicks `Xóa đã chọn`.
10. UI confirms with count and first few display names.
11. Module-specific delete adapter deletes/deactivates selected ids.
12. UI exits selection mode after success or cancel.

Why not a separate checkbox list:

- Harder to keep aligned with sorted/filtered table rows.
- More layout code per screen.

Why not Qt row selection only:

- Less explicit and easier to trigger accidental deletes.
- Does not satisfy the desired checkbox-column interaction.

Why not proxy model selection:

- Current target screens are simple `QTableWidget` implementations.
- A proxy-model design would require larger rewrites before the feature itself.

### Proposed Reusable Helper

Create a shared helper in a later implementation batch, for example:

`shared/widgets/table_selection_mode.py`

Suggested class:

`TableSelectionModeController`

Constructor inputs:

- `table: QTableWidget`
- `id_column: int`
- `id_role: Qt.ItemDataRole = UserRole`
- `name_getter: Callable[[int], str] | None`
- `on_mode_changed: Callable[[bool], None] | None`
- `on_selection_changed: Callable[[set[int]], None] | None`

Core methods:

- `enter()`
- `exit(clear=True)`
- `is_active`
- `selected_ids() -> list[int]`
- `selected_rows() -> list[int]`
- `set_rows_selectable(...)`
- `refresh_after_table_render()`

Important implementation detail:

- Tables are re-rendered on filter/reload. The helper should preserve selected ids across re-render where possible, then reapply checkbox states.
- Avoid storing row indexes as the source of truth. Store ids.

Recommended UI controls per module:

- Primary mode button: `Chọn để xóa`
- In mode:
  - `Xóa đã chọn`
  - `Hủy`
  - label `Đã chọn: N`

Confirmation content:

- `Bạn có chắc muốn xóa {N} mục đã chọn không?`
- Show first 5 names.
- For products/employees, include action summary if known:
  - hard-delete count
  - deactivate count

## E. Recommended Implementation Batches

### Batch A: Shared Helper + Attendance Employee Tab

Why first:

- Employee delete semantics are simple.
- Same attendance DB only.
- Existing service already returns hard-delete vs deactivate result.
- Lower blast radius than product/history.

Module strategy:

- UI file: `modules/attendance/ui/employee_tab.py`
- Table: `self.table`
- Row id source: first column `UserRole` contains `employee.id`
- Display name source: `Employee.name` or first table column text
- Delete service method:
  - `AttendanceEmployeeService.delete_or_deactivate_employee(employee_id)`
- Expected result message:
  - `Đã xóa {X} nhân viên.`
  - `Đã chuyển {Y} nhân viên sang ngừng sử dụng.`
  - Include failures if any.
- Partial failure:
  - continue per selected employee or stop on first failure. Recommendation: continue and summarize failures because employee deletes are independent.

Tests:

- selection mode enters/exits;
- checkbox column appears;
- selected count updates;
- cancel clears selection;
- service called for selected ids;
- hard-delete/deactivate counts summarized;
- normal edit double-click still works outside selection mode.

### Batch B: Apply Shared Helper to Inventory / Hàng hóa

Module strategy:

- UI file: `modules/inventory/ui/product_list_view.py`
- Table: `self._table`
- Row id source: first column `UserRole` contains `product.id`
- Display name source: product name column
- Delete service/controller methods:
  - `InventoryController.get_delete_mode(product_id)`
  - `InventoryController.delete_product(product_id)`
- Pre-confirm summary:
  - call `get_delete_mode(...)` for selected ids.
  - summarize permanent delete vs deactivate.
- Expected result message:
  - `Đã xóa vĩnh viễn {X} hàng hóa chưa phát sinh.`
  - `Đã chuyển {Y} hàng hóa sang ngừng sử dụng.`
- Partial failure:
  - continue and summarize, because product deletes/deactivations are independent at service level.

Additional care:

- Product list has search/filter and include-inactive toggle; selection should survive filtering only if ids remain visible or should clear on filter changes. Recommendation for V1: clear selection when filter/include-inactive changes while in selection mode, or exit mode on reload to avoid hidden selected rows.

### Batch C: Defer or Separately Design Lịch sử Multi-Delete

Recommendation:

- Do not include `Lịch sử` in the first reusable helper rollout beyond making the helper technically reusable.
- Add a dedicated design/implementation batch only if the user approves the higher risk.

If implemented later:

- Row id source:
  - `TransactionHistoryView`: first column `UserRole` stores `(transaction_type, transaction_id)`
  - `InvoiceListView`: invoice id
  - `ReturnListView`: return id
  - `DebtPaymentListView`: ledger id
- Display name source:
  - transaction type + customer/date/amount
- Delete service methods:
  - invoice: `SalesController.delete_invoice(...)`
  - return: `ReturnController.delete_return_invoice(...)`
  - debt payment: `CustomerController.delete_debt_payment(...)`
- Required design before code:
  - whether to allow mixed transaction types in one batch;
  - whether to sort operations oldest/newest or by selected row order;
  - whether to use one shared SQLAlchemy session/transaction for all selected main DB changes;
  - how to report partial failures;
  - how to recompute customer balances if multiple debt-affecting rows for the same customer are deleted.

## F. Test Plan

### Shared Selection Mode Helper

1. Enter selection mode:
   - checkbox column appears.
   - existing data columns shift right.
   - selected count starts at 0.
2. Exit selection mode:
   - checkbox column disappears.
   - selected ids clear.
   - normal table behavior returns.
3. Toggle row checkboxes:
   - selected ids update.
   - selected count updates.
4. Reload/re-render while active:
   - either selected ids are preserved for visible rows or cleared consistently, depending on chosen V1 behavior.
5. Double-click behavior:
   - outside selection mode, existing edit/detail behavior still works.
   - inside selection mode, double-click does not open edit/detail unexpectedly.

### Attendance Employees

1. Selection mode enters/exits in `EmployeeManagementTab`.
2. Checkbox column aligns with employee rows.
3. Cancel clears employee selections.
4. Confirm delete calls `delete_or_deactivate_employee(...)` for selected ids.
5. Employee without history is hard-deleted.
6. Employee with history is deactivated.
7. Mixed selection shows hard-deleted/deactivated summary.
8. Partial failure shows summary and does not crash.
9. `employees_changed` emits after successful batch changes.
10. Normal add/edit/single-row behavior still works outside selection mode.

### Inventory Products

1. Selection mode enters/exits in `ProductListView`.
2. Checkbox column aligns with filtered product rows.
3. Pre-confirm summary distinguishes hard delete vs deactivate using `get_delete_mode(...)`.
4. Product without history hard-deletes.
5. Product with invoice/return/receipt/adjustment history deactivates.
6. Mixed selection shows correct summary.
7. Partial failure shows failed products and preserves successful operations.
8. Search/filter/include-inactive behavior does not leave hidden selected rows in an ambiguous state.
9. Normal create/edit/receipt/adjustment behavior still works outside selection mode.

### Lịch sử

Only after separate approval:

1. Transaction history selection supports mixed row payloads safely.
2. Invoice delete restores stock/customer effects.
3. Return delete restores stock/customer effects.
4. Debt payment delete removes balance effects and recomputes later snapshots.
5. Multiple selected rows for the same customer produce correct final balance.
6. Multiple selected rows for the same product produce correct stock.
7. Partial failure behavior is explicit and tested.
8. All history subtabs refresh consistently.

## G. Open Questions

1. Should selected rows remain selected when filters/search text changes, or should selection mode exit on filter changes?
   - Recommendation: exit or clear selection on filter changes for V1.
2. Should batch delete continue after one row fails, or stop immediately?
   - Recommendation: continue for employees/products; defer decision for history.
3. Should the existing single-row `Xóa` button become `Chọn để xóa`, or should there be two buttons?
   - Recommendation: reuse the existing `Xóa` button to enter selection mode, then replace/augment actions with `Xóa đã chọn` and `Hủy`.
4. Should inactive rows be selectable for delete?
   - Products: yes if visible, but confirmation must be clear.
   - Employees: likely yes if visible, but service behavior should be checked for already-inactive employees.
5. Should history batch delete be allowed at all?
   - Recommendation: defer from V1 due to stock/debt rollback risk.
6. Should a future bulk service method be added for products/employees?
   - Not required for V1. Per-row service calls preserve existing business rules.
