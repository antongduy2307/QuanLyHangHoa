# Attendance Product CUT Sync Investigation

Investigation/design only. No implementation, schema migration, UI behavior, or runtime behavior is changed by this document.

## A - Current Product Schema / Flow Investigation

### Product model/table

- File: `modules/inventory/models.py`
- Class: `Product`
- Table: `products`
- Primary key: `id`
- Product name field: `product_name`
- Product code field: `product_code_base`, unique and required
- Active/inactive field: `is_active`, default `True`
- Delete-related fields: no deleted timestamp or soft-delete reason field was found. Soft deletion is represented by `is_active = False`.
- Timestamp fields: none found on `Product`.
- Relevant relationships:
  - `prices`
  - `inventory_balance`
  - `receipt_items`
  - `adjustment_items`
  - `invoice_items`
  - `order_items`
  - `return_items`

The product table only enforces uniqueness for `product_code_base`; product names are not clearly unique at the model layer. That matters for attendance sync because `BagType.name` is currently unique.

### Product repository/service/controller flow

- File: `modules/inventory/repository.py`
  - `ProductRepository.list_products(include_inactive=False)` lists active products by default and includes inactive products only when requested.
  - Product persistence helpers are used by `ProductService`.
- File: `modules/inventory/service.py`
  - `ProductService.create_product(...)` creates active products and initializes related price/balance data.
  - `ProductService.update_product(...)` supports editing `product_name`, `product_code_base`, `unit_mode`, and pricing fields.
  - `ProductService.get_delete_mode(product_id)` returns `deactivate` when product history exists and `hard_delete` otherwise.
  - `ProductService.delete_product(product_id)` either sets `is_active = False` or hard deletes the product depending on history.
- File: `modules/inventory/controller.py`
  - `InventoryController.create_product(...)`
  - `InventoryController.update_product(...)`
  - `InventoryController.get_delete_mode(...)`
  - `InventoryController.delete_product(...)`

Product names can be changed. Products can be hard deleted when no history exists, and soft-deactivated when history exists.

### Product UI flow

- File: `modules/inventory/ui/product_list_view.py`
- Class: `ProductListView`
- Add product:
  - `_open_create_product(...)`
  - opens `ProductDialog`
  - calls `InventoryController.create_product(...)`
  - reloads the list locally.
- Edit product:
  - `_edit_product(...)`
  - calls `InventoryController.update_product(...)`
  - reloads the list locally.
- Delete/deactivate product:
  - `_delete_product(...)`
  - checks delete mode through the controller
  - calls `InventoryController.delete_product(...)`
  - reloads the list locally.

No app-wide product changed event/signal was found in the product list flow. The current refresh pattern is local reload after product changes. This means a V1 attendance sync can safely run when entering Attendance or Attendance Settings, without needing a product event bus first.

### Product data needed for attendance sync

Attendance sync should read only:

- `Product.id`
- `Product.product_name`
- `Product.is_active`

Attendance must not import:

- selling price
- cost
- stock quantity
- product unit/unit mode
- inventory quantities
- sales/order/customer data

## B - Current Attendance BagType / CUT Work Schema Investigation

### BagType / CUT work model

- File: `modules/attendance/models.py`
- Class: `BagType`
- Table: `bag_types`
- Primary key: `id`
- Name field: `name`, currently unique and required
- Quota field: `quota_quantity`, `Numeric(12, 2)`, default `0`
- Excess unit price field: `excess_unit_price`, `Numeric(12, 2)`, default `0`
- Legacy `unit_price` field exists and defaults to `0`
- Active/inactive field: `is_active`, default `True`
- Snapshot fields: none on `BagType`; snapshots live on log rows.
- Constraints:
  - nonnegative `unit_price`
  - nonnegative `quota_quantity`
  - nonnegative `excess_unit_price`

### CutLog / CUT employee production model

- File: `modules/attendance/models.py`
- Class: `CutLog`
- Table: `cut_logs`
- Fields:
  - `id`
  - `daily_record_id`
  - `bag_type_id`
  - `quantity`, `Numeric(12, 3)`
  - `unit_price_snapshot`
  - `quota_quantity_snapshot`, `Numeric(12, 2)`
  - `excess_unit_price_snapshot`, `Numeric(12, 2)`
  - `amount_snapshot`
- Relationship to BagType:
  - `bag_type_id` references `bag_types.id`
  - `bag_type` relationship is used by UI/report code.
- Decimal quantity support:
  - `quantity` is already Decimal-compatible through `Numeric(12, 3)`.

### BLOW extra CUT / VK model

- File: `modules/attendance/models.py`
- Class: `ExtraCutWorkLog`
- Table: `extra_cut_work_logs`
- This is separate from `CutLog`.
- Fields:
  - `id`
  - `daily_record_id`
  - `bag_type_id`
  - `quantity`, `Numeric(12, 3)`
  - `excess_unit_price_snapshot`, `Numeric(12, 2)`
  - `amount_snapshot`
  - `created_at`
  - `updated_at`
- Relationship to BagType:
  - `bag_type_id` references `bag_types.id`
  - `bag_type` relationship is used by UI/report code.
- Decimal quantity support:
  - `quantity` is already Decimal-compatible.

### Attendance settings UI

- File: `modules/attendance/settings_service.py`
  - `AttendanceSettingsService.list_bag_types(include_inactive=True)`
  - `AttendanceSettingsService.create_bag_type(...)`
  - `AttendanceSettingsService.update_bag_type(...)`
  - `AttendanceSettingsService.set_bag_type_active(...)`
- File: `modules/attendance/ui/settings_tab.py`
  - `AttendancePriceSettingsTab`
  - `BagTypeDialog`
  - `BagTypeFormValue`

Current settings behavior:

- `AttendancePriceSettingsTab.reload()` calls `list_bag_types(include_inactive=False)`, so inactive bag types are hidden from the active settings table.
- The bag type table currently shows:
  - name
  - quota quantity
  - excess unit price
- Users can create, edit, and deactivate bag types manually.
- Product-linked fields, exclusion checkbox, and incomplete-row highlighting do not exist yet.

### Attendance day-entry UI

- File: `modules/attendance/ui/day_entry_tab.py`
- Class: `DayEntryTab`
- CUT employee bag work:
  - `_build_cut_form(...)`
  - `_available_cut_bag_types(...)`
  - `_add_cut_bag_row(...)`
  - `_collect_payload(...)`
- BLOW extra CUT / VK work:
  - `_build_extra_cut_form(...)`
  - `_add_extra_cut_bag_row(...)`
  - `_collect_payload(...)`

Current day-entry behavior:

- Active bag types are available for CUT employee rows and BLOW extra CUT/VK rows.
- Decimal quantity input is already supported for CUT and VK quantities.
- Incomplete bag types with zero quota or zero price can currently be selected if active.

### Attendance report services

- File: `modules/attendance/report_service.py`
- Class: `AttendanceReportService`
- 10-day report:
  - `build_report(...)`
  - `_work_values_for_record(...)`
  - `_format_work_value(...)`
- 30-day report:
  - `build_monthly_report(...)`
  - `_monthly_values_for_record(...)`
  - `_format_quantity(...)`

Reports use saved amount snapshots for money totals. Quantity reports use `CutLog.quantity`. Labels are derived from the current `BagType.name`, so strict historical name preservation would require a future log-level name snapshot if the business requires old reports to keep old names after product rename.

### Seed/default data

- File: `modules/attendance/seed.py`
- `DEFAULT_BAG_TYPES` seeds initial manual bag types such as `Bao 25kg`, `Bao 50kg`, and `Bao PP`.
- Seeding is idempotent by bag type name.

After product sync is introduced, default bag types should not remain the long-term source of truth for CUT work. Existing seeded rows should be treated as legacy/manual rows and preserved or deactivated safely.

### Attendance migrations/init

- File: `modules/attendance/db.py`
- `init_attendance_db()`
- `_upgrade_attendance_schema(engine)`

Current migration style is idempotent and SQLite-oriented. New `BagType` columns should be added through this same attendance schema upgrade path.

## C - Current Data Flow / Breakage Analysis

### Places where BagType/CUT work is used

- `modules/attendance/models.py`
  - `BagType`
  - `CutLog`
  - `ExtraCutWorkLog`
- `modules/attendance/settings_service.py`
  - lists, creates, updates, and deactivates bag types.
- `modules/attendance/ui/settings_tab.py`
  - displays and edits bag type price settings.
- `modules/attendance/repository.py`
  - `list_bag_types_for_entry(...)`
  - includes historical bag types by id when reloading existing records.
- `modules/attendance/ui/day_entry_tab.py`
  - CUT employee bag selection and BLOW extra CUT/VK selection.
- `modules/attendance/report_service.py`
  - report labels and quantities use BagType relationships.
- `modules/attendance/seed.py`
  - creates default bag types.

### What breaks if old BagTypes are hard deleted?

Hard deletion is risky.

- Existing `CutLog.bag_type_id` and `ExtraCutWorkLog.bag_type_id` rows can become orphaned or deletion can fail when foreign keys are enforced.
- Day-entry reload can fail or lose labels for historical records.
- 10-day and 30-day reports can fail when accessing `log.bag_type.name`.
- Diagnostics/backup can still copy the DB, but the copied DB would contain damaged attendance history.

### What breaks if old BagTypes are deactivated but preserved?

This is the safest default.

- Historical logs keep their `bag_type_id`.
- Existing reload behavior can include inactive historical bag types by id.
- Reports remain mostly compatible.
- New day-entry selections can hide inactive rows.

The main risk is user confusion if inactive/legacy rows are still shown in settings without clear labeling.

### What breaks if old BagTypes remain visible?

- Users may keep recording new attendance against old manual bag types instead of product-linked bag types.
- Duplicate names become confusing.
- Incomplete config warnings become harder to explain.
- Manual rows can compete with synced product rows.

### Safest handling for old BagTypes with history

Preserve them, mark them as legacy, and deactivate them from new selection. Show them only in a legacy/inactive settings section if needed.

### Safest handling for old BagTypes without history

Deactivate them in V1. Hard deletion can be a later explicit cleanup operation after backup and user confirmation.

## D - Two-Database Linkage Risk Analysis

### Performance

Product list size is expected to be small enough for periodic sync. Day-entry search should read attendance `BagType` rows only, not query products on every keystroke. Reports should continue using attendance logs and snapshots.

### SQLite locking

The safest transaction boundary is:

1. Open main DB session.
2. Read product `id`, `product_name`, and `is_active` into memory.
3. Close main DB session.
4. Open attendance DB session.
5. Upsert attendance rows.
6. Commit attendance DB changes.

This avoids holding simultaneous write transactions on both SQLite databases.

### Cross-database integrity

There is no real foreign key between separate SQLite files. `source_product_id` must be treated as an external reference, not a database-enforced relationship. Sync must tolerate missing products, restored databases, and renamed products.

### Backup/restore

- File: `modules/settings/backup_service.py`
- Class: `UserBackupService`
- `create_user_backup()` includes both the main app DB from `settings.db_path` and attendance DB from `get_attendance_db_path()` when present.

Product-attendance linkage increases the need for consistent two-DB backups. If only one DB is restored, linked rows can become stale until sync repairs what it can. Backup/restore documentation and diagnostics should explicitly mention both databases before implementation.

### Existing historical data

Existing `CutLog` and `ExtraCutWorkLog` rows depend on old `BagType` ids. Those rows must not be rewritten or orphaned during initial sync. Saved amount snapshots should remain the source of truth for historical money totals.

### CI/test complexity

Sync tests will need isolated temp paths for both app DB and attendance DB. Existing CI work already made DB path handling portable; implementation tests should continue that pattern and avoid hardcoded local paths.

### Migration complexity

Required migration is moderate if limited to `BagType` metadata columns. It becomes high risk if attempting to merge databases or infer links for old historical bag types by name.

### User experience

The negative checkbox `Không dùng cho chấm công` is important because products may exist that are not attendance work. Without the checkbox, users would see warnings for many intentionally unused products.

### Option A - Keep two databases and sync product names into attendance.db

Pros:

- Preserves current architecture.
- Limits attendance to product names only.
- Avoids importing sales/inventory data.
- Keeps attendance reports fast and local to attendance DB.
- Lower migration risk.

Cons:

- No cross-DB foreign key.
- Requires sync service and stale-link repair logic.
- Requires consistent backup/restore expectations.

Risks:

- Duplicate product names conflict with current unique `BagType.name`.
- Restoring only one DB can create stale product links.

Implementation complexity: medium.

Recommendation: use this option.

### Option B - Merge app.db and attendance.db into one database

Pros:

- Real foreign keys are possible.
- Single backup target.
- Product link integrity is simpler.

Cons:

- Broad migration risk.
- Large blast radius across sales, inventory, customer, order, attendance, backup, diagnostics, and tests.
- Contradicts the current preference to keep the databases separate if safe.

Risks:

- High chance of regressions in unrelated modules.
- More difficult rollback.

Implementation complexity: high.

Recommendation: do not choose this for V1.

### Option C - Do not sync; attendance directly queries app.db products every time

Pros:

- No duplicated product name data.
- Product rename is immediately visible.

Cons:

- Attendance day-entry/search depends on main DB availability.
- Attendance settings still need attendance-owned quota, price, and exclusion fields.
- Cross-database reads become common.
- Harder to preserve an attendance-specific active/configured list.

Risks:

- More locking/session complexity in UI flows.
- More coupling between modules.

Implementation complexity: medium-high.

Recommendation: avoid this for V1.

## E - Proposed Schema Extension

Add metadata to `BagType` in `modules/attendance/models.py` and migrate through `modules/attendance/db.py`.

### Proposed columns

#### `is_product_linked`

- Type: Boolean
- Nullable/default: `NOT NULL DEFAULT 0`
- Purpose: identifies bag types created by product sync.
- Migration behavior: existing rows default to `False`.
- Historical impact: none.

#### `source_product_id`

- Type: Integer
- Nullable/default: nullable, default `NULL`
- Purpose: external reference to `products.id` in the main app DB.
- Migration behavior: existing rows default to `NULL`.
- Historical impact: none.
- Constraint recommendation: unique where not null, or regular unique if SQLite behavior with multiple nulls is acceptable.

#### `source_product_name_snapshot`

- Type: String/Text
- Nullable/default: nullable, default `NULL`
- Purpose: records the latest product name seen by sync for diagnostics and stale-link repair.
- Migration behavior: existing rows default to `NULL`.
- Historical impact: none.

#### `is_excluded_from_attendance`

- Type: Boolean
- Nullable/default: `NOT NULL DEFAULT 0`
- Purpose: backs the negative checkbox `Không dùng cho chấm công`.
- Migration behavior: existing rows default to `False`.
- Historical impact: none.

#### `is_legacy`

- Type: Boolean
- Nullable/default: `NOT NULL DEFAULT 0`
- Purpose: marks old manual/default bag types preserved for history.
- Migration behavior: existing rows may be marked legacy during an implementation migration step after checking history.
- Historical impact: none if rows are preserved.

### Name uniqueness issue

Current `BagType.name` is unique, while `Product.product_name` does not appear to be unique. This is the highest schema/design risk.

Preferred long-term model:

- uniqueness should be based on `source_product_id` for product-linked rows, not `name`;
- the UI can still display product name as the visible name;
- duplicate product names should be allowed if the inventory module allows them.

If changing/removing the name unique constraint is too risky in V1, the sync service must detect duplicate product names and fail with a clear warning instead of silently appending suffixes. Appending suffixes would violate the requirement that attendance uses the product name.

### Log-level name snapshots

Current reports use saved money snapshots but current `BagType.name` for labels. Because product rename should update linked `BagType.name`, old reports may show the new product name for old records. If strict historical label preservation is required, add `bag_type_name_snapshot` to `CutLog` and `ExtraCutWorkLog` in a later batch. This is not required for the first sync batch unless the business confirms old report labels must never change.

## F - Proposed Sync Service Design

### Service

Recommended file: `modules/attendance/product_sync_service.py`

Recommended class: `AttendanceProductSyncService`

Dependencies:

- main app DB session factory
- attendance DB session factory
- `modules.inventory.models.Product`
- `modules.attendance.models.BagType`, `CutLog`, `ExtraCutWorkLog`
- logging

### Inputs/outputs

Input:

- optional `include_inactive_products=True` for full reconciliation.

Output:

- created linked rows count
- updated linked rows count
- deactivated linked rows count
- legacy rows affected count
- incomplete active linked item list
- warnings, such as duplicate product names or name conflicts

### Transaction boundary

Do not use a cross-database transaction.

Recommended flow:

1. Read products from main DB into plain DTOs.
2. Close main DB session.
3. Open attendance DB transaction.
4. Upsert/deactivate `BagType` rows.
5. Commit attendance DB.

### Responsibilities

For active new products:

- create linked `BagType`;
- `name = product.product_name`;
- `quota_quantity = 0`;
- `excess_unit_price = 0`;
- `is_excluded_from_attendance = False`;
- `is_product_linked = True`;
- set `source_product_id`;
- set `source_product_name_snapshot`.

For renamed products:

- update linked `BagType.name`;
- update `source_product_name_snapshot`;
- preserve quota, excess price, active state, and exclusion checkbox;
- do not rewrite old log snapshots.

For inactive or missing products:

- if no attendance history exists: deactivate in V1;
- if attendance history exists: keep row, deactivate it, and mark it legacy/stale;
- do not hard delete automatically.

For old manual BagTypes:

- with history: mark legacy and deactivate from new selection;
- without history: deactivate in V1;
- avoid name-based auto-linking unless there is a deliberate migration rule and backup.

Never overwrite:

- `quota_quantity`;
- `excess_unit_price`;
- `is_excluded_from_attendance`;
- historical log snapshots.

### Incomplete active linked items

The service should return rows matching:

```text
is_product_linked == true
AND is_active == true
AND is_excluded_from_attendance == false
AND (quota_quantity == 0 OR excess_unit_price == 0)
```

### Recommended sync trigger points

V1:

- when entering the large `Chấm công` tab, before warning detection;
- when opening/reloading attendance price settings;
- optionally at app startup as best-effort, with logging but no blocking popup.

Not recommended:

- syncing on every search keystroke;
- syncing inside report generation.

Future:

- add product-changed event integration after inventory product create/update/delete if an app-wide event pattern is introduced.

## G - Warning Popup / Navigation Design

### Popup condition

After sync, show a warning when entering the large `Chấm công` tab if incomplete active linked items exist:

```text
is_excluded_from_attendance == false
AND (quota_quantity == 0 OR excess_unit_price == 0)
```

### Suggested Vietnamese content

Title:

```text
Thiếu cấu hình việc cắt
```

Body:

```text
Có {count} mặt hàng đã đồng bộ sang việc cắt nhưng chưa cấu hình đủ số lượng khoán hoặc đơn giá vượt khoán.

Vui lòng vào Cài đặt giá chấm công để nhập đủ thông tin, hoặc tick "Không dùng cho chấm công" nếu mặt hàng này không dùng để chấm công.

Một số mục cần kiểm tra:
- {name_1}
- {name_2}
- {name_3}
```

Buttons:

- `Đi tới cài đặt`
- `Để sau`

### Navigation behavior

When the user clicks `Đi tới cài đặt`:

1. switch to large tab `Cài đặt`;
2. open subtab `Cài đặt giá chấm công`;
3. focus the CUT work settings section;
4. highlight incomplete rows with a red border/background;
5. scroll/select the first incomplete row if feasible.

### Popup frequency

Recommended V1:

- show when entering the large Attendance tab if incomplete items exist;
- do not repeatedly show while the user is already on that tab;
- show again on a later tab entry until the issue is resolved or excluded.

This matches the user request while avoiding repeated interruptions during a single stay in the tab.

## H - Settings UI Design

### CUT work settings table

The CUT work list should show product-linked items with:

- product name / CUT work name;
- quota quantity;
- excess unit price;
- checkbox `Không dùng cho chấm công`.

### Behavior

Product-linked names:

- should not be freely edited in attendance settings;
- source of truth is product name from inventory.

Editable fields:

- quota quantity;
- excess unit price;
- `Không dùng cho chấm công`.

Incomplete highlight:

- red border/background when:
  - product-linked;
  - active;
  - not excluded;
  - quota is zero or excess price is zero.

Checkbox semantics:

- checked means intentionally not used for attendance;
- checked rows do not trigger popup;
- checked rows should not appear in day-entry selection;
- unchecked rows are expected to be configured.

Legacy rows:

- should not be mixed silently with active product-linked rows;
- show in a separate legacy/inactive section or behind an `Hiện mục cũ` toggle;
- mark as `Dữ liệu cũ` or `Không còn dùng`;
- preserve for historical reports.

## I - Day-Entry Behavior

Recommended available list for both CUT employee bag work and BLOW extra CUT/VK:

```text
is_active == true
AND is_product_linked == true
AND is_excluded_from_attendance == false
AND quota_quantity > 0
AND excess_unit_price > 0
```

Also include historical bag type ids already used by the currently loaded record so old records can be reloaded safely.

Rationale:

- excluded products should not be selectable;
- incomplete products should not silently create zero/incorrect attendance amounts;
- the popup and settings red highlight guide users to configure items before use;
- BLOW VK should use the same configured CUT work list;
- existing decimal quantity support remains unchanged.

## J - Product Change Event Integration

Current product create/update/delete flow reloads the product list locally in `modules/inventory/ui/product_list_view.py`. No app-wide `product_changed` signal was found.

Recommended V1:

- sync when entering Attendance;
- sync when opening/reloading Attendance price settings.

This means product changes are picked up on the next relevant attendance action.

Future improvement:

- add a product changed signal/event after:
  - `InventoryController.create_product(...)`;
  - `InventoryController.update_product(...)`;
  - `InventoryController.delete_product(...)`;
- trigger the sync service in response, or mark attendance sync dirty and run it on next tab entry.

## K - Migration Strategy

### Safe migration steps

1. Create a backup before migration.
2. Add new `BagType` columns idempotently in `modules/attendance/db.py`.
3. Add a unique index for `source_product_id` where not null, if supported by the chosen migration approach.
4. Preserve all existing `BagType` rows.
5. Detect history using `CutLog` and `ExtraCutWorkLog`.
6. Mark existing manual rows with history as legacy and inactive from new selection.
7. Deactivate existing manual rows without history in V1.
8. Run initial sync from current active products.
9. Preserve existing `CutLog` and `ExtraCutWorkLog` rows.
10. Continue using saved snapshots for report money totals.

### Rollback and repair risks

If sync creates wrong items:

- product-linked rows can be identified by `is_product_linked` and `source_product_id`;
- quota/price should remain attendance-owned, so sync reruns should not destroy user configuration;
- deactivation is easier to recover from than hard deletion.

If product ids change:

- links become stale because `source_product_id` is external;
- `source_product_name_snapshot` helps diagnose stale rows;
- manual repair tooling may be needed.

If only one DB is restored:

- sync can recreate missing linked rows from products;
- if attendance DB has links to product ids that no longer exist, those rows should be deactivated/stale rather than deleted;
- backup documentation should emphasize restoring both DBs together.

## L - Backup / Restore Check

### Files inspected

- `modules/settings/backup_service.py`
- `tests/test_settings_backup.py`
- `shell/app_window.py`

### Current behavior

`UserBackupService.create_user_backup()` includes both:

- main app DB from `settings.db_path`;
- attendance DB from `get_attendance_db_path()`.

The backup manifest records whether each DB was present and included.

### Recommendation

The current backup direction is compatible with product-attendance sync because both DBs are backed up when present. Implementation should still add explicit documentation or diagnostics wording that product-linked attendance configuration depends on both DBs being restored consistently.

No backup code should be changed as part of the investigation-only task.

## M - Test Plan For Implementation Batch

### Schema migration

- new columns are added to `bag_types`;
- migration is idempotent;
- existing rows are preserved;
- existing `CutLog` and `ExtraCutWorkLog` rows remain readable;
- old integer and decimal quantities still load.

### Initial sync

- active products create linked `BagType` rows;
- only product name is imported;
- quota defaults to `0`;
- excess unit price defaults to `0`;
- excluded defaults to `False`;
- product selling price, cost, stock, unit, inventory, sales data are not imported.

### Config preservation

- user sets quota and excess price;
- sync rerun does not overwrite quota or price;
- sync rerun does not overwrite `is_excluded_from_attendance`.

### Product rename

- linked `BagType.name` updates;
- `source_product_name_snapshot` updates;
- old log amount snapshots remain unchanged.

### Product inactive/delete

- inactive product deactivates/hides linked `BagType`;
- hard-deleted product missing from source deactivates/hides linked `BagType`;
- rows with history are preserved;
- no orphan logs are created.

### Legacy BagType

- legacy rows with history are not hard deleted;
- legacy rows without history are deactivated in V1;
- legacy rows are not shown as normal active product-linked rows.

### Incomplete detection

- quota `0` triggers warning;
- price `0` triggers warning;
- both configured means no warning;
- `Không dùng cho chấm công` checked means no warning;
- all incomplete items excluded means no popup.

### Settings UI

- product-linked names are read-only;
- quota and price editable;
- checkbox text is exactly `Không dùng cho chấm công`;
- checked checkbox means excluded from attendance;
- red highlight appears only for incomplete non-excluded rows;
- settings navigation from popup opens the correct tab/section;
- first incomplete row is selected or scrolled into view if implemented.

### Large Attendance tab popup

- appears on tab entry when incomplete rows exist;
- does not appear while already staying on the same tab;
- appears again on a later tab entry until resolved;
- `Đi tới cài đặt` navigates correctly;
- `Để sau` dismisses only the current popup.

### Day-entry

- CUT employee list uses product-linked configured rows;
- BLOW VK list uses the same available configured rows;
- excluded rows are hidden;
- incomplete rows are hidden under the recommended V1 behavior;
- historical inactive ids still reload for existing records;
- decimal quantity behavior remains unchanged.

### Reports

- old historical 10-day reports still build;
- old historical 30-day reports still build;
- new product-linked records report correctly;
- saved amount snapshots remain the source of truth for totals.

### Backup

- backup includes both DBs;
- restoring both DBs preserves product-linked attendance config;
- tests cover missing one DB if current backup system supports it.

### CI

- temp main DB and temp attendance DB are isolated;
- no hardcoded local paths;
- sync tests run on Windows GitHub runner with Python 3.12.

## N - Final Recommendation

Keep two databases and implement one-way sync from main app products into attendance `BagType` rows. Do not merge databases for V1.

Recommended implementation batches:

1. Schema + sync service + tests, with no popup/UI changes yet.
2. Settings UI: product-linked rows, read-only names, `Không dùng cho chấm công`, and red incomplete-row highlight.
3. Attendance tab popup and navigation to attendance price settings.
4. Day-entry filtering for configured product-linked CUT work and BLOW VK work, plus tab-entry/settings sync triggers.
5. Legacy cleanup refinements after real data is reviewed.

Highest-risk areas:

- current unique `BagType.name` versus non-unique `Product.product_name`;
- preserving old historical reports while product names can change;
- avoiding hard deletion of historical bag types;
- keeping backup/restore expectations clear for two linked SQLite databases.

First implementation work should be the schema and sync service with isolated tests. First manual testing should cover product create, rename, deactivate/delete, attendance settings warning state, and day-entry selection for both CUT employees and BLOW VK.
