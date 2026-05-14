# PROJECT_HANDOFF_SUMMARY

Tài liệu này là bản bàn giao trạng thái dự án `QuanLyHangHoa` tại thời điểm 2026-05-13. Mục tiêu là giúp một phiên ChatGPT/Codex mới có thể hiểu phần lớn bối cảnh kỹ thuật, nghiệp vụ, các quyết định đã chốt, các tính năng lớn vừa làm, và các điểm cần cẩn trọng khi tiếp tục phát triển.

Ngôn ngữ mô tả dùng tiếng Việt. Tên file, class, function, table, command line và code identifier được giữ nguyên tiếng Anh.

## A. Tổng quan dự án

### 1. App name và mục đích

`QuanLyHangHoa` là ứng dụng desktop nội bộ để quản lý hàng hóa và vận hành cửa hàng/xưởng, bao gồm:

- Quản lý hàng hóa, tồn kho, nhập kho, điều chỉnh kho.
- Bán hàng, hóa đơn, trả hàng.
- Khách hàng, công nợ, thanh toán.
- Đặt hàng.
- Báo cáo và lịch sử giao dịch.
- Chấm công sản xuất cho tổ thổi và tổ cắt.
- Cài đặt, sao lưu, diagnostics, cập nhật phiên bản.

### 2. Loại ứng dụng hiện tại

- Python desktop app.
- UI dùng Qt qua `PySide6`/Qt-style widgets.
- ORM dùng SQLAlchemy.
- Database local dùng SQLite.
- Có hai SQLite DB tách riêng:
  - Main app DB: `app.db`.
  - Attendance DB: `attendance.db`.
- Release desktop dùng PyInstaller qua `desktop_app.spec`.
- Installer Windows dùng Inno Setup qua `installer/QuanLyHangHoa.iss`.
- CI/CD dùng GitHub Actions trên Windows runner.

### 3. Main business domains

Các domain chính hiện có trong repo:

- `modules/inventory`: hàng hóa, tồn kho, nhập kho, điều chỉnh kho, effect tồn kho.
- `modules/sales`: bán hàng, hóa đơn, dòng hóa đơn, thanh toán theo hóa đơn.
- `modules/returns`: trả hàng, dòng trả hàng, hoàn tồn kho/công nợ.
- `modules/customer`: khách hàng, công nợ, ledger thanh toán.
- `modules/orders`: đơn đặt hàng/yêu cầu đặt hàng.
- `modules/reporting`: báo cáo nghiệp vụ.
- `modules/attendance`: nhân viên, chấm công, báo cáo chấm công, cấu hình giá, đồng bộ CUT work từ sản phẩm, effect tồn kho từ sản lượng CUT/VK.
- `modules/settings`: cài đặt chung, backup, diagnostics, update check, admin diagnostics.
- `shell`: app shell, navigation, page composition.
- `shared`: widgets, UI utilities, shared dialogs/helpers.

### 4. Version/release status

Version hiện tại detect được:

- `core/version.py`: `APP_VERSION = "0.8.1"`.
- `version.json`: `"version": "0.8.1"`.
- `version.json` hiện trỏ installer URL tới repo GitHub:
  `https://github.com/antongduy2307/QuanLyHangHoa/releases/download/v0.8.1/QuanLyHangHoa-Setup-v0.8.1.exe`

Lưu ý: `installer/QuanLyHangHoa.iss` có `#define MyAppVersion GetEnv("APP_VERSION")` fallback `"0.7.3"`, nhưng release scripts thường truyền version khi build. Trước khi release cần kiểm tra lại `version.json`, tag, installer name, và Inno version.

### 5. Important repo/tooling files

- `main.py`: entrypoint chạy app Qt.
- `core/`: config, paths, DB init/migrations, logging, update/version, backup/diagnostics helpers.
- `shell/`: bootstrap app, main window, navigation, page wiring.
- `modules/`: các domain business modules.
- `shared/`: widgets, UI helper, message box, theme, reusable table selection mode.
- `tests/`: unittest suite, gồm cả Qt offscreen tests.
- `.github/workflows/ci.yml`: CI unittest + compileall.
- `.github/workflows/release.yml`: release workflow, build exe/installer, upload artifact.
- `scripts/`: build/check version scripts, PyInstaller/Inno orchestration.
- `desktop_app.spec`: PyInstaller spec.
- `installer/QuanLyHangHoa.iss`: Inno Setup installer script.
- `requirements.txt`: dependencies.
- `version.json`: update manifest.

## B. Architecture overview

### 1. Main shell/window

Các file chính:

- `main.py`
- `shell/bootstrap.py`
- `shell/app_window.py`

Luồng khởi động chính:

1. `main.py` tạo `QApplication`.
2. Gọi `shell.bootstrap.bootstrap_application()`.
3. `bootstrap_application()`:
   - cấu hình logging/theme/runtime;
   - gọi `core.db.init_db()` trước khi tạo UI DB-backed pages;
   - load module packages trong `ACTIVE_MODULE_PACKAGES`;
   - tạo `AppWindow`;
   - setup startup update check timer.
4. `AppWindow` dựng các large tabs/pages từ module registry.

`shell/bootstrap.py` hiện có:

```python
ACTIVE_MODULE_PACKAGES = (
    "modules.inventory",
    "modules.sales",
    "modules.orders",
    "modules.customer",
    "modules.reporting",
    "modules.attendance",
    "modules.settings",
)
```

Large tab order hiện tại về cơ bản là:

1. Hàng hóa / inventory.
2. Bán hàng / sales.
3. Đặt hàng / orders.
4. Khách hàng / customer.
5. Báo cáo / reporting.
6. Lịch sử / history.
7. Chấm công / attendance.
8. Cài đặt / settings.

`HistoryPage` được insert trong `AppWindow` trước attendance/settings. `AppWindow` cũng giữ `_module_pages` để refresh liên module.

Một số signal/event quan trọng trong `AppWindow`:

- Inventory/product changes refresh sales/customer/history/reporting/orders where needed.
- Sales/returns/customer events refresh history/customer/reporting/inventory.
- Settings `attendance_config_changed` refresh attendance page.
- Entering Attendance large tab chạy product-to-attendance sync và warning popup cấu hình CUT.
- Settings page có method `open_attendance_price_settings(first_incomplete_id=None)` để mở đúng tab cấu hình giá chấm công.

### 2. Module pattern

Phần lớn modules theo pattern:

- `models.py`: SQLAlchemy ORM models.
- `repository.py`: DB query/persistence functions.
- `service.py`: business logic, validation, transaction orchestration.
- `controller.py`: bridge giữa UI và service.
- `ui/`: QWidget/page/dialog/table view.
- `tests/test_*.py`: unittest coverage theo domain.

Không phải module nào cũng có đủ tất cả lớp, nhưng pattern chung là:

- UI không nên chứa business rule phức tạp.
- Service giữ validation và rollback/apply.
- Repository giữ query chi tiết.
- Controller chuẩn hóa API cho UI.

### 3. Database/session pattern

Main DB:

- File path mặc định: `settings.db_path`, thường là `<LOCALAPPDATA>/QuanLyHangHoa/app.db`; fallback local `data/app.db`.
- Init: `core.db.init_db()`.
- Engine/session:
  - `core.db.get_engine()`
  - `core.db.SessionFactory`
  - `core.db.get_session()`
  - `core.db.reset_engine_cache()`

Attendance DB:

- File path: `modules.attendance.db.get_attendance_db_path()`, thường là `<LOCALAPPDATA>/QuanLyHangHoa/attendance.db`.
- Init: `modules.attendance.db.init_attendance_db()`.
- Engine/session:
  - `modules.attendance.db.get_attendance_engine()`
  - `modules.attendance.db.AttendanceSessionLocal`
  - `modules.attendance.db.get_attendance_session()`
  - `modules.attendance.db.reset_attendance_engine_cache()`

Rủi ro đã từng gặp:

- Nếu test/UI tạo DB connection trước `init_db()`, SQLite có thể tạo file rỗng, sau đó query `invoices` gây `sqlite3.OperationalError: no such table: invoices`.
- Settings và engine đều có cache; test phải reset cache trước/sau khi đổi temp runtime dir.
- Test temp dirs không nên nằm trong `tests/_tmp` hoặc `tests/_diagnostics_tmp` vì có thể gây permission warnings/locked dirs trong Git.

### 4. Configuration/path pattern

Các file chính:

- `core/config.py`
- `core/paths.py`

`core/config.py`:

- `DEFAULT_APP_NAME = "QuanLyHangHoa"`.
- `Settings` chứa:
  - `app_name`
  - `app_data_dir`
  - `db_path`
  - `log_dir`
  - `export_dir`
  - `backup_dir`
  - `temp_dir`
  - `log_level`
  - update manifest URL/timeouts/retries/startup delay.
- `get_settings()` có cache.

`core/paths.py`:

- Nếu có `LOCALAPPDATA`, runtime nằm trong `%LOCALAPPDATA%\QuanLyHangHoa`.
- Nếu không, fallback về `data/` trong repo/app folder.
- Main DB mặc định là `app.db`.
- Attendance DB nằm cùng app data dir với tên `attendance.db`.
- Logs/exports/backups/temp nằm dưới runtime dir.

### 5. Error handling/UI message pattern

- UI dùng `shared.widgets.message_box.MessageBox` cho info/warning/error/confirm.
- Domain/service validation thường raise `ValidationError` hoặc service-level error rõ nghĩa.
- UI nên hiển thị thông báo thân thiện, không để raw `sqlite3.IntegrityError` hoặc `OperationalError` lộ trực tiếp cho user.
- Logging dùng `core.logging`/standard logging. Các lỗi sync/inventory diagnostics nên log context như `daily_record_id`, `employee_id`, `date`.

## C. Databases and schemas

### 1. Main app DB

Main DB do `core.db.Base` quản lý, khởi tạo bởi `core.db.init_db()`.

Các nhóm bảng chính:

- Products/hàng hóa:
  - `products`
  - `product_prices`
- Inventory/tồn kho:
  - `inventory_balances`
  - `inventory_receipts`
  - `inventory_receipt_items`
  - `inventory_adjustments`
  - `inventory_adjustment_items`
  - `inventory_stock_effects`
- Sales:
  - `invoices`
  - `invoice_items`
- Returns:
  - `return_invoices`
  - `return_invoice_items`
- Customers/debt:
  - `customers`
  - `customer_balance_ledgers`
- Orders:
  - `order_requests`
  - `order_request_items`

### 2. Attendance DB

Attendance DB do `modules.attendance.models.AttendanceBase` quản lý, khởi tạo bởi `modules.attendance.db.init_attendance_db()`.

Các bảng chính:

- `employees`
- `periods`
- `employee_shift_periods`
- `daily_records`
- `work_types`
- `work_logs`
- `bag_types`
- `cut_logs`
- `extra_cut_work_logs`

### 3. `Product`

File:

- `modules/inventory/models.py`

Class/table:

- `Product`
- `products`

Fields chính:

- `id`: primary key.
- `product_code_base`: unique/indexed mã hàng gốc.
- `product_name`: indexed tên hàng.
- `unit_mode`: enum/string, `BAO_KG` hoặc `BICH`.
- `is_active`: soft-delete/deactivate flag.
- `created_at`, `updated_at`.

Relationships:

- `prices`: `ProductPrice`.
- `inventory_balance`: `InventoryBalance`.
- `receipt_items`: `InventoryReceiptItem`.
- `adjustment_items`: `InventoryAdjustmentItem`.
- `invoice_items`: `InvoiceItem`.
- `return_items`: `ReturnInvoiceItem`.

Important constraints/behavior:

- `product_code_base` unique cả active và inactive.
- Product có history không hard-delete, chỉ set `is_active=False`.
- Product inactive khi tạo lại cùng code/name sẽ được reactivate thay vì insert row mới.
- `Product.id` là external source cho attendance `BagType.source_product_id`.

### 4. `InventoryBalance`

File:

- `modules/inventory/models.py`

Class/table:

- `InventoryBalance`
- `inventory_balances`

Fields chính:

- `id`
- `product_id`: unique FK tới `products.id`.
- `on_hand_bao_decimal`: Numeric cho sản phẩm `BAO_KG`.
- `on_hand_kg_decimal`: Numeric, hiện không phải luồng chính cho chấm công.
- `on_hand_bich_integer`: Numeric/integer-like cho sản phẩm `BICH`.
- timestamps.

Behavior:

- `BAO_KG` stock chính dùng `UnitType.BAO`.
- `BICH` stock chính dùng `UnitType.BICH`.
- Decimal quantities được hỗ trợ ở service/inventory effect.
- Negative stock có thể được cho phép tùy luồng hiện tại; không nên tự ý thay đổi khi chưa audit toàn bộ sales/inventory logic.

### 5. `InventoryStockEffect`

File:

- `modules/inventory/models.py`

Class/table:

- `InventoryStockEffect`
- `inventory_stock_effects`

Mục đích:

- Durable ledger/effect layer cho sản lượng `CUT_LOG` và `EXTRA_CUT_WORK_LOG` từ attendance update vào tồn kho main DB.
- Dùng để rollback/apply idempotent theo `DailyRecord`.

Fields chính:

- `id`
- `source_type`: ví dụ `ATTENDANCE_DAILY_RECORD`.
- `source_id`: `DailyRecord.id` từ attendance DB.
- `source_line_type`: `CUT_LOG` hoặc `EXTRA_CUT_WORK_LOG`.
- `source_line_id`: `CutLog.id` hoặc `ExtraCutWorkLog.id`; đã được harden không cho `None` ở service.
- `attendance_employee_id`
- `attendance_work_date`
- `attendance_bag_type_id`
- `product_id`: FK main DB tới `products.id`.
- `quantity_delta`: Numeric, số lượng tăng tồn.
- `unit_type`: `BAO` hoặc `BICH`.
- `movement_datetime`
- `note`
- `created_at`, `updated_at`.

Indexes/constraints:

- Index theo `(source_type, source_id)`.
- Index theo `product_id`.
- Unique key theo `(source_type, source_id, source_line_type, source_line_id)`.

Important:

- Rollback luôn theo `(source_type, source_id)`, không phụ thuộc line id cũ vì attendance logs có thể bị clear/recreate khi edit.
- `source_line_id` vẫn bắt buộc để duplicate line protection có ý nghĩa.

### 6. `Invoice` và `InvoiceItem`

File:

- `modules/sales/models.py`

Class/table:

- `Invoice` / `invoices`
- `InvoiceItem` / `invoice_items`

Fields chính:

- `Invoice.id`
- `invoice_code`: unique.
- `customer_id`: nullable.
- `customer_snapshot_name`
- `invoice_datetime`
- `total_amount`
- `paid_amount`
- `payment_method`
- `note`
- `status`
- `created_at`, `updated_at`

`InvoiceItem` chứa:

- `invoice_id`
- `product_id`
- `unit_type`
- `quantity`
- `unit_price`
- `line_total`
- product snapshot fields.

Behavior:

- Tạo hóa đơn làm giảm tồn kho.
- Có customer debt ledger effects nếu khách hàng/công nợ liên quan.
- Update/delete hóa đơn cần rollback/apply tồn kho và công nợ.

### 7. `ReturnInvoice` và `ReturnInvoiceItem`

File:

- `modules/returns/models.py`

Class/table:

- `ReturnInvoice` / `return_invoices`
- `ReturnInvoiceItem` / `return_invoice_items`

Fields chính:

- `return_code`: unique.
- optional `source_invoice_id`.
- optional `customer_id`.
- customer/product snapshots.
- `is_quick_return`
- `return_datetime`
- `total_amount`
- `handling_mode`

Behavior:

- Trả hàng thường làm tăng tồn kho.
- Có thể tác động công nợ khách hàng.
- Update/delete phải rollback/apply.

### 8. `Customer` và `CustomerBalanceLedger`

File:

- `modules/customer/models.py`

Class/table:

- `Customer` / `customers`
- `CustomerBalanceLedger` / `customer_balance_ledgers`

Fields chính:

- `Customer.current_balance`
- `Customer.total_sales`
- `Customer.is_walk_in`
- `Customer.is_active`
- timestamps.

Ledger fields chính:

- `event_type`
- `ref_type`
- `ref_id`
- `source_ref_type`
- `source_ref_id`
- `display_order`
- `amount_delta`
- `balance_after`
- `transaction_datetime`
- `note`

Important:

- Có migration/logic để tránh collision cho generated invoice payment rows.
- Balance recomputation phải giữ thứ tự ledger ổn định.

### 9. Attendance models

File:

- `modules/attendance/models.py`

`Employee` / `employees`:

- `id`
- `name`: unique.
- `team`: BLOW/CUT.
- `is_active`
- timestamps.
- Delete behavior: hard-delete nếu chưa có `DailyRecord`, deactivate nếu có history.

`DailyRecord` / `daily_records`:

- `id`
- `employee_id`
- `date`
- `period_id`
- `is_absent`
- `status`: `DRAFT` hoặc `DONE`.
- `total_amount_snapshot`
- unique theo employee/date.
- Relationships tới `work_logs`, `cut_logs`, `extra_cut_work_logs`.

`WorkType` / `work_types`:

- `id`
- `name`
- `team`
- `input_type`: quantity/tick.
- `unit_price`
- `config_json`
- `is_active`
- unique `(team, name)`.

`WorkLog` / `work_logs`:

- `daily_record_id`
- `work_type_id`
- `quantity`
- snapshot fields.
- unique `(daily_record_id, work_type_id)`.

`BagType` / `bag_types`:

- `id`
- `name`: unique.
- `unit_price`
- `quota_quantity`
- `excess_unit_price`
- `is_active`
- product sync fields:
  - `is_product_linked`
  - `source_product_id`
  - `source_product_name_snapshot`
  - `is_excluded_from_attendance`
  - `is_legacy`
- Used by `CutLog` and `ExtraCutWorkLog`.

`CutLog` / `cut_logs`:

- `daily_record_id`
- `bag_type_id`
- `quantity`: Numeric(12,3), decimal support.
- `unit_price_snapshot`
- `quota_quantity_snapshot`
- `excess_unit_price_snapshot`
- `amount_snapshot`

`ExtraCutWorkLog` / `extra_cut_work_logs`:

- For BLOW extra CUT/VK work.
- `daily_record_id`
- `bag_type_id`
- `quantity`: Numeric(12,3), decimal support.
- `excess_unit_price_snapshot`
- `amount_snapshot`

## D. Inventory / Hàng hóa module

### 1. Product creation/update/delete

Key files:

- `modules/inventory/models.py`
- `modules/inventory/repository.py`
- `modules/inventory/service.py`
- `modules/inventory/controller.py`
- `modules/inventory/ui/product_list_view.py`

`InventoryService.create_product(...)`:

- Normalize `product_code_base` and `product_name` theo existing rules.
- Validate code/name/unit/prices.
- Check existing product by `product_code_base`, including inactive products.
- Nếu không có existing code: create new `Product`.
- Nếu existing active: raise duplicate validation error.
- Nếu existing inactive: có thể reactivate nếu cùng code/name/unit hợp lệ.

`InventoryService.update_product(...)`:

- Update editable product fields theo current rules.
- Cần cẩn trọng với `unit_mode` nếu sản phẩm có history.

`InventoryService.delete_product(...)`:

- Nếu product không có history: hard-delete.
- Nếu product có history: set `is_active=False`.
- Không hard-delete product đã có invoices/returns/receipts/adjustments/attendance link history.

### 2. Product reactivation behavior

Bug đã được xử lý theo report `docs/PRODUCT_REACTIVATE_ON_RECREATE.md`.

Business rule hiện tại:

- Nếu user tạo product cùng `product_code_base` và cùng `product_name` với một product inactive:
  - Reactivate existing product.
  - Preserve same `Product.id`.
  - Preserve invoices/returns/stock history.
  - Preserve attendance `BagType.source_product_id` link.
  - Không insert row mới.
- Nếu same code nhưng khác name:
  - Raise friendly `ValidationError`.
  - Không để raw `sqlite3.IntegrityError` lộ ra.
- Nếu same code/name nhưng khác `unit_mode` và product có history:
  - Raise friendly `ValidationError`.
  - Không tự đổi unit mode vì có thể phá lịch sử tồn kho/bán hàng/chấm công.

### 3. Active/inactive product listing

Product list UI có filter/include inactive. Inactive products không phải dòng active mặc định nhưng có thể xem tùy chế độ. Reactivated product xuất hiện lại trong list active.

### 4. Inventory stock model

`InventoryBalance` giữ stock hiện tại:

- `BAO_KG`: stock theo `UnitType.BAO` cho các effect chính; không tự động convert sang KG cho attendance.
- `BICH`: stock theo `UnitType.BICH`.
- Decimal quantity được giữ bằng `Decimal`/Numeric, không dùng float cho logic quan trọng.
- Negative stock behavior là logic hiện hữu của inventory/sales; không thay đổi nếu không có batch riêng.

### 5. Receipts

Receipts:

- Key models: `InventoryReceipt`, `InventoryReceiptItem`.
- Tạo receipt làm tăng stock.
- Có history rows để product delete mode biết product có lịch sử.
- Update/delete receipt cần rollback/apply stock theo service hiện tại.

### 6. Adjustments

Adjustments:

- Key models: `InventoryAdjustment`, `InventoryAdjustmentItem`.
- Dùng old/new/delta behavior để điều chỉnh stock.
- Là một loại history khiến product thường bị deactivate thay vì hard-delete.

### 7. Product delete mode

`InventoryController.get_delete_mode(product_id)` được product multi-delete dùng để preview:

- `hard_delete`: product chưa có history.
- `deactivate`: product đã có history.

Execution vẫn gọi `InventoryController.delete_product(product_id)` từng product, không bulk SQL trực tiếp.

### 8. Product link to attendance

`Product.id` được lưu ở `BagType.source_product_id`.

Tác động:

- Product create: product sync tạo linked `BagType`.
- Product rename: product sync update `BagType.name`.
- Product inactive/delete: product sync deactivate/hide linked `BagType` an toàn.
- Product reactivate: product sync có thể active lại linked `BagType` nếu không conflict.

### 9. UI

Key file:

- `modules/inventory/ui/product_list_view.py`

UI product list hỗ trợ:

- Add/edit/search/filter/include inactive.
- Delete button hiện vào multi-delete selection mode.
- Checkbox column bằng `shared/widgets/table_selection_mode.py`.
- Pre-confirm summary hard-delete/deactivate.
- Partial failure summary.
- Search/filter/include inactive thay đổi sẽ exit selection mode để tránh selected hidden rows.

### 10. Tests

Relevant tests:

- `tests/test_inventory_service.py`
- `tests/test_product_search_ui.py`
- `tests/test_attendance_product_sync.py`
- `tests/test_schema_invariants.py`

## E. Sales / Returns / Customer debt

### 1. Sales invoice behavior

Key files:

- `modules/sales/models.py`
- `modules/sales/repository.py`
- `modules/sales/service.py`
- `modules/sales/controller.py`
- `modules/sales/ui/*`

Behavior:

- Creating `Invoice` decreases inventory stock through inventory service/repository.
- Invoice line stores product snapshots so old invoices remain readable after product rename/delete.
- If customer is attached and paid amount is less than total, customer debt ledger changes.
- If `paid_amount > 0`, generated payment ledger row may be created.
- Update/delete invoice must rollback old stock/debt effects then apply latest state.

Do not change sales formulas/business rules casually; they are tightly coupled with inventory and customer debt.

### 2. Return invoice behavior

Key files:

- `modules/returns/models.py`
- `modules/returns/repository.py`
- `modules/returns/service.py`
- return-related UI/controller files.

Behavior:

- Return increases stock for returned products.
- Customer debt/balance can be affected depending return mode/customer.
- Return lines store snapshots.
- Update/delete return must rollback/apply stock and debt.

### 3. Customer debt/payment behavior

Key files:

- `modules/customer/models.py`
- `modules/customer/service.py`
- `modules/customer/repository.py`
- `modules/customer/ui/*`

Behavior:

- Standalone debt payments produce ledger rows.
- Invoice-generated payment rows are represented in ledger.
- Balance recomputation uses ordered ledger.
- Previous fixes addressed `ref_id`/ordering collisions for generated invoice payment rows.

### 4. History page

Key files:

- `modules/sales/ui/transaction_history_view.py`
- history page wiring in `shell/app_window.py`.

History page shows:

- Invoice history.
- Return history.
- Customer payment/debt history where applicable.

Important:

- `TransactionHistoryView.reload()` queries `SalesController.list_transaction_history()` -> `SalesRepository.list_invoices()` -> `invoices`.
- CI previously failed if UI smoke created this view before `init_db()`.
- Fix strategy: tests/app startup must initialize DB schema before DB-backed UI pages.

Delete behavior in history is high risk because deleting invoice/return/payment can affect inventory and customer debt. Multi-delete for `Lịch sử` has been investigated but deliberately deferred.

### 5. Important tests

- `tests/test_sales_*`
- `tests/test_return_*`
- `tests/test_customer_*`
- `tests/test_customer_invoice_payment_migration.py`
- `tests/test_order_service.py`
- `tests/test_order_ui.py`
- `tests/test_smoke.py`

## F. Orders / Reports / History

### 1. Orders

Key files:

- `modules/orders/models.py`
- `modules/orders/service.py`
- `modules/orders/controller.py`
- `modules/orders/ui/*`

Models:

- `OrderRequest`
- `OrderRequestItem`

Current behavior:

- Orders are requests/reservations/business workflow, not direct stock mutation like invoice/receipt.
- `OrderRequest.source_invoice_id` can link converted/completed order to invoice.
- Stock impact should remain in sales/inventory services unless explicitly designed otherwise.

### 2. Reports

Reporting module:

- `modules/reporting/*`

Reports aggregate business data from main DB and are refreshed by shell events. Attendance reports are inside attendance module and covered later.

### 3. History

History is a shell-level page inserted by `AppWindow`, not a normal module tab from registry.

Known limitations:

- Delete is service-specific and risky.
- Multi-delete for history is not implemented.
- Any future history delete work must inspect rollback effects for invoice/return/customer ledgers before adding selection UI.

## G. Attendance / Chấm công module overview

### 1. Main files and subtabs

Key files:

- `modules/attendance/models.py`
- `modules/attendance/db.py`
- `modules/attendance/repository.py`
- `modules/attendance/service.py`
- `modules/attendance/product_sync_service.py`
- `modules/attendance/inventory_effect_service.py`
- `modules/attendance/inventory_diagnostic_service.py`
- `modules/attendance/ui/page.py`
- `modules/attendance/ui/employee_tab.py`
- `modules/attendance/ui/day_entry_tab.py`
- `modules/attendance/ui/report_tab.py`
- `modules/attendance/ui/settings_tab.py`

Attendance page/subtabs:

- `Nhân viên`
- `Chấm công`
- `Báo cáo`
- Attendance settings/price settings are exposed through Settings page and attendance UI components.

### 2. Employee management

`AttendanceEmployeeService`:

- Create/update employees.
- Delete behavior:
  - hard-delete if no `DailyRecord`.
  - deactivate if has `DailyRecord`.

UI:

- `modules/attendance/ui/employee_tab.py`
- Multi-delete selection mode is implemented for employees.
- Delete button enters checkbox selection mode.
- Selected employees are processed one by one via `AttendanceEmployeeService.delete_or_deactivate_employee(employee_id)`.
- Summary shows hard-deleted/deactivated/failed counts.

### 3. Day entry

Key service:

- `AttendanceDayEntryService.save_attendance(payload, *, finalize)`

Concepts:

- Date selection.
- Employee list/status.
- `DRAFT` vs `DONE`.
- `is_absent` handling.
- BLOW team work logs.
- CUT team product-linked work logs.
- BLOW extra CUT/VK logs.
- Decimal quantity for CUT/VK.

Save behavior:

- `finalize=False`: record status `DRAFT`.
- `finalize=True`: record status `DONE`.
- Existing logs are cleared/rebuilt.
- Session is flushed before inventory snapshot is built, so `CutLog.id` and `ExtraCutWorkLog.id` exist.
- Inventory effect service is called after flush.

### 4. DRAFT/DONE/absent inventory effects

Current integrated behavior:

- DRAFT attendance saves attendance only and removes/rolls back prior inventory effects for that record.
- DONE CUT increases linked product stock.
- DONE BLOW extra CUT/VK also increases linked product stock.
- Editing DONE rolls back old inventory effects and applies latest quantities.
- DONE -> DRAFT rolls back inventory effects.
- DONE -> absent rolls back inventory effects.
- Removed CUT/VK lines are rolled back.

### 5. Attendance reports

Reports include:

- 10-day report.
- 30-day report.

Known UI characteristics:

- Table layout adjusted for flexible width.
- Spacer between employee sections.
- Total row.
- Decimal CUT/VK quantities supported.

Reports should continue using snapshots/current logic as implemented; do not change formula/reporting behavior without targeted tests.

### 6. Attendance settings

Attendance price settings have been updated:

- Top-left dropdown `Nhóm cài đặt`.
- Options:
  - `Công việc tổ thổi`
  - `Loại bao tổ cắt`
- Only selected section/table visible at a time.
- CUT manual `Thêm` button removed/hidden.
- Product-linked CUT rows remain editable for:
  - `quota_quantity`
  - `excess_unit_price`
  - `is_excluded_from_attendance` / `Không dùng cho chấm công`
- Product-linked names are read-only.
- Incomplete linked rows highlighted red.

### 7. Important attendance tests

- `tests/test_attendance_batch1.py`
- `tests/test_attendance_product_sync.py`
- `tests/test_attendance_settings_ui.py`
- `tests/test_app_window_attendance_sync.py`
- `tests/test_attendance_day_entry.py`
- `tests/test_attendance_employee_management.py`
- `tests/test_attendance_inventory_effect_service.py`
- `tests/test_attendance_inventory_integration.py`
- `tests/test_attendance_inventory_diagnostics.py`
- `tests/test_attendance_inventory_diagnostics_ui.py`

## H. BLOW team / Tổ thổi business rules

### 1. WorkType types

`WorkType` supports:

- Numeric/quantity work.
- Checkbox/tick work.

Calculation logic lives in:

- `modules/attendance/blow_work.py`

### 2. Quota behavior correction

Important correction:

- Không phải tất cả numeric machine work đều trừ quota `-3`.
- Current implemented rule: only work type named `Thừa máy` uses quota `3`.
- Formula for `Thừa máy`:

```text
amount = max(0, quantity - 3) * unit_price
```

Other numeric work types use:

```text
amount = quantity * unit_price
```

Tick work types use fixed price when checked.

### 3. Quantity defaults

Numeric inputs default theo UI/service hiện tại. Do not cast CUT/VK decimal quantity to int. BLOW regular `WorkLog.quantity` is still integer-like in model.

### 4. Checkbox work like `Phụ găng`

Glove work names are tracked in service:

```python
GLOVE_WORK_NAMES = {"Phụ găng 1 máy", "Phụ găng 2 máy"}
```

These are checkbox/tick style work items.

### 5. BLOW extra CUT / VK

BLOW employees can have extra CUT/VK section:

- UI lets user search/add product-linked CUT items.
- Uses same filtered `BagType` list as CUT day-entry.
- Quantity supports decimal.
- Formula:

```text
amount = quantity * excess_unit_price_snapshot
```

Do not apply CUT employee tiered quota formula to VK.

When `DailyRecord.status == DONE`, VK quantity also increases inventory stock through `AttendanceInventoryEffectService`.

### 6. Report representation

VK/extra CUT appears in attendance reports as extra cut work. Totals include amount snapshots. Formula should remain:

```text
quantity * excess_unit_price_snapshot
```

## I. CUT team / Tổ cắt business rules

### 1. CUT items are product-linked

CUT work items are no longer manually/randomly created as independent bag types. Source of truth is inventory product list:

- `Product.product_name` -> `BagType.name`
- `Product.id` -> `BagType.source_product_id`

### 2. Manual CUT add removed

Attendance price settings no longer exposes CUT `Thêm` button. Existing product-linked rows are configured there, but creation comes from product sync.

### 3. Product-linked `BagType` config

Each linked CUT `BagType` has:

- `quota_quantity`
- `excess_unit_price`
- `is_excluded_from_attendance`
- `is_product_linked`
- `source_product_id`
- `source_product_name_snapshot`
- `is_legacy`

### 4. Incomplete config

Incomplete condition:

```text
is_product_linked == true
AND is_active == true
AND is_excluded_from_attendance == false
AND (quota_quantity == 0 OR excess_unit_price == 0)
```

Behavior:

- Warning popup appears when entering large `Chấm công` tab.
- Settings rows get red highlight.
- Day-entry hides incomplete rows from new selection.
- If `Không dùng cho chấm công` is checked, row is not incomplete and does not trigger popup.

### 5. CUT worker calculation

Formula lives in:

- `modules/attendance/cut_bonus.py`

Current multi-item logic:

- Filter active items with quantity > 0.
- Compute `total_quantity`.
- Compute `quota_average = sum(quota_quantity) / number_of_items`.
- If `total_quantity <= quota_average`: no bonus.
- If any item quantity >= its quota:
  - For item meeting quota: `(quantity - quota) * excess_unit_price`.
  - For item below quota: `quantity * excess_unit_price`.
- Otherwise:
  - Use distributed quota: `max(0, quantity - quota_average_per_item) * excess_unit_price`.

Important:

- Decimal quantity supported.
- No penalty below quota.
- Do not change this formula casually.

### 6. Inventory effect

When `DailyRecord.status == DONE`:

- `CutLog.quantity` increases linked product stock.
- Unit mapping:
  - Product `BAO_KG` -> inventory `UnitType.BAO`.
  - Product `BICH` -> inventory `UnitType.BICH`.

DRAFT/absent/edit behavior:

- DRAFT: no effect, rollback prior effect.
- DONE edit: rollback/apply latest.
- DONE -> DRAFT/absent: rollback.

### 7. Reports

10-day/30-day reports use attendance logs/snapshots. Old historical logs should remain readable even if `BagType` later becomes inactive/legacy/excluded.

## J. Product ↔ Attendance link feature

### 1. Sync service

File:

- `modules/attendance/product_sync_service.py`

Class:

- `AttendanceProductSyncService`

Key fields on `BagType`:

- `is_product_linked`
- `source_product_id`
- `source_product_name_snapshot`
- `is_excluded_from_attendance`
- `is_legacy`

### 2. Sync triggers

Current triggers:

- Attendance price settings reload runs `sync_products_to_cut_work()`.
- Entering large `Chấm công` tab runs sync and incomplete warning.
- Product changes are picked up at next sync/settings/attendance tab entry.

Do not sync on every search keystroke.

### 3. Product create

Active product creates linked `BagType`:

- `name = Product.product_name`
- `quota_quantity = 0`
- `excess_unit_price = 0`
- `is_active = True`
- `is_product_linked = True`
- `source_product_id = Product.id`
- `source_product_name_snapshot = Product.product_name`
- `is_excluded_from_attendance = False`
- `is_legacy = False`

### 4. Product rename

Product rename updates:

- `BagType.name`
- `BagType.source_product_name_snapshot`

It preserves:

- `quota_quantity`
- `excess_unit_price`
- `is_excluded_from_attendance`
- historical logs.

### 5. Product inactive/delete/reactivate

Inactive/missing product:

- Linked `BagType` is deactivated.
- If has history, `is_legacy=True`.
- No hard-delete of attendance history.

Reactivated product:

- Same `Product.id` remains valid.
- Next product sync can reactivate/update linked CUT work if no conflict.

### 6. Old manual `BagType`

Manual/default old rows:

- `is_product_linked=False`.
- If history exists: set legacy/inactive.
- If no history: deactivate, no hard-delete in sync batch.
- Reports/history still readable.

### 7. Duplicate product name conflict policy

Because `BagType.name` is unique and product names may duplicate:

- Do not append suffix silently.
- Do not merge products by name.
- Duplicate active product names generate warnings.
- Name conflict with manual `BagType.name` generates warning.
- Non-conflicting rows still sync.

### 8. Incomplete config popup

Title:

- `Thiếu cấu hình việc cắt`

Buttons:

- `Đi tới cài đặt`
- `Để sau`

Behavior:

- Shows when entering large `Chấm công` tab if incomplete linked rows exist.
- Does not repeat while user remains in same Attendance tab.
- Can show again after leaving/re-entering if unresolved.
- `Đi tới cài đặt` opens Settings -> Attendance price settings and focuses/highlights first incomplete row if feasible.

### 9. Day-entry filtering

New selection list includes only:

```text
is_active == true
AND is_product_linked == true
AND is_excluded_from_attendance == false
AND is_legacy == false
AND quota_quantity > 0
AND excess_unit_price > 0
```

Historical reload behavior:

- Existing saved records still include their old `bag_type_id` rows for display/edit, even if inactive/legacy/excluded/incomplete now.
- Repository supports include selected ids for historical compatibility.

### 10. Save-time validation

`AttendanceDayEntryService.save_attendance(...)` rejects newly added invalid CUT/VK rows:

- inactive
- not product-linked
- excluded
- legacy
- quota or price zero

Historical existing rows already in original record can be saved again for compatibility, but adding a different invalid old item is rejected.

### 11. Tests and docs

Docs:

- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_INVESTIGATION.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH1.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH2.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH3.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH4.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH5.md`

Tests:

- `tests/test_attendance_product_sync.py`
- `tests/test_attendance_settings_ui.py`
- `tests/test_app_window_attendance_sync.py`
- `tests/test_attendance_day_entry.py`

## K. Attendance CUT/VK → Inventory feature

### 1. Requirement

When attendance record is finalized/DONE:

- CUT employee `CutLog.quantity` increases linked product stock.
- BLOW extra CUT/VK `ExtraCutWorkLog.quantity` also increases linked product stock.
- DRAFT does not update stock.
- Old historical records are not automatically backfilled.
- Admin can edit/finalize multiple times without double-counting.

### 2. `inventory_stock_effects`

File/model:

- `modules/inventory/models.py`
- `InventoryStockEffect`
- table `inventory_stock_effects`

Important fields:

- `source_type = ATTENDANCE_DAILY_RECORD`
- `source_id = DailyRecord.id`
- `source_line_type = CUT_LOG` or `EXTRA_CUT_WORK_LOG`
- `source_line_id = CutLog.id` or `ExtraCutWorkLog.id`
- `attendance_employee_id`
- `attendance_work_date`
- `attendance_bag_type_id`
- `product_id`
- `quantity_delta`
- `unit_type`
- `movement_datetime`
- `note`

Indexes/constraints:

- `(source_type, source_id)` index.
- `product_id` index.
- Unique `(source_type, source_id, source_line_type, source_line_id)`.

`source_line_id` hardening:

- Service rejects `None`.
- Duplicate source lines in a snapshot are rejected.
- Unsupported `source_line_type` is rejected.

### 3. `AttendanceInventoryEffectService`

File:

- `modules/attendance/inventory_effect_service.py`

Class:

- `AttendanceInventoryEffectService`

DTOs:

- `AttendanceInventoryEffectSnapshot`
- `AttendanceInventoryEffectLine`
- result/delta dataclasses.

Main method:

- `reconcile_daily_record_effects(snapshot)`

Behavior:

1. Validate snapshot and lines before mutation.
2. Load old effects by:

```text
source_type = ATTENDANCE_DAILY_RECORD
source_id = snapshot.daily_record_id
```

3. Roll back old effects by applying inverse deltas to `InventoryBalance`.
4. Delete old effect rows.
5. If snapshot status is not DONE or `is_absent=True`, commit rollback only.
6. If DONE/non-absent, apply current CUT/VK quantities and insert new effect rows.

Unit mapping:

- `Product.unit_mode == BAO_KG` -> `UnitType.BAO`.
- `Product.unit_mode == BICH` -> `UnitType.BICH`.
- Do not apply KG conversion for attendance.

Decimal support:

- Uses `Decimal`/Numeric-compatible values.
- Do not use float.

Validation:

- Missing `product_id`: error.
- Missing main `Product`: error.
- Unsupported unit mode: error.
- Missing `source_line_id`: error.
- Unsupported `source_line_type`: error.

### 4. Integration into `AttendanceDayEntryService.save_attendance`

File:

- `modules/attendance/service.py`

Class/method:

- `AttendanceDayEntryService.save_attendance(payload, *, finalize)`

Call order:

1. Open attendance session/transaction.
2. Load/create `DailyRecord`.
3. Capture existing/historical bag ids for validation compatibility.
4. Clear/rebuild `work_logs`, `cut_logs`, `extra_cut_work_logs`.
5. Set final record status:
   - DONE if `finalize=True`.
   - DRAFT if `finalize=False`.
6. Flush attendance session.
7. Build `AttendanceInventoryEffectSnapshot` from flushed objects.
8. Call `AttendanceInventoryEffectService.reconcile_daily_record_effects(snapshot)`.
9. Return `AttendanceSaveResult` only if reconciliation succeeds.

Snapshot fields:

- `daily_record_id = record.id`
- `employee_id = record.employee_id`
- `work_date = record.date`
- `status = record.status`
- `is_absent = record.is_absent`
- CUT lines from current `CutLog`.
- VK lines from current `ExtraCutWorkLog`.
- `product_id = log.bag_type.source_product_id`.

Error propagation:

- Inventory reconciliation errors are not swallowed.
- UI should not show save success if inventory update failed.

Cross-DB caveat:

- attendance DB and main DB are separate.
- Full atomicity across both DB files is not guaranteed.
- Diagnostics/reconcile service mitigates but does not remove theoretical partial-commit risk.

### 5. `AttendanceInventoryDiagnosticService`

File:

- `modules/attendance/inventory_diagnostic_service.py`

Class:

- `AttendanceInventoryDiagnosticService`

Methods:

- `list_issues()`
- `build_snapshot_for_daily_record(daily_record_id)`
- `reconcile_daily_record(daily_record_id)`

Issue types:

- `MISSING_EFFECTS_FOR_DONE_RECORD`
- `STALE_EFFECTS_FOR_DRAFT_OR_ABSENT_RECORD`
- `STALE_EFFECTS_FOR_MISSING_DAILY_RECORD`
- `QUANTITY_MISMATCH`
- `PRODUCT_MISMATCH`
- `MISSING_PRODUCT_LINK`
- `MISSING_MAIN_PRODUCT`

Behavior:

- `list_issues()` is read-only.
- Detects DONE records with missing effects.
- Detects stale effects for DRAFT/absent/missing records.
- Detects aggregate quantity/product mismatch.
- `reconcile_daily_record()` explicitly rebuilds snapshot and calls effect service.
- Does not auto-backfill.
- Does not auto-run on startup.

### 6. Admin diagnostics UI

File:

- `modules/settings/ui/page.py`

Panel:

- `AttendanceInventoryDiagnosticsPanel`

UI supports:

- Scan issues.
- Show Vietnamese labels for issue types.
- Reconcile selected `daily_record_id` explicitly.
- Refresh after reconcile.
- Missing-source effects are not auto-cleaned.

### 7. Reports/tests

Docs:

- `docs/ATTENDANCE_CUT_TO_INVENTORY_INVESTIGATION.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH1.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_PREFLIGHT.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH2.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH3.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH4.md`

Tests:

- `tests/test_attendance_inventory_effect_service.py`
- `tests/test_attendance_inventory_integration.py`
- `tests/test_attendance_inventory_diagnostics.py`
- `tests/test_attendance_inventory_diagnostics_ui.py`

## L. Settings / Backup / Diagnostics / Update

### 1. Settings page

Key file:

- `modules/settings/ui/page.py`

Settings includes:

- General settings.
- UI scale/size settings.
- Update check.
- Backup button.
- Diagnostics export.
- Attendance price settings.
- Attendance inventory diagnostics panel.

### 2. Backup

Backup service:

- likely under `modules/settings` or `core` backup services.

Behavior:

- Creates zip in backup folder.
- Includes main DB `app.db` if present.
- Includes attendance DB `attendance.db` if present.
- Includes manifest metadata.

Important:

- Product-attendance and attendance-inventory features depend on both DBs.
- Backup/restore should treat `app.db` and `attendance.db` as a pair.
- Restoring only one DB can break external links or diagnostics.

### 3. Diagnostics

Diagnostics service exports:

- app info.
- UI environment.
- recent logs.

It generally does not include DBs, to avoid leaking data and large files. Attendance inventory diagnostic service is separate: it scans DB consistency and can reconcile selected records.

### 4. Auto-update

Files:

- `core/version.py`
- `version.json`
- update-related code in `core`/settings.

Manifest fields:

- `version`
- `installer_url`
- `notes`
- `min_required_version`

Important release rule:

- `installer_url` must be a direct `.exe` URL.
- `version.json` does not magically update itself.
- After release, manually verify raw GitHub URL points to current repo and current installer.

Release flow:

1. Update `core/version.py`.
2. Update `version.json`.
3. Build/test locally if possible.
4. Push/tag release.
5. GitHub Actions builds installer.
6. Verify Release asset URL.
7. Verify `version.json` installer URL.

Common failure:

- Raw URL still points to old repo/link/version.

### 5. Background image feature

There is a root `.jpg` file in repo, but no clearly confirmed production background-image feature was detected in the current code inspection. If future task involves background image:

- Verify actual implementation first.
- App should run if optional image missing.
- Do not add required image dependency to PyInstaller without fallback.

## M. UI changes and current UX state

### 1. Main tab order

Current effective order places `Lịch sử` before `Chấm công` and `Cài đặt`.

### 2. Attendance report table

Current attendance report UI has:

- 10-day / 30-day tabs.
- Flexible width behavior.
- Spacer between employee sections.
- Total row.
- Decimal CUT/VK display support.

### 3. Numeric input style

Recent UI direction:

- Avoid spin button style where it causes row height/UX issues.
- Use compact line edits similar to sales table.
- CUT/VK quantity supports decimal.

### 4. Search/add row behavior for CUT/VK

Day-entry search/add:

- Uses filtered product-linked `BagType` list.
- Excluded/incomplete/legacy/manual rows hidden for new selection.
- Existing historical rows still reload if already saved.

### 5. Multi-delete

Investigation:

- `docs/MULTI_DELETE_UI_INVESTIGATION.md`

Implemented:

- Shared helper `shared/widgets/table_selection_mode.py`.
- Attendance employees multi-delete.
- Inventory products multi-delete.

Deferred:

- `Lịch sử` multi-delete, because invoices/returns/payments have rollback effects on stock and customer debt.

### 6. Known UI caveats

- Admin inventory diagnostics UI is intentionally small/manual, not automatic.
- Some modules still use per-feature dialogs/message boxes; avoid modal dialogs in CI tests unless patched.
- For UI tests, run with `QT_QPA_PLATFORM=offscreen`.

## N. Testing and CI/CD status

### 1. Test framework

- Test framework: `unittest`.
- Qt tests run offscreen.
- CI uses Windows runner.

### 2. Important commands

Canonical test discovery:

```powershell
python -m unittest discover -s tests -p "test*.py" -t .
```

Compile check:

```powershell
python -m compileall core modules tests shell
```

### Suggested focused test commands by area

Attendance product sync:

```powershell
python -m unittest tests.test_attendance_product_sync tests.test_attendance_settings_ui tests.test_app_window_attendance_sync
```

Attendance day-entry/inventory:

```powershell
python -m unittest tests.test_attendance_day_entry tests.test_attendance_inventory_effect_service tests.test_attendance_inventory_integration tests.test_attendance_inventory_diagnostics
```

Attendance inventory diagnostics UI:

```powershell
python -m unittest tests.test_attendance_inventory_diagnostics_ui tests.test_attendance_inventory_diagnostics
```

Attendance employee management and multi-delete:

```powershell
python -m unittest tests.test_attendance_employee_management
```

Inventory/product:

```powershell
python -m unittest tests.test_inventory_service tests.test_inventory_transactions tests.test_product_search_ui
```

Sales/returns/customer:

```powershell
python -m unittest tests.test_sales_service tests.test_return_service tests.test_customer_service
```

Smoke/CI:

```powershell
python -m unittest tests.test_smoke
python -m unittest discover -s tests -p "test*.py" -t .
python -m compileall core modules tests shell
```

Các test files trong danh sách trên đang tồn tại ở thời điểm cập nhật tài liệu. Nếu một nhánh tương lai đổi tên test file, dùng command tương đương theo module hiện có.

### 3. Current test count

Latest known full discovery from recent work:

```text
Ran 489 tests OK
```

Treat this as a recent local baseline, not a permanent guarantee.

### 4. GitHub Actions CI/CD

Files:

- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`

Current CI checks:

- Sets `QT_QPA_PLATFORM=offscreen`.
- Sets `LOCALAPPDATA` to runner temp path.
- Runs from repo root.
- Runs:

```powershell
python -m unittest discover -s tests -p "test*.py" -t .
python -m compileall core modules tests shell
```

Release workflow:

- Checks version/tag.
- Installs requirements.
- Runs unittest discovery.
- Runs compileall.
- Builds PyInstaller app.
- Builds Inno installer.
- Uploads installer/checksum to GitHub Release.

### 5. Previous CI issues fixed

Docs:

- `docs/CI_DB_INIT_UI_RELOAD_FIX.md`
- `docs/CI_NO_SUCH_TABLE_INVOICES_INVESTIGATION.md`
- `docs/CI_TEST_RUNTIME_STABILITY_SECOND_PASS.md`

Fixed/handled issues:

- `ImportError: Start directory is not importable: 'tests'`:
  - ensured importable `tests` package and discovery command with `-s tests -p "test*.py" -t .`.
- UI smoke DB init:
  - schema must exist before constructing DB-backed pages like `TransactionHistoryView`.
- Temp dirs under `tests/_tmp` / `tests/_diagnostics_tmp`:
  - tests should use system temp and close DB engines/log handlers.
- Offscreen Qt modal hangs:
  - tests patch/avoid message boxes where needed.

### 6. Test helpers

Important patterns:

- Use temp runtime outside repo.
- Set `LOCALAPPDATA` or supported env before loading settings.
- Clear `core.config.get_settings` cache.
- Reset `core.db` engine cache.
- Reset `modules.attendance.db` engine cache if attendance DB involved.
- Call `core.db.init_db()`.
- Call `modules.attendance.db.init_attendance_db()` if attendance UI/DB involved.
- Close/delete Qt widgets after tests.

### 7. Guidance

For future changes:

- Run focused tests first.
- Then run full discovery and compileall.
- Do not create temp runtime directories under tracked `tests/`.
- Do not skip/delete tests to pass CI.

## O. Important decisions / design rationale

1. Keep two DBs for now; do not merge immediately.
   - Main DB and attendance DB remain separate to reduce migration risk.
   - Cross-DB features use explicit source references and diagnostics.

2. Do not auto-backfill old attendance records.
   - Old DONE records may lack inventory effects.
   - Diagnostics can list them.
   - Backfill must be explicit/manual in a future feature.

3. Product-linked `BagType.name` comes from `Product.product_name`.
   - Attendance settings cannot freely rename product-linked CUT work.

4. Manual CUT add removed.
   - CUT work source is inventory products.
   - Attendance settings only configures quota/price/exclusion.

5. Use `inventory_stock_effects` instead of blind stock increments.
   - Enables rollback/apply/idempotence.
   - Gives diagnostics source references.

6. Use rollback/apply reconciliation.
   - Re-saving same DONE record must not double count.
   - Editing DONE must reflect latest quantities only.

7. Defer `Lịch sử` multi-delete.
   - Sales/returns/customer debt delete effects are high risk.
   - Needs separate design and tests.

8. Product recreate same code/name should reactivate inactive product.
   - Prevents `UNIQUE constraint failed: products.product_code_base`.
   - Preserves history and attendance links.

9. Backup/restore must treat both DBs together.
   - Product-attendance links and inventory effects cross DB boundary.

10. Release `version.json` must be manually checked.
    - Update manifest URL and version before/after release.

## P. Current open tasks / next steps

### 1. Product reactivation on recreate same code/name

Status: implemented.

Docs:

- `docs/PRODUCT_REACTIVATE_ON_RECREATE.md`

Behavior:

- Same inactive code/name reactivates existing product.
- Same code/different name raises friendly validation.
- Same code/name/different unit with history raises friendly validation.

### 2. Attendance price settings UI

Status: implemented.

Docs:

- `docs/ATTENDANCE_PRICE_SETTINGS_UI_BATCH1.md`

Implemented:

- Dropdown between `Công việc tổ thổi` and `Loại bao tổ cắt`.
- CUT add button removed.
- Product-linked CUT names read-only.
- Quota/excess/exclusion editable.
- Red incomplete highlight preserved.

### 3. Multi-delete

Status:

- Employees: implemented.
- Products: implemented.
- History: deferred.

Docs:

- `docs/MULTI_DELETE_UI_INVESTIGATION.md`
- `docs/MULTI_DELETE_EMPLOYEE_BATCH1.md`
- `docs/MULTI_DELETE_PRODUCT_BATCH2.md`

Next if needed:

- Do not implement history multi-delete without dedicated rollback/debt/inventory design.

### 4. Admin UI for Attendance inventory diagnostics

Status: implemented as small Settings panel.

Current behavior:

- Scan issues.
- View issue list.
- Reconcile selected daily record explicitly.
- No auto-backfill.
- No startup auto-reconcile.

### 5. Optional manual backfill tool

Status: pending/future.

Recommended future design:

- List old DONE records without effects.
- Preview product deltas.
- Require explicit confirmation.
- Reconcile selected records or selected date range.
- Produce audit report.

### 6. Possible future DB unification

Status: not recommended now.

If ever needed:

- Treat as dedicated architecture migration.
- Need backup/restore plan, migration scripts, rollback plan, and full test suite.
- Do not combine with feature work.

### 7. Web/online attendance idea

Status: not implemented.

Likely future approach:

- Separate backend/web or API for employee QR/mobile attendance.
- Desktop remains admin/master app for now.
- Needs separate auth, sync, deployment, offline/online design.

### 8. Known bugs/caveats

- Cross-DB partial commit risk remains theoretical but mitigated by diagnostics/reconcile.
- Existing local DBs created before preflight may have DB column nullable for `source_line_id`; service prevents inserting `NULL`.
- Raw DB errors should not be surfaced to user; use validation errors/message boxes.
- `version.json` update/release flow remains manual-risk.
- Background image feature was not clearly confirmed in current code inspection.

## Q. How to continue in a new ChatGPT session

### 1. Files to provide/read first

Ask user or inspect:

- `docs/PROJECT_HANDOFF_SUMMARY.md` first.
- Latest relevant `docs/*.md` report for the feature being continued.
- Latest Codex output report from the previous batch.
- Screenshots/logs if UI or CI issue.
- Exact failing command output if tests fail.

For attendance product sync:

- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_*.md`

For attendance inventory effects:

- `docs/ATTENDANCE_CUT_TO_INVENTORY_*.md`

For multi-delete:

- `docs/MULTI_DELETE_*.md`

For CI:

- `docs/CI_*.md`

### 2. What not to assume

Do not assume:

- DB merge has happened.
- Old attendance records are backfilled.
- `Lịch sử` multi-delete is safe.
- `version.json` updates automatically.
- Attendance diagnostics auto-reconcile runs.
- Product names are globally unique.
- CUT manual BagTypes should be recreated.
- UI tests can show modal dialogs in CI.

### 3. How to propose future Codex prompts

Prefer small batches:

- Investigation/design first for risky changes.
- Implementation batch with clear scope.
- Tests and compileall required.
- Markdown report output required for major changes.

Good prompt structure:

- Goal.
- In scope.
- Out of scope.
- Exact files likely involved.
- Required tests.
- Required docs/report.
- Commands to run.

### 4. Commands before release

Recommended:

```powershell
python -m unittest discover -s tests -p "test*.py" -t .
python -m compileall core modules tests shell
```

Also verify:

- `core/version.py`
- `version.json`
- `.github/workflows/release.yml`
- `installer/QuanLyHangHoa.iss`
- `desktop_app.spec`
- release asset URL after GitHub Release.

### 5. Critical safety rules

Do not:

- Change attendance formulas casually.
- Bulk mutate inventory without source reference/effect rows.
- Auto-backfill old attendance records.
- Merge DBs as part of normal feature work.
- Skip/delete tests.
- Hide DB errors using broad `try/except` without diagnostics.
- Use float for quantities/money.
- Hard-delete historical products/employees/BagTypes.
- Add direct SQL bulk delete for product/employee/history multi-delete.

## R. Appendix: documents and test files index

### 1. Important docs present

Attendance product-to-CUT sync:

- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_INVESTIGATION.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH1.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH2.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH3.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH4.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH5.md`

Attendance CUT/VK to inventory:

- `docs/ATTENDANCE_CUT_TO_INVENTORY_INVESTIGATION.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH1.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_PREFLIGHT.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH2.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH3.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH4.md`

Attendance price settings:

- `docs/ATTENDANCE_PRICE_SETTINGS_UI_BATCH1.md`

Multi-delete:

- `docs/MULTI_DELETE_UI_INVESTIGATION.md`
- `docs/MULTI_DELETE_EMPLOYEE_BATCH1.md`
- `docs/MULTI_DELETE_PRODUCT_BATCH2.md`

CI/runtime stability:

- `docs/CI_DB_INIT_UI_RELOAD_FIX.md`
- `docs/CI_NO_SUCH_TABLE_INVOICES_INVESTIGATION.md`
- `docs/CI_TEST_RUNTIME_STABILITY_SECOND_PASS.md`

Product recreation/reactivation:

- `docs/PRODUCT_REACTIVATE_ON_RECREATE.md`

This handoff:

- `docs/PROJECT_HANDOFF_SUMMARY.md`

### 2. Important test files

Inventory/product:

- `tests/test_inventory_service.py`
- `tests/test_product_search_ui.py`
- `tests/test_inventory_transactions.py`
- `tests/test_schema_invariants.py`

Sales/returns/customer/orders:

- `tests/test_order_service.py`
- `tests/test_order_ui.py`
- `tests/test_sales_pos_layout.py`
- `tests/test_customer_list_search.py`
- `tests/test_customer_ui.py`
- `tests/test_customer_invoice_payment_migration.py`

Attendance product sync/settings/day-entry:

- `tests/test_attendance_product_sync.py`
- `tests/test_attendance_settings_ui.py`
- `tests/test_app_window_attendance_sync.py`
- `tests/test_attendance_day_entry.py`
- `tests/test_attendance_employee_management.py`
- `tests/test_attendance_batch1.py`

Attendance inventory effects:

- `tests/test_attendance_inventory_effect_service.py`
- `tests/test_attendance_inventory_integration.py`
- `tests/test_attendance_inventory_diagnostics.py`
- `tests/test_attendance_inventory_diagnostics_ui.py`

CI/smoke/runtime:

- `tests/test_smoke.py`
- app-window/history/settings related tests if present.

### 3. Important code files by area

Shell/bootstrap:

- `main.py`
- `shell/bootstrap.py`
- `shell/app_window.py`

Core:

- `core/config.py`
- `core/paths.py`
- `core/db.py`
- `core/version.py`

Inventory:

- `modules/inventory/models.py`
- `modules/inventory/repository.py`
- `modules/inventory/service.py`
- `modules/inventory/controller.py`
- `modules/inventory/ui/product_list_view.py`

Sales/history:

- `modules/sales/models.py`
- `modules/sales/repository.py`
- `modules/sales/service.py`
- `modules/sales/controller.py`
- `modules/sales/ui/transaction_history_view.py`

Returns/customer/orders:

- `modules/returns/models.py`
- `modules/customer/models.py`
- `modules/orders/models.py`

Attendance:

- `modules/attendance/models.py`
- `modules/attendance/db.py`
- `modules/attendance/repository.py`
- `modules/attendance/service.py`
- `modules/attendance/blow_work.py`
- `modules/attendance/cut_bonus.py`
- `modules/attendance/product_sync_service.py`
- `modules/attendance/inventory_effect_service.py`
- `modules/attendance/inventory_diagnostic_service.py`
- `modules/attendance/ui/employee_tab.py`
- `modules/attendance/ui/day_entry_tab.py`
- `modules/attendance/ui/report_tab.py`
- `modules/attendance/ui/settings_tab.py`

Settings/diagnostics:

- `modules/settings/ui/page.py`

Shared:

- `shared/widgets/message_box.py`
- `shared/widgets/table_selection_mode.py`

Build/release:

- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `scripts/build_exe.ps1`
- `scripts/build_installer.ps1`
- `scripts/check_version.ps1`
- `desktop_app.spec`
- `installer/QuanLyHangHoa.iss`
- `version.json`

## S. Latest manual verification and release state

### 1. Current detected version

Trạng thái detect từ repo tại lần cập nhật tài liệu này:

- `core/version.py`: `APP_VERSION = "0.8.1"`.
- `version.json`: `"version": "0.8.1"`.
- Hai giá trị này đang khớp nhau.

Nếu user đang chạy một bản đã cài ngoài máy, exact deployed user version không thể detect chắc chắn chỉ từ repo. Cần kiểm tra trực tiếp trong app đã cài hoặc installer/release đang dùng.

### 2. Current update manifest

`version.json` hiện có:

- `version`: `0.8.1`
- `installer_url`: `https://github.com/antongduy2307/QuanLyHangHoa/releases/download/v0.8.1/QuanLyHangHoa-Setup-v0.8.1.exe`
- Repo trong URL: `antongduy2307/QuanLyHangHoa`
- `min_required_version`: `0.8.0`

Ghi nhớ khi release:

- `installer_url` phải là link trực tiếp tới file `.exe`.
- Không dùng link trang release HTML nếu update checker/download logic cần direct installer.
- `version.json` không tự update sau khi GitHub Release build xong; phải kiểm tra thủ công.

### 3. Release state

- `.github/workflows/release.yml` tồn tại và có release workflow build PyInstaller/Inno installer.
- `.github/workflows/ci.yml` tồn tại và chạy unittest discovery + compileall.
- Latest known local test baseline trong tài liệu trước: `Ran 489 tests OK`.
- CI/CD có vẻ được cấu hình đúng theo repo, nhưng tài liệu này không thể xác nhận trạng thái GitHub Actions live tại thời điểm đọc nếu không mở GitHub.
- Exact deployed user version không detect được từ repo.

### 4. Manual verification checklist

| Area | Manual test | Expected result | Status |
| --- | --- | --- | --- |
| Product recreate/reactivation | Create product, create history, delete/deactivate product, recreate same code + same name | Old product is reactivated, same `Product.id`, no raw `IntegrityError` | Implemented; manual verification should be confirmed |
| Attendance price settings | Open price settings, switch dropdown between `Công việc tổ thổi` and `Loại bao tổ cắt` | Only one table visible at a time; CUT add button absent | Implemented; manual verification should be confirmed |
| CUT attendance to inventory | Product stock starts at 0, save CUT quantity as DRAFT, then finalize DONE | DRAFT leaves stock unchanged; DONE increases stock by quantity | Manually tested OK |
| Edit finalized CUT | Change finalized quantity from 10.5 to 7 | Stock becomes 7, not 17.5 | Manually tested OK |
| DONE to DRAFT / absent | Convert finalized record to draft or absent | Stock effect rolls back | Manually tested OK |
| BLOW VK to inventory | Add extra CUT/VK quantity for BLOW employee and finalize | Linked product stock increases by VK quantity | Manually tested OK |
| Attendance inventory diagnostics | Open diagnostics panel, scan issues, reconcile selected record explicitly if needed | Issues listed or no-issue message shown; reconcile only on explicit action | Implemented; manual verification should be confirmed |
| Employee multi-delete | Enter selection mode, select multiple employees, delete | Hard-delete/deactivate summary appears | Implemented; manual verification should be confirmed |
| Product multi-delete | Enter selection mode, select multiple products, delete | Hard-delete/deactivate summary appears | Implemented; manual verification should be confirmed |
| Update flow | Open update check | App reads current `version.json` and downloads direct installer URL | Unknown / needs manual verification |

## T. Danger zones / Không sửa nếu chưa xác nhận

- Attendance formulas:
  - BLOW `Thừa máy` quota `-3` chỉ áp dụng cho `Thừa máy`, không áp dụng cho toàn bộ numeric work.
  - VK formula là `quantity * excess_unit_price_snapshot`.
  - CUT multi-code quota/bonus logic rất nhạy; không đổi nếu chưa có xác nhận user/client và test cụ thể.
- Inventory effects:
  - Không update tồn kho từ attendance bằng direct blind increment.
  - Phải dùng `inventory_stock_effects` source reference.
  - Phải rollback/apply theo `source_type + source_id`.
  - Không dùng float cho quantity/money.
- Old attendance records:
  - Không auto-backfill old DONE records.
  - Backfill nếu có phải manual, preview-based, và được xác nhận.
- Database architecture:
  - Không merge `app.db` và `attendance.db` trong một feature bình thường.
  - DB unification là migration project riêng.
- History multi-delete:
  - Không implement bulk delete cho `Lịch sử` một cách casual.
  - Invoice/return/debt payment deletion ảnh hưởng stock và customer debt.
- Product deletion:
  - Không hard-delete products with history.
  - Recreate same inactive code/name phải reactivate existing product.
- Backup/restore:
  - Treat `app.db` và `attendance.db` as a pair.
  - Restore chỉ một DB có thể tạo mismatch.
- CI/tests:
  - Không skip/delete tests để pass CI.
  - Không dùng broad `try/except` để che DB initialization errors.
  - Không để tests tạo temp dirs dưới repo.
- Release/update:
  - `version.json` không update tự động.
  - `installer_url` phải check thủ công.
  - Old installed apps có thể vẫn đọc old repo manifest nếu chưa migrate/update manifest config.

## U. Latest implemented vs pending status matrix

| Feature / Area | Status | Main files | Main docs | Notes / Caveats |
| --- | --- | --- | --- | --- |
| Product reactivation on recreate same code/name | Implemented | `modules/inventory/service.py`, `modules/inventory/repository.py` | `docs/PRODUCT_REACTIVATE_ON_RECREATE.md` | Same inactive code/name reactivates; same code/different name or unsafe unit change raises validation. |
| Attendance price settings dropdown + remove CUT add | Implemented; needs manual verification | `modules/attendance/ui/settings_tab.py` | `docs/ATTENDANCE_PRICE_SETTINGS_UI_BATCH1.md` | CUT rows still editable for quota/price/exclusion; CUT add button absent. |
| Product-to-attendance CUT sync | Implemented | `modules/attendance/product_sync_service.py`, `modules/attendance/db.py`, `modules/attendance/models.py` | `docs/ATTENDANCE_PRODUCT_CUT_SYNC_*.md` | Keeps two DBs; syncs only product id/name/active state. |
| Attendance CUT/VK to inventory effect | Implemented | `modules/attendance/service.py`, `modules/attendance/inventory_effect_service.py`, `modules/inventory/models.py` | `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH1.md`, `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH2.md`, `docs/ATTENDANCE_CUT_TO_INVENTORY_PREFLIGHT.md` | Manual logic testing was confirmed for DRAFT/DONE/edit/rollback cases. |
| Attendance inventory diagnostics service | Implemented | `modules/attendance/inventory_diagnostic_service.py` | `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH3.md` | Scan is read-only; reconcile is explicit. |
| Attendance inventory diagnostics UI | Implemented; needs manual verification | `modules/settings/ui/page.py` | `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH4.md` | Admin maintenance surface, no auto-backfill. |
| Employee multi-delete | Implemented; needs manual verification | `modules/attendance/ui/employee_tab.py`, `shared/widgets/table_selection_mode.py` | `docs/MULTI_DELETE_EMPLOYEE_BATCH1.md` | Uses existing delete/deactivate service per selected employee. |
| Product multi-delete | Implemented; needs manual verification | `modules/inventory/ui/product_list_view.py`, `shared/widgets/table_selection_mode.py` | `docs/MULTI_DELETE_PRODUCT_BATCH2.md` | Uses existing delete mode/delete service per product. |
| History multi-delete | Deferred | `modules/sales/ui/transaction_history_view.py` and related sales/returns/customer services | `docs/MULTI_DELETE_UI_INVESTIGATION.md` | High risk due stock/debt rollback; do not implement without separate plan. |
| Manual backfill for old DONE attendance | Pending | likely `modules/attendance/inventory_diagnostic_service.py` plus UI/service batch | `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH3.md`, `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH4.md` | Must be preview-based and manually confirmed. |
| DB unification | Deferred | `core/db.py`, `modules/attendance/db.py`, all models/services | `docs/ATTENDANCE_PRODUCT_CUT_SYNC_INVESTIGATION.md`, `docs/ATTENDANCE_CUT_TO_INVENTORY_INVESTIGATION.md` | Future dedicated migration project only. |
| Web/online QR attendance idea | Future idea | none confirmed | none confirmed | Not implemented; needs backend/auth/sync design. |
| Background image feature | Unknown / inspect code | unknown; root contains image asset but no confirmed feature path | none confirmed | Inspect code before claiming implemented. |
| Auto-update / `version.json` flow | Implemented; needs manual verification | `core/version.py`, `version.json`, update/settings code, `.github/workflows/release.yml` | release/update notes in this handoff | Must manually verify direct installer URL and old app manifest behavior. |

## V. Future assistant startup checklist

1. Read `docs/PROJECT_HANDOFF_SUMMARY.md`.
2. Ask user what the latest branch/version is.
3. Ask whether latest changes have been pushed/released.
4. Ask for latest Codex report if continuing a recent batch.
5. Ask for screenshot/log if UI or CI issue.
6. Before proposing code:
   - identify affected module;
   - classify task as business logic, UI only, DB migration, release issue, CI/test issue, or documentation;
   - decide whether an investigation `.md` report is needed first.
7. For risky tasks, require:
   - report in `docs/`;
   - focused tests;
   - full unittest discovery;
   - compileall.
8. For release tasks, verify:
   - `core/version.py`;
   - `version.json`;
   - GitHub Release asset URL;
   - direct installer URL.
9. For attendance/inventory tasks, re-check:
   - two-DB boundary;
   - `inventory_stock_effects` source semantics;
   - DRAFT/DONE/absent rollback behavior;
   - old-record backfill policy.
10. For UI tasks, confirm:
   - existing widgets/signals;
   - offscreen test strategy;
   - no modal hang in CI.
