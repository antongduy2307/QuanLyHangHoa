# Attendance Product CUT Sync Batch 1

Batch 1 implements the schema and service foundation for one-way synchronization from inventory products to attendance CUT work items. It does not add popup behavior, settings-row highlighting, settings navigation, day-entry filtering, report UI changes, database merging, or cross-database foreign keys.

## A. Files Changed

- `modules/attendance/models.py`
- `modules/attendance/db.py`
- `modules/attendance/product_sync_service.py`
- `tests/test_attendance_product_sync.py`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH1.md`

## B. Schema Changes

`BagType` now has product-sync metadata fields:

- `is_product_linked`
  - Boolean, not null, default false.
  - Marks attendance CUT work rows created from inventory products.
- `source_product_id`
  - Integer, nullable.
  - External reference to main app `products.id`.
  - No cross-database foreign key.
- `source_product_name_snapshot`
  - String, nullable.
  - Latest product name observed during sync.
- `is_excluded_from_attendance`
  - Boolean, not null, default false.
  - Foundation for the future `Không dùng cho chấm công` checkbox.
- `is_legacy`
  - Boolean, not null, default false.
  - Marks preserved old/manual rows that should not be used as normal active product-linked work.

The existing `BagType.name` uniqueness remains unchanged in this batch.

## C. Migration Behavior

`modules/attendance/db.py` adds the new columns idempotently in `_upgrade_attendance_schema`.

Existing rows are preserved with defaults:

- `is_product_linked = false`
- `source_product_id = null`
- `source_product_name_snapshot = null`
- `is_excluded_from_attendance = false`
- `is_legacy = false`

The migration also creates a partial unique index:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ix_bag_types_source_product_id_unique
ON bag_types (source_product_id)
WHERE source_product_id IS NOT NULL
```

This protects one linked attendance `BagType` per product id without requiring cross-database foreign keys.

## D. Sync Service Behavior

New file: `modules/attendance/product_sync_service.py`

Main class:

- `AttendanceProductSyncService`

Public methods:

- `sync_products_to_cut_work() -> AttendanceProductSyncResult`
- `list_incomplete_cut_work_items() -> list[ProductCutWorkItem]`

DTOs:

- `ProductCutSyncProduct`
- `ProductCutWorkItem`
- `AttendanceProductSyncResult`

The service reads only:

- `Product.id`
- `Product.product_name`
- `Product.is_active`

It does not read or import product selling price, cost, stock, unit mode, inventory quantity, sales data, customer data, or order data.

Transaction boundary:

1. Read product rows from the main DB into DTOs.
2. Close the main DB session.
3. Open an attendance DB transaction.
4. Upsert/deactivate attendance `BagType` rows.
5. Commit attendance DB changes.

Active products create linked `BagType` rows with:

- `name = product.product_name`
- `quota_quantity = 0`
- `excess_unit_price = 0`
- `unit_price = 0`
- `is_active = true`
- `is_product_linked = true`
- `source_product_id = product.id`
- `source_product_name_snapshot = product.product_name`
- `is_excluded_from_attendance = false`
- `is_legacy = false`

Existing linked rows are updated for product rename by changing:

- `name`
- `source_product_name_snapshot`

The sync preserves:

- `quota_quantity`
- `excess_unit_price`
- `is_excluded_from_attendance`
- historical `CutLog` rows
- historical `ExtraCutWorkLog` rows

Inactive or missing products deactivate the linked attendance row. If history exists, or if the source product is missing, the row is also marked legacy. Rows are not hard deleted.

## E. Conflict Policy

Batch 1 keeps the existing `BagType.name` uniqueness and does not append suffixes or merge products by name.

The service returns warnings and skips ambiguous operations for:

- duplicate active product names;
- product names that conflict with existing manual `BagType.name`;
- product renames that would collide with another `BagType.name`;
- duplicate attendance `source_product_id` rows if detected.

Non-conflicting rows continue syncing when safe.

## F. Incomplete Detection

Incomplete items are returned as `ProductCutWorkItem` DTOs when:

```text
is_product_linked == true
AND is_active == true
AND is_excluded_from_attendance == false
AND (quota_quantity == 0 OR excess_unit_price == 0)
```

Excluded rows are not reported incomplete. This is the service foundation for the future Attendance tab popup and Settings red highlight.

## G. Legacy Handling

Manual/default `BagType` rows are never hard deleted in Batch 1.

When sync runs:

- manual rows with `CutLog` or `ExtraCutWorkLog` history are marked `is_legacy = true` and deactivated;
- manual rows without history are deactivated and preserved;
- linked rows for inactive/missing products are deactivated and preserved;
- linked rows with history are marked legacy when deactivated.

This preserves old attendance history and avoids orphaning reports or record reloads.

## H. Tests / Verification

Added focused tests in `tests/test_attendance_product_sync.py` for:

- schema migration columns and idempotency;
- initial product sync;
- config preservation;
- product rename;
- inactive product handling;
- hard-deleted/missing product handling;
- manual bag type with `CutLog` history;
- manual bag type with `ExtraCutWorkLog` history;
- manual bag type without history;
- incomplete detection;
- duplicate active product name warning;
- manual name conflict warning;
- product rename conflict warning;
- temp DB isolation through `LOCALAPPDATA`.

Verification run:

```text
python -m unittest tests.test_attendance_product_sync
python -m unittest tests.test_attendance_batch1
python -m unittest tests.test_settings_backup
python -m unittest discover tests
python -m compileall modules tests core
```

Results:

- `tests.test_attendance_product_sync`: 13 tests passed.
- `tests.test_attendance_batch1`: 3 tests passed.
- `tests.test_settings_backup`: 4 tests passed.
- Full discovery: 378 tests passed.
- Compileall: completed successfully.

Expected update-service and diagnostics log traces appeared during full discovery; they did not fail tests.

## I. Caveats / Next Batch Recommendation

The main remaining design risk is `Product.product_name` not being unique while `BagType.name` is unique. Batch 1 intentionally returns warnings and skips ambiguous rows instead of weakening the existing schema or silently renaming attendance work items.

Recommended next batch:

1. Add settings UI support for linked product rows, read-only linked names, editable quota/price, and the `Không dùng cho chấm công` checkbox.
2. Add red highlight for incomplete linked rows.
3. Add Attendance tab warning popup and navigation to settings.
4. Add day-entry filtering for active, product-linked, configured, non-excluded CUT work items.
