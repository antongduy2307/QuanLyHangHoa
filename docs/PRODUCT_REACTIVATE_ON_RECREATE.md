# Product Reactivate On Recreate

## A. Files Changed

- `modules/inventory/repository.py`
  - Added `get_product_by_code_base(...)` that includes inactive products.
- `modules/inventory/service.py`
  - Updated `InventoryService.create_product(...)` to check existing product codes before insert.
  - Added safe inactive-product reactivation behavior.
  - Reused a shared price synchronization helper for create, update, and reactivation.
- `tests/test_inventory_service.py`
  - Added regression coverage for inactive-product reactivation and validation paths.
- `tests/test_attendance_product_sync.py`
  - Added coverage that product reactivation makes the linked attendance CUT work active/configurable again.

## B. Root Cause

`Product.product_code_base` has a database-level unique constraint.

When a product with history was deleted, `delete_product(...)` preserved history by setting `Product.is_active = False`. Later, `create_product(...)` did not check inactive rows before inserting a new product with the same code, so SQLite raised:

`UNIQUE constraint failed: products.product_code_base`

The failure happened below the service validation layer, which exposed a low-level database error instead of a domain-specific product validation path.

## C. Reactivation Behavior

`InventoryService.create_product(...)` now:

1. Normalizes `product_code_base` and `product_name` through existing validators.
2. Looks up an existing product by normalized code, including inactive products.
3. If the code belongs to an active product, raises `ValidationError("Mã hàng đã tồn tại.")`.
4. If the code belongs to an inactive product with the same normalized name and same unit mode:
   - sets `is_active = True`;
   - preserves the existing product id;
   - preserves inventory balance, invoice, return, receipt, adjustment, and external attendance links;
   - updates enabled price rows from the new create payload.
5. If no existing code is found, creates a new product as before.

Unused products that are hard-deleted still follow the existing hard-delete behavior.

## D. Unit Mode Safety

Reactivation rejects a different requested `unit_mode` with:

`Mã hàng này đã tồn tại với kiểu đơn vị khác. Không thể khôi phục bằng kiểu đơn vị mới.`

This avoids changing the interpretation of historical stock, invoice, return, and attendance-linked quantities.

## E. Attendance Sync Impact

Product id is preserved on reactivation, so `BagType.source_product_id` remains valid.

`AttendanceProductSyncService` already treats active products as source of truth and reactivates linked BagTypes in `_update_linked_bag_type(...)`. A regression test now verifies:

- product becomes inactive;
- sync deactivates/marks linked BagType legacy;
- product is reactivated with the same id;
- sync reactivates the existing linked BagType and clears legacy state.

## F. Error Message Behavior

- Active duplicate code: friendly `ValidationError`, no raw SQLite `IntegrityError`.
- Inactive same code/name/unit: reactivated without duplicate insert.
- Inactive same code but different name:
  `Mã hàng này đã từng tồn tại với tên khác. Vui lòng kiểm tra lại mã hàng hoặc khôi phục sản phẩm cũ.`
- Inactive same code/name but different unit mode:
  `Mã hàng này đã tồn tại với kiểu đơn vị khác. Không thể khôi phục bằng kiểu đơn vị mới.`

## G. Tests / Verification

Commands run:

- `python -m unittest tests.test_inventory_service`
  - Result: 25 tests passed.
- `python -m unittest tests.test_attendance_product_sync`
  - Result: 14 tests passed.
- `python -m unittest tests.test_product_search_ui`
  - Result: 4 tests passed.
- `python -m compileall core modules tests shell`
  - Result: completed successfully.
- `python -m unittest discover -s tests -p "test*.py" -t .`
  - Result: 480 tests passed.

Notes:

- The requested `tests.test_inventory_ui` module does not exist in this repository; inventory UI coverage found locally is `tests.test_product_search_ui`.
- PowerShell emitted the existing local profile execution-policy warning before commands; test commands still completed.
- Existing mocked update-service and diagnostics failure logs appeared during full discovery; the suite completed successfully.

## H. Caveats

- Reactivation updates price rows from the create dialog payload but does not change product code, name, unit mode, balance, or historical rows.
- Same-code inactive product with a different name remains a validation error because automatically renaming a historical product could confuse old reports and external attendance links.
