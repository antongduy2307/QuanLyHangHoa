# Attendance CUT/VK To Inventory Investigation

This is an investigation and design report only. No runtime code, schema, migrations, or tests were changed.

The new requirement is to make finalized Attendance CUT production increase inventory stock for the linked inventory products:

- CUT employee `CutLog.quantity`
- BLOW employee extra CUT / VK `ExtraCutWorkLog.quantity`

DRAFT records must not update inventory. DONE/finalized records must update inventory exactly once for their latest saved quantities, so edit/finalize flows need rollback/apply behavior rather than cumulative stock increases.

## Part A - Inventory Architecture

### Product Model / Table

File: `modules/inventory/models.py`

Class: `Product`

Table: `products`

Fields relevant to this design:

- `id`: integer primary key.
- `product_code_base`: `String(64)`, unique, indexed.
- `product_name`: `String(255)`, indexed.
- `unit_mode`: enum `UnitMode`.
- `is_active`: boolean, default true.
- `created_at`, `updated_at`.

Relationships relevant to inventory and history:

- `prices`: `ProductPrice`
- `inventory_balance`: `InventoryBalance`
- `receipt_items`: `InventoryReceiptItem`
- `adjustment_items`: `InventoryAdjustmentItem`
- `invoice_items`: `InvoiceItem`
- `return_items`: `ReturnInvoiceItem`

Product creation/update/delete flow:

- `modules/inventory/controller.py`
  - `InventoryController.create_product(...)`
  - `InventoryController.update_product(...)`
  - `InventoryController.delete_product(...)`
- `modules/inventory/service.py`
  - `InventoryService.create_product(...)`
  - `InventoryService.update_product(...)`
  - `InventoryService.delete_product(...)`
  - `InventoryService._has_product_history(...)`

Delete behavior:

- `InventoryService.delete_product(product_id)` hard-deletes products with no history.
- If history exists, it sets `Product.is_active = False`.
- `_has_product_history(...)` checks invoice items, return items, receipt items, and adjustment items.

### Inventory Stock Model / Table

File: `modules/inventory/models.py`

Class: `InventoryBalance`

Table: `inventory_balances`

Fields:

- `id`: integer primary key.
- `product_id`: foreign key to `products.id`, unique.
- `on_hand_bao_decimal`: `Numeric(14, 3)`, nullable.
- `on_hand_bich_integer`: `Numeric(14, 3)`, nullable.
- `updated_at`.

Quantity behavior:

- Decimal stock is supported.
- BAO/KG products store canonical inventory in `on_hand_bao_decimal`.
- BICH products store canonical inventory in `on_hand_bich_integer`.
- KG is not stored as a separate stock column; it is derived from BAO in service/reporting logic.
- Negative inventory is allowed by current service behavior and tests.

Constraints:

- Only one stock column may be non-null.
- At least one stock column must be non-null.

Service access:

- `modules/inventory/repository.py`
  - `InventoryRepository.get_product(product_id)`
  - `InventoryRepository.get_or_create_balance(product)`
- `modules/inventory/service.py`
  - `InventoryService.get_current_quantity(product_id)`
  - `InventoryService.get_available_quantity(product_id, unit_type)`
  - `InventoryService.increase_stock(product_id, quantity, unit_type)`
  - `InventoryService.decrease_stock(product_id, quantity, unit_type)`
  - `InventoryService._apply_stock_change(...)`

### Inventory Movement / History

There is no general inventory movement ledger with durable source references today.

Existing document tables:

- `InventoryReceipt`
  - file: `modules/inventory/models.py`
  - table: `inventory_receipts`
  - fields: `id`, `receipt_code`, `created_at`, `note`
- `InventoryReceiptItem`
  - file: `modules/inventory/models.py`
  - table: `inventory_receipt_items`
  - fields: `id`, `receipt_id`, `product_id`, `quantity`, `note`
- `InventoryAdjustment`
  - file: `modules/inventory/models.py`
  - table: `inventory_adjustments`
  - fields: `id`, `created_at`, `note`
- `InventoryAdjustmentItem`
  - file: `modules/inventory/models.py`
  - table: `inventory_adjustment_items`
  - fields: `id`, `adjustment_id`, `product_id`, `old_quantity`, `new_quantity`, `delta_quantity`, `note`

These tables do not currently store:

- generic `movement_type`
- `source_type`
- `source_id`
- `source_line_type`
- `source_line_id`
- idempotency keys for rollback/reapply

Sales and returns update stock through services and keep history in their own document tables (`invoice_items`, `return_invoice_items`), not in a shared movement ledger.

### Existing Stock-Changing Services

File: `modules/inventory/service.py`

`InventoryService.create_receipt(items)`:

- validates line quantities;
- creates an `InventoryReceipt`;
- calls `increase_stock(...)` for each item;
- appends `InventoryReceiptItem` records.

`InventoryService.create_adjustment(items)`:

- reads current canonical quantity;
- sets stock to requested `new_quantity`;
- stores `InventoryAdjustmentItem` with old/new/delta snapshots.

`InventoryService.increase_stock(...)` and `InventoryService.decrease_stock(...)`:

- accept `Decimal | int | str`;
- validate product/unit compatibility;
- mutate canonical inventory balance.

File: `modules/sales/service.py`

`SalesService.create_invoice(...)`:

- binds sales/customer/inventory services to one main DB session;
- calls `_apply_invoice_state(...)`;
- decreases stock for invoice items.

`SalesService.update_invoice(...)`:

- calls `_rollback_invoice_effects(invoice)`;
- clears old items;
- applies new invoice state.

`SalesService.delete_invoice(...)`:

- calls `_rollback_invoice_effects(invoice)`;
- deletes invoice.

`SalesService._rollback_invoice_effects(invoice)`:

- increases stock for every existing invoice item to reverse the previous sale effect.

File: `modules/returns/service.py`

`ReturnService.create_return_invoice(...)` / `create_quick_return_invoice(...)`:

- create return lines;
- increase stock.

`ReturnService.update_return_invoice(...)`:

- calls `_rollback_return_effects(...)`;
- clears old items;
- applies new return state.

`ReturnService.delete_return_invoice(...)`:

- calls `_rollback_return_effects(...)`;
- deletes return.

`ReturnService._rollback_return_effects(return_invoice)`:

- decreases stock for each old return item.

File: `modules/orders/service.py`

Orders read inventory for availability/summary, but they do not mutate stock. Existing tests intentionally allow orders above current stock.

### Existing Rollback / Apply Patterns

Sales and returns are the closest existing pattern:

1. Load existing document and lines.
2. Roll back old stock effect from existing lines.
3. Clear old lines.
4. Apply new lines and stock effect.
5. Commit all changes in one main DB transaction.

This pattern is transactionally safe for sales/returns because the document and inventory balances are in the same main DB.

Attendance cannot directly reuse that guarantee because attendance lives in a separate SQLite database.

### Existing Inventory Tests

Relevant test areas:

- `tests/test_inventory_service.py`
  - stock increase/decrease;
  - decimal BAO/BICH stock;
  - negative stock persistence;
  - product delete/deactivate behavior.
- `tests/test_inventory_transactions.py`
  - receipts increase stock;
  - adjustments set stock and store old/new/delta.
- `tests/test_sales_service.py`
  - invoices decrease stock;
  - invoice update/delete rollback behavior.
- `tests/test_return_service.py`
  - returns increase stock;
  - return update/delete rollback behavior.
- `tests/test_order_service.py`
  - orders do not change inventory.

## Part B - Attendance Save / Finalize Flow

### DailyRecord Model

File: `modules/attendance/models.py`

Class: `DailyRecord`

Table: `daily_records`

Fields:

- `id`: integer primary key.
- `employee_id`: foreign key to attendance `employees.id`.
- `date`: work date.
- `period_id`: attendance period.
- `is_absent`: boolean.
- `status`: enum `DailyRecordStatus`, values `DRAFT` and `DONE`.
- `total_amount_snapshot`: integer money snapshot.

Relationships:

- `work_logs`
- `cut_logs`
- `extra_cut_work_logs`

Constraints:

- unique `(employee_id, date)`.
- non-negative `total_amount_snapshot`.

### CutLog Model

File: `modules/attendance/models.py`

Class: `CutLog`

Table: `cut_logs`

Fields:

- `id`
- `daily_record_id`
- `bag_type_id`
- `quantity`: `Numeric(12, 3)`, decimal-capable.
- `unit_price_snapshot`
- `quota_quantity_snapshot`
- `excess_unit_price_snapshot`
- `amount_snapshot`

Relationships:

- `daily_record`
- `bag_type`

Constraints:

- unique `(daily_record_id, bag_type_id)`.
- `quantity >= 0`.

### ExtraCutWorkLog / VK Model

File: `modules/attendance/models.py`

Class: `ExtraCutWorkLog`

Table: `extra_cut_work_logs`

Fields:

- `id`
- `daily_record_id`
- `bag_type_id`
- `quantity`: `Numeric(12, 3)`, decimal-capable.
- `excess_unit_price_snapshot`
- `amount_snapshot`
- `created_at`, `updated_at`

Relationships:

- `daily_record`
- `bag_type`

Constraints:

- unique `(daily_record_id, bag_type_id)`.
- `quantity > 0`.

### BagType Product Link

File: `modules/attendance/models.py`

Class: `BagType`

Table: `bag_types`

Product sync fields already implemented:

- `is_product_linked`
- `source_product_id`
- `source_product_name_snapshot`
- `is_excluded_from_attendance`
- `is_legacy`

`source_product_id` is an external reference to main DB `products.id`. There is no cross-database foreign key.

### AttendanceDayEntryService.save_attendance

File: `modules/attendance/service.py`

Class: `AttendanceDayEntryService`

Method: `save_attendance(payload, *, finalize)`

Current flow:

1. Opens an attendance DB session and transaction.
2. Loads employee.
3. Ensures the attendance period for the selected date.
4. Loads an existing `DailyRecord` or creates a new one.
5. Rejects edits in locked periods.
6. Sets `record.status = DRAFT` before rebuilding logs.
7. Captures `existing_cut_bag_type_ids` and `existing_extra_cut_bag_type_ids` for historical validation compatibility.
8. Clears existing `work_logs`, `cut_logs`, and `extra_cut_work_logs`.
9. If absent:
   - sets `record.is_absent = True`;
   - sets total amount to 0.
10. If not absent:
   - BLOW employees use `_apply_blow_payload(...)`;
   - CUT employees use `_apply_cut_payload(...)`.
11. Sets final status:
   - `DONE` when `finalize=True`;
   - `DRAFT` otherwise.
12. Flushes and returns `AttendanceSaveResult`.

Important observations:

- Existing logs are cleared and recreated on every save.
- This is convenient for recalculation, but line IDs may change after an edit.
- Any inventory effect design should roll back by `daily_record_id` source, not rely only on stable old log IDs.
- There is no separate delete/unfinalize API in this service. Saving `finalize=False` acts as DONE-to-DRAFT, and saving absent clears production lines.

### Batch 5 Validation

File: `modules/attendance/service.py`

Constant:

- `INVALID_CUT_WORK_MESSAGE`

Methods:

- `_apply_cut_payload(...)`
- `_apply_extra_cut_work_payload(...)`
- `_is_bag_type_valid_for_new_cut_work(...)`

New CUT/VK bag type rows are valid only when the BagType is:

- active;
- product-linked;
- not excluded from attendance;
- not legacy;
- `quota_quantity > 0`;
- `excess_unit_price > 0`.

Historical compatibility:

- A bag type already present in the original loaded record can be saved again even if it is now inactive, legacy, excluded, or incomplete.

Inventory implication:

- Historical invalid rows can still be edited for attendance compatibility, but DONE inventory application still needs a resolvable `source_product_id` and a real main DB product.

## Part C - Business Rule Confirmation

Intended rule compatibility:

1. DRAFT attendance saves attendance only.
   - Current code supports DRAFT.
   - Inventory integration should roll back prior effects if an existing DONE record is changed to DRAFT, then apply nothing.

2. DONE attendance applies inventory effect.
   - Current code sets status at the end of `save_attendance`.
   - Inventory integration should apply only when final status is DONE.

3. CUT employee `CutLog.quantity` increases linked product stock.
   - `CutLog.quantity` supports Decimal.
   - `CutLog.bag_type.source_product_id` provides the product link.

4. BLOW extra CUT / VK increases linked product stock.
   - `ExtraCutWorkLog.quantity` supports Decimal.
   - It uses the same linked `BagType`.

5. Edit DONE record needs rollback/apply.
   - Current code clears/recreates logs.
   - Inventory effects must be reconciled by daily record source so old stock is removed and latest lines are applied.

6. DONE to DRAFT / absent / removed line needs rollback.
   - Current save flow can produce those states.
   - Inventory integration should roll back prior source effects and apply none for DRAFT/absent/removed rows.

7. Existing historical records before this feature should not be automatically backfilled.
   - Current databases have no effect marker.
   - A future implementation should only create effects for records saved/finalized after the feature is installed, unless an explicit backfill tool is run.

Potential business decision to confirm before implementation:

- If an old DONE record from before this feature is opened and saved again after the feature exists, should it create stock effect at that time? The safest operational rule is: any user-initiated save/finalize after the feature exists reconciles inventory for that record; untouched historical records are not backfilled automatically.

## Part D - Two-Database Vs Merged Database Analysis

### Option A - Keep Two DBs And Add Inventory Effect Layer

Description:

- Keep `app.db` and `attendance.db`.
- Continue using `BagType.source_product_id` as an external main DB product reference.
- Add a durable inventory effect/movement layer in the main DB.
- Coordinate attendance save and inventory reconciliation in service code.

Pros:

- Builds on the product-to-attendance sync already implemented.
- Lowest data migration risk.
- Avoids rewriting attendance repositories, settings, reports, backup, and tests.
- Can be implemented incrementally.
- Keeps current deployment/update risk narrow.

Cons:

- No real cross-database foreign keys.
- No single transaction across both SQLite files in the current engine setup.
- Needs explicit reconciliation, diagnostics, and error handling.

Implementation complexity:

- Moderate.

Rollback risk:

- Manageable if all attendance stock effects are recorded with source keys and can be reversed by source.

Backup/restore impact:

- Both DBs must be backed up/restored together.

Recommendation:

- Recommended for V1.

### Option B - Merge app.db And attendance.db Now

Description:

- Move attendance tables into the main DB.
- Replace external product references with normal foreign keys where appropriate.

Pros:

- One SQLite transaction can cover attendance and inventory.
- Referential integrity is simpler.
- Long-term data model may be cleaner.

Cons:

- High migration risk for existing users.
- Requires changing attendance DB engine/session code across many files.
- Requires migrating existing `attendance.db` into `app.db`.
- Raises backup/restore and diagnostics migration complexity.
- Broad test fallout likely.
- Larger release risk than the requested feature.

Implementation complexity:

- High.

Recommendation:

- Do not merge now. Treat as a future dedicated architecture migration if the app outgrows the two-DB model.

### Option C - Rebuild Database From Scratch

Description:

- Replace current DB design with a new unified schema.

Pros:

- Clean theoretical design.

Cons:

- Highest data-loss and migration risk.
- Inappropriate for an existing deployed app.
- Would delay the business feature behind a broad rewrite.

Implementation complexity:

- Very high.

Recommendation:

- Do not rebuild from scratch.

### Architecture Recommendation

Do not roll back the product-attendance link. Do not merge databases now. Do not rebuild the database.

Continue from the current product-linked design and add a main DB inventory effect layer plus reconciliation/diagnostics.

## Part E - Proposed Inventory Effect Design

### Current Gap

`InventoryService.increase_stock(...)` and `decrease_stock(...)` can mutate balances, but they do not record source references. Using them directly from attendance would risk:

- double-counting repeated DONE saves;
- no way to know what an attendance record previously applied;
- no reliable rollback for edited/removed lines;
- weak diagnostics after a partial failure.

### Recommended Main DB Schema Extension

In a future implementation batch, add a main DB table such as:

`inventory_stock_effects`

Suggested fields:

- `id`: integer primary key.
- `source_type`: string, e.g. `ATTENDANCE_DAILY_RECORD`.
- `source_id`: integer, attendance `daily_records.id`.
- `source_line_type`: string, `CUT_LOG` or `EXTRA_CUT_WORK_LOG`.
- `source_line_id`: integer, attendance log id at the time the effect was applied.
- `attendance_employee_id`: integer snapshot for diagnostics.
- `attendance_work_date`: date snapshot.
- `attendance_bag_type_id`: integer snapshot.
- `product_id`: integer foreign key to main DB `products.id`.
- `quantity_delta`: `Numeric(14, 3)`.
- `unit_type`: enum/string compatible with `UnitType`, usually `BAO` or `BICH`.
- `movement_datetime`: date/datetime from `DailyRecord.date`.
- `note`: text, e.g. `Chấm công tổ cắt`.
- `created_at`, `updated_at`.

Recommended indexes:

- index `(source_type, source_id)` for rollback by daily record.
- unique `(source_type, source_id, source_line_type, source_line_id)` if source line ids are kept.
- index `product_id` for product history.

Important line-id caveat:

- Attendance logs are cleared/recreated on save, so old `source_line_id` values may not be stable across edits.
- The rollback/apply operation should primarily roll back all effects by `(source_type, source_id)` before applying current lines.
- `source_line_id` is still valuable as an audit snapshot, but rollback should not depend on matching old line IDs one-by-one.

### Quantity And Unit Mapping

Attendance quantity should map to the product's canonical inventory family:

- If `Product.unit_mode == UnitMode.BAO_KG`, apply attendance quantity as `UnitType.BAO`.
- If `Product.unit_mode == UnitMode.BICH`, apply attendance quantity as `UnitType.BICH`.

Reason:

- Current BAO/KG inventory stores stock as bags in `on_hand_bao_decimal`.
- Attendance CUT/VK quantities represent produced product units/bags, not KG conversions.
- Decimal quantity is already supported on both sides.

If the business later needs a CUT item to update KG instead of BAO, that should be an explicit future setting rather than inferred.

### Service Design

Suggested class:

`AttendanceInventoryEffectService`

Suggested file:

- `modules/attendance/inventory_effect_service.py`

Dependencies:

- main DB `SessionFactory`
- `InventoryService`
- read-only attendance record/effect DTOs from `AttendanceDayEntryService`

Core public method:

`reconcile_daily_record_effects(record_effect_snapshot) -> AttendanceInventoryEffectResult`

Responsibilities:

1. In main DB transaction, find existing `inventory_stock_effects` for:
   - `source_type = ATTENDANCE_DAILY_RECORD`
   - `source_id = daily_record.id`
2. Roll back those old effects by applying inverse deltas to inventory balances.
3. Delete or mark old effect rows as superseded.
4. If current attendance record is not DONE or is absent, stop.
5. Validate current CUT/VK lines:
   - linked BagType has `source_product_id`;
   - product exists in main DB;
   - product unit mode can be mapped;
   - product state is acceptable by final business rule.
6. Apply current deltas:
   - CUT log quantity -> stock increase.
   - VK log quantity -> stock increase.
7. Insert new effect rows.

Idempotence:

- Running reconcile repeatedly for the same unchanged DONE record should leave stock unchanged after the first run because old source effects are rolled back before current effects are applied.

### Why Not Reuse InventoryReceipt

Using `InventoryReceipt` as synthetic attendance receipt records is possible but not recommended:

- receipt rows have no first-class source id;
- no unique source key prevents duplicate receipts;
- rollback would depend on code/notes conventions;
- editing attendance would need to find and replace generated receipt documents.

A dedicated effect/movement table is clearer and safer.

## Part F - Cross-DB Failure Handling

### Partial Commit Risk

Because `app.db` and `attendance.db` are separate SQLite files, the current architecture cannot guarantee a single atomic commit across attendance save and inventory update.

Failure scenarios:

1. Attendance commit succeeds, inventory effect fails.
2. Inventory effect succeeds, attendance commit fails.
3. Process crashes between DB commits.
4. Product link is stale or product is deleted.
5. Inventory balance row is locked or unavailable.

### Recommended V1 Behavior

Use synchronous reconciliation and fail clearly:

1. Validate product links before finalizing:
   - each DONE effect line has `source_product_id`;
   - each product exists;
   - unit mode can be mapped.
2. Save attendance in attendance DB.
3. Reconcile inventory effects in main DB immediately.
4. If inventory reconciliation fails, show a clear error and log details.
5. Provide a diagnostic/retry path for records whose attendance status and inventory effect rows disagree.

Practical call-order recommendation:

- If possible, keep the attendance transaction open until inventory validation passes.
- After attendance flush and before reporting success, run inventory reconciliation.
- If main DB reconciliation raises, raise the service error so the UI does not claim success.

Remaining risk:

- If one DB commits and the other fails, a repair path is still needed. The effect table makes this diagnosable and reversible.

### Outbox / Retry Option

For stronger reliability, add a future small status table:

`attendance_inventory_sync_status`

Suggested fields:

- `daily_record_id`
- `status`: `pending`, `applied`, `failed`
- `last_error`
- `updated_at`

This is not required for the first backend implementation if the effect table and diagnostic service are present, but it is the right direction if partial failures are observed.

## Part G - Integration Points

Primary integration point:

- `modules/attendance/service.py`
- `AttendanceDayEntryService.save_attendance(...)`

Support method likely needed:

- Build a plain `AttendanceInventoryEffectSnapshot` after saving/flushing the attendance record.

Snapshot should include:

- `daily_record_id`
- `employee_id`
- `work_date`
- `status`
- `is_absent`
- CUT lines:
  - `cut_log_id`
  - `bag_type_id`
  - `quantity`
  - `source_product_id`
- VK lines:
  - `extra_cut_work_log_id`
  - `bag_type_id`
  - `quantity`
  - `source_product_id`

### Proposed Pseudocode

#### Save DRAFT

```python
result = save_attendance_record_in_attendance_db(status=DRAFT)
inventory_effect_service.reconcile_daily_record_effects(
    snapshot_for(record_id, status=DRAFT)
)
return result
```

Effect:

- rollback existing effects for the record;
- apply nothing.

#### Save New DONE

```python
validate_done_inventory_links(payload)
result = save_attendance_record_in_attendance_db(status=DONE)
snapshot = load_effect_snapshot(record_id)
inventory_effect_service.reconcile_daily_record_effects(snapshot)
return result
```

Effect:

- no old effects on first run;
- apply all CUT/VK quantities.

#### Edit Existing DONE

```python
validate_done_inventory_links(payload)
result = save_attendance_record_in_attendance_db(status=DONE)
snapshot = load_effect_snapshot(record_id)
inventory_effect_service.reconcile_daily_record_effects(snapshot)
return result
```

Effect:

- rollback old source effects;
- apply latest quantities only.

#### DONE To DRAFT

```python
result = save_attendance_record_in_attendance_db(status=DRAFT)
inventory_effect_service.reconcile_daily_record_effects(
    snapshot_for(record_id, status=DRAFT)
)
return result
```

Effect:

- rollback old source effects;
- apply nothing.

#### Absent Day

```python
result = save_attendance_record_in_attendance_db(is_absent=True)
inventory_effect_service.reconcile_daily_record_effects(snapshot_for_absent(record_id))
return result
```

Effect:

- rollback old source effects;
- apply nothing.

#### Removed CUT/VK Line

No special case is needed if reconciliation is by daily record source:

- old effects are all rolled back;
- only current remaining lines are applied.

### Constructor / Dependency Recommendation

`AttendanceDayEntryService` can accept an optional inventory effect service dependency:

```python
AttendanceDayEntryService(
    repository=None,
    inventory_effect_service=None,
)
```

Tests can inject a fake service. Production can use the real service.

## Part H - UI / UX Impact

Minimal UI changes recommended for implementation:

1. On DONE save success:
   - optional text can mention stock was updated;
   - not required if the current save success message is already adequate.

2. On inventory update failure:
   - show a blocking validation/error message;
   - do not silently save as if all is complete.

Suggested Vietnamese message:

`Không cập nhật được tồn kho từ chấm công. Vui lòng kiểm tra hàng hóa liên kết và thử lưu lại.`

3. Product inventory history:
   - if an inventory history UI is added or extended, attendance effects should be labeled:
     - `Chấm công tổ cắt`
   - optional note:
     - employee name/team;
     - attendance date;
     - CUT or VK source.

4. Diagnostics:
   - future diagnostics should show records where DONE attendance and inventory effects are mismatched.

Do not add UI in the first backend-only implementation unless needed to surface existing service errors.

## Part I - Migration / Backfill Strategy

Recommendation:

1. Do not automatically backfill old DONE attendance records.
2. Add the inventory effect schema going forward.
3. Apply stock effects only when records are saved/finalized after the feature is installed.
4. Add an optional backfill/diagnostic tool later.

Optional future backfill tool:

- list DONE attendance records with CUT/VK quantities and no inventory effect;
- preview per-product stock deltas;
- require manual confirmation;
- write effect rows and apply stock;
- recommend backup first.

Backup/restore:

- `modules/settings/backup_service.py` already includes both DBs when present:
  - main app DB from `settings.db_path`;
  - attendance DB from `get_attendance_db_path()`.
- This feature increases the importance of restoring both DBs together.
- Restoring only one DB can leave attendance source records and inventory effect rows inconsistent.

Rollback strategy:

- Because effects are source-keyed, a repair tool can roll back all effects for a daily record or reapply them from current attendance lines.
- Do not try to infer attendance production from stock balances alone.

## Part J - Test Plan

### Core Behavior

1. DRAFT CUT save does not update stock.
2. DRAFT VK save does not update stock.
3. DONE CUT save increases linked product stock.
4. DONE VK save increases linked product stock.
5. DONE absent day applies no production stock.

### Edit / Rollback / Idempotence

6. Editing DONE CUT quantity upward increases stock by the net difference only.
7. Editing DONE CUT quantity downward decreases stock by the net difference only.
8. Editing DONE VK quantity upward/downward updates stock by net difference only.
9. Re-saving the same DONE record is idempotent and does not double count.
10. Removing a CUT line rolls back that line's stock effect.
11. Removing a VK line rolls back that line's stock effect.
12. DONE to DRAFT rolls back all source effects.
13. DONE to absent rolls back all source effects.

### Multi-Product / Decimal

14. Multiple products in one attendance record update the correct inventory balances.
15. Two employees producing the same product on the same day aggregate correctly.
16. Decimal CUT quantity updates stock exactly.
17. Decimal VK quantity updates stock exactly.

### Product Link / Product State

18. Missing `source_product_id` rejects with a clear service error for DONE records.
19. `source_product_id` pointing to a missing product rejects clearly.
20. Product inactive/deleted behavior follows the final product-state rule.
21. Historical invalid BagType rows can be re-saved for attendance, but DONE inventory application requires a resolvable product.

### Cross-DB Failure

22. Inventory apply failure does not produce duplicate effect rows.
23. Retry after failure applies stock once.
24. Diagnostic service can find DONE attendance records with missing/mismatched inventory effects.
25. Main DB rollback failure is logged with daily record and product details.

### Inventory History / Effect Rows

26. Effect rows store `source_type = ATTENDANCE_DAILY_RECORD`.
27. CUT rows store `source_line_type = CUT_LOG`.
28. VK rows store `source_line_type = EXTRA_CUT_WORK_LOG`.
29. Product history can label effects as `Chấm công tổ cắt` if a history UI is added.

### Backup / Restore

30. User backup includes both main and attendance DBs.
31. Documentation warns that restoring only one DB can create mismatch.

## Part K - Final Recommendation

### 1. Should We Roll Back Current Product-Attendance Link Feature?

No.

The current product-to-`BagType` link is the correct foundation. `BagType.source_product_id` is exactly the bridge needed to connect CUT/VK production to inventory products without importing product prices, stock, or sales fields into attendance.

### 2. Should We Merge The DBs Now?

No.

Merging now would turn this feature into a broad architecture migration. The current requirement can be delivered with the existing two-DB model if inventory effects are source-tracked and reconciled.

### 3. Should We Rebuild DB From Scratch?

No.

That would be unnecessarily risky for existing deployed data and not needed for this feature.

### 4. Recommended Implementation Batches

Batch 1 - Inventory effect schema and service:

- add main DB `inventory_stock_effects`;
- add `AttendanceInventoryEffectService`;
- implement rollback/apply/reconcile by attendance daily record source;
- test idempotence and decimal quantities.

Batch 2 - Attendance save integration:

- integrate reconciliation into `AttendanceDayEntryService.save_attendance(...)`;
- handle DRAFT, DONE, absent, edit, removed lines, and VK;
- inject fake service in tests.

Batch 3 - Failure diagnostics:

- add service to detect DONE records with missing/mismatched effects;
- add retry/reconcile command or settings diagnostic entry.

Batch 4 - UI polish:

- display clear error on inventory update failure;
- optionally label inventory history rows as `Chấm công tổ cắt`.

Batch 5 - Optional manual backfill:

- preview old DONE records without effects;
- manually apply after backup/confirmation.

### 5. Highest Risks

1. Cross-DB partial commits.
2. Double-counting without durable effect rows.
3. Stale or missing `source_product_id`.
4. Product unit mapping ambiguity for BAO/KG products.
5. Restoring only one DB.
6. Editing old DONE records after the feature ships may unexpectedly create stock if not communicated.

### 6. First Manual Tests

1. Create product, sync/configure CUT work, save DRAFT attendance, verify stock unchanged.
2. Finalize CUT attendance, verify stock increases.
3. Edit finalized quantity up/down, verify stock equals latest finalized quantity only.
4. Add BLOW VK production, verify stock increases.
5. Convert DONE to DRAFT, verify stock rolls back.
6. Save absent over previous DONE production, verify stock rolls back.
7. Try missing product link, verify clear error.
8. Create backup after inventory effect, verify both DBs are included.
