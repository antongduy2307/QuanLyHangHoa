# PROJECT HANDOFF SUMMARY - QuanLyHangHoa

Tài liệu này là bản bàn giao trạng thái dự án để tiếp tục phát triển trong một phiên ChatGPT/Codex mới. Nội dung viết bằng tiếng Việt, nhưng giữ nguyên code identifiers, file paths, class names, function names, table names và command lines.

## A. Tổng Quan Dự Án

### 1. Tên và mục đích

Ứng dụng: `QuanLyHangHoa`.

Mục đích: ứng dụng desktop nội bộ để quản lý hàng hóa, tồn kho, bán hàng, trả hàng, khách hàng/công nợ, đơn đặt hàng, báo cáo, lịch sử giao dịch, chấm công sản xuất, cài đặt, sao lưu, chẩn đoán và cập nhật ứng dụng.

### 2. Loại ứng dụng hiện tại

- Python desktop app.
- UI dùng `PyQt6`.
- ORM dùng `SQLAlchemy`.
- Dữ liệu cục bộ bằng SQLite.
- Có hai SQLite DB chính:
  - main app DB: `app.db`.
  - attendance DB: `attendance.db`.
- Đóng gói Windows bằng `PyInstaller` qua `desktop_app.spec`.
- Installer Windows bằng Inno Setup qua `installer/QuanLyHangHoa.iss`.
- CI/CD bằng GitHub Actions:
  - `.github/workflows/ci.yml`
  - `.github/workflows/release.yml`
- Test runner chính: `unittest`.
- Qt tests chạy offscreen qua `QT_QPA_PLATFORM=offscreen`.

### 3. Business domains

- `modules.inventory`: hàng hóa, giá bán, tồn kho, nhập kho, điều chỉnh tồn, xóa/ngừng sử dụng hàng.
- `modules.sales`: bán hàng, hóa đơn, sửa/xóa hóa đơn, tác động tồn kho và công nợ.
- `modules.returns`: trả hàng, quick return, trả theo hóa đơn, tác động tồn kho và công nợ.
- `modules.customer`: khách hàng, công nợ, ledger, debt payments.
- `modules.orders`: đơn đặt hàng, chuyển đơn sang bán hàng, không tự trừ tồn ở bước tạo đơn.
- `modules.reporting`: báo cáo kinh doanh/tồn kho.
- `shell.history_page` và các list/detail views: lịch sử giao dịch, hóa đơn, trả hàng, thanh toán nợ.
- `modules.attendance`: nhân viên, chấm công ngày, báo cáo chấm công, cấu hình giá chấm công, đồng bộ product -> CUT work, CUT/VK -> inventory effects.
- `modules.settings`: cài đặt chung, UI scale, backup, diagnostics, update check, attendance price settings, attendance-inventory diagnostics panel.

### 4. Version hiện tại

Trong `core/version.py`:

```python
APP_VERSION = "0.8.0"
```

Trong `version.json` hiện tại:

```json
{
  "version": "0.8.0",
  "installer_url": "https://github.com/antongduy2307/QuanLyHangHoa/releases/download/v0.8.0/QuanLyHangHoa-Setup-v0.8.0.exe",
  "notes": [
    "Adding sync from Goods to Attendance",
    ":3"
  ],
  "min_required_version": "0.7.0"
}
```

### 5. File/thư mục quan trọng

- `main.py`: entrypoint ứng dụng.
- `core/`: cấu hình, paths, DB init, migrations, enums, logging, version.
- `shell/`: bootstrap app, main window, navigation tabs, history page.
- `modules/`: domain modules.
- `shared/`: widgets dùng chung, theme, UI scale, message box, table helper.
- `tests/`: unittest suite.
- `.github/workflows/`: CI/release workflows.
- `scripts/`: build/check scripts (`build_exe.ps1`, `build_installer.ps1`, `check_version.ps1`).
- `desktop_app.spec`: PyInstaller spec.
- `installer/QuanLyHangHoa.iss`: Inno Setup script.
- `docs/`: các investigation/batch reports đã sinh trong quá trình phát triển.

## B. Kiến Trúc Tổng Quan

### 1. Main shell/window

Files:

- `main.py`
- `shell/bootstrap.py`
- `shell/app_window.py`
- `shell/navigation.py`
- `shell/history_page.py`

`shell/bootstrap.py`:

- `ACTIVE_MODULE_PACKAGES` hiện gồm:
  - `modules.inventory`
  - `modules.sales`
  - `modules.orders`
  - `modules.customer`
  - `modules.reporting`
  - `modules.attendance`
  - `modules.settings`
- `bootstrap_application(app)`:
  - đọc `Settings` từ `core.config.get_settings()`;
  - cấu hình logging;
  - install exception hooks;
  - apply theme;
  - gọi `init_db()` cho main DB trước khi dựng UI;
  - load module specs;
  - tạo `AppWindow`.

`shell/app_window.py`:

- Class: `AppWindow(QMainWindow)`.
- Tạo `NavigationTabs`.
- Chèn `HistoryPage` trước `attendance` và `settings`, nên tab order thực tế là:
  - `Hàng hóa`
  - `Bán hàng`
  - `Đặt hàng`
  - `Khách hàng`
  - `Báo cáo`
  - `Lịch sử`
  - `Chấm công`
  - `Cài đặt`
- Giữ refs:
  - `_history_page`
  - `_attendance_page`
  - `_reporting_page`
  - `_settings_page`
- Signal/event quan trọng:
  - settings `check_updates_requested` -> update service.
  - settings `backup_requested` -> `UserBackupService`.
  - settings `export_diagnostics_requested` -> `DiagnosticsService`.
  - settings `attendance_config_changed` -> refresh attendance page.
  - module pages `transaction_changed`/`order_changed` -> refresh history/reporting/customer/inventory/orders.
- Khi chuyển vào tab lớn `Chấm công`, `_handle_enter_attendance_tab()` chạy `AttendanceProductSyncService.sync_products_to_cut_work()`, log warnings, và nếu có incomplete CUT work thì show popup “Thiếu cấu hình việc cắt”.

### 2. Module pattern

Pattern phổ biến:

- `models.py`: SQLAlchemy models.
- `repository.py`: query/persistence primitives.
- `service.py`: business rules, validation, transaction orchestration.
- `controller.py`: adapter giữa UI và service.
- `ui/`: pages/widgets/dialogs.
- `dto.py`: DTOs cho UI/service.
- `tests/test_*.py`: unittest coverage.

Ví dụ:

- Inventory:
  - `modules/inventory/models.py`
  - `modules/inventory/repository.py`
  - `modules/inventory/service.py`
  - `modules/inventory/controller.py`
  - `modules/inventory/ui/product_list_view.py`
- Attendance:
  - `modules/attendance/models.py`
  - `modules/attendance/repository.py`
  - `modules/attendance/service.py`
  - `modules/attendance/settings_service.py`
  - `modules/attendance/product_sync_service.py`
  - `modules/attendance/inventory_effect_service.py`
  - `modules/attendance/inventory_diagnostic_service.py`
  - `modules/attendance/ui/*`

### 3. Database/session pattern

Main DB:

- File path logic: `core/config.py`, `core/paths.py`.
- Default DB path: `get_settings().db_path`, thường là `%LOCALAPPDATA%/QuanLyHangHoa/app.db`.
- SQLAlchemy base/session:
  - `core.db.Base`
  - `core.db.ENGINE`
  - `core.db.SessionFactory`
- Init:
  - `core.db.init_db()`
  - imports models from customer/inventory/orders/returns/sales.
  - `Base.metadata.create_all(bind=ENGINE)`.
  - idempotent migrations:
    - customer address/note/is_active columns;
    - customer ledger ordering columns;
    - `migrate_customer_invoice_payments_to_debt_payment_v1(...)`.
- Test reset helper:
  - `core.db.reset_engine_cache()`.

Attendance DB:

- Path: `modules.attendance.db.get_attendance_db_path()` -> `get_settings().app_data_dir / "attendance.db"`.
- SQLAlchemy base/session:
  - `AttendanceBase`
  - `AttendanceSessionLocal`
  - `get_attendance_engine()`.
- Init:
  - `init_attendance_db()`;
  - `AttendanceBase.metadata.create_all(bind=engine)`;
  - `_upgrade_attendance_schema(engine)`;
  - `seed_attendance_defaults(session)`.
- Test reset helper:
  - `reset_attendance_engine_cache()`.

Rủi ro quan trọng:

- `core.config.get_settings()` dùng `lru_cache`, nên tests cần `cache_clear()` sau khi đổi env vars.
- Main DB `ENGINE` được tạo khi import `core.db`; tests cần `reset_engine_cache()` nếu đổi runtime path.
- Attendance engine cũng cached qua `lru_cache`.
- Không tạo UI DB-backed trước khi gọi `init_db()`/`init_attendance_db()` trong tests/smoke.

### 4. Configuration/path pattern

Files:

- `core/config.py`
- `core/paths.py`

Key env vars:

- `APP_NAME`
- `APP_RUNTIME_DIR_NAME`
- `APP_DB_PATH`
- `APP_LOG_DIR`
- `APP_EXPORT_DIR`
- `APP_BACKUP_DIR`
- `APP_TEMP_DIR`
- `APP_LOG_LEVEL`
- `APP_UPDATE_MANIFEST_URL`
- `APP_UPDATE_TIMEOUT_MS`
- `APP_UPDATE_DOWNLOAD_TIMEOUT_MS`
- `APP_UPDATE_DOWNLOAD_RETRY_COUNT`
- `APP_UPDATE_STARTUP_DELAY_MS`

Default:

- Runtime dir under `%LOCALAPPDATA%/QuanLyHangHoa`.
- If `LOCALAPPDATA` missing, fallback legacy `data/` under repo.
- Có migration từ legacy runtime dir sang current dir trong `migrate_legacy_runtime_dir(...)`.

### 5. Error/log/message pattern

- Custom exceptions: `core.exceptions.AppError`, `ValidationError`, `RepositoryError`, `NotFoundError`.
- User-facing UI message helper: `shared/widgets/message_box.py` (`MessageBox.info/warning/error`).
- Logging:
  - `core.logging.configure_logging(...)`.
  - Diagnostics export dùng log tail.
- Nguyên tắc: không swallow lỗi DB thật bằng broad try/except trong service; UI có thể catch để show message, tests phải init DB đúng thay vì dựa vào lỗi bị nuốt.

## C. Databases Và Schemas

### 1. Main app DB

Base: `core.db.Base`.

#### `Product`

- File: `modules/inventory/models.py`
- Class: `Product`
- Table: `products`
- Fields chính:
  - `id`
  - `product_code_base` unique/indexed
  - `product_name`
  - `unit_mode`
  - `is_active`
  - `created_at`
  - `updated_at`
- Relationships:
  - `prices`
  - `inventory_balance`
  - `receipt_items`
  - `adjustment_items`
  - `invoice_items`
  - `return_items`
- Constraints:
  - non-blank product code/name.
- Soft-delete:
  - `Product.is_active = False` khi có history.
  - hard delete nếu không có history.

#### `ProductPrice`

- Table: `product_prices`.
- Unique: `(product_id, unit_type)`.
- Fields: `product_id`, `unit_type`, `price`, `is_enabled`.
- Service validates unit compatibility.

#### `InventoryBalance`

- Table: `inventory_balances`.
- One row per product.
- Fields:
  - `product_id` unique FK.
  - `on_hand_bao_decimal`
  - `on_hand_bich_integer`
- Rules:
  - `BAO_KG` stores stock only in `on_hand_bao_decimal`.
  - `BICH` stores stock only in `on_hand_bich_integer`.
  - KG is derived from BAO by service, not stored as independent balance.
  - Negative stock is allowed for oversell/correction workflows.

#### `InventoryReceipt` / `InventoryReceiptItem`

- Tables:
  - `inventory_receipts`
  - `inventory_receipt_items`
- Receipt increases stock through `InventoryService.create_receipt(...)`.
- Quantity interpreted by product mode.

#### `InventoryAdjustment` / `InventoryAdjustmentItem`

- Tables:
  - `inventory_adjustments`
  - `inventory_adjustment_items`
- Adjustment stores `old_quantity`, `new_quantity`, computed `delta_quantity`.
- `new_quantity >= 0`, old may be negative.

#### `InventoryStockEffect`

- File: `modules/inventory/models.py`
- Class: `InventoryStockEffect`
- Table: `inventory_stock_effects`
- Purpose: durable source-reference layer for attendance production stock effects.
- Fields:
  - `source_type`
  - `source_id`
  - `source_line_type`
  - `source_line_id`
  - `attendance_employee_id`
  - `attendance_work_date`
  - `attendance_bag_type_id`
  - `product_id`
  - `quantity_delta`
  - `unit_type`
  - `movement_datetime`
  - `note`
  - `created_at`
  - `updated_at`
- Unique:
  - `(source_type, source_id, source_line_type, source_line_id)`.
- Indexes:
  - `(source_type, source_id)`
  - `product_id`.
- Important hardening: `source_line_id` is non-null and service validates it before inserting.

#### `Invoice` / `InvoiceItem`

- File: `modules/sales/models.py`
- Tables:
  - `invoices`
  - `invoice_items`
- Fields:
  - `invoice_code`
  - nullable `customer_id`
  - `customer_snapshot_name`
  - `invoice_datetime`
  - `total_amount`
  - `paid_amount`
  - `payment_method`
  - `status`
  - items have product/unit/quantity/price snapshots.
- Snapshot fields preserve display after product/customer changes.

#### `ReturnInvoice` / `ReturnInvoiceItem`

- File: `modules/returns/models.py`
- Tables:
  - `return_invoices`
  - `return_invoice_items`
- Fields:
  - `return_code`
  - optional `source_invoice_id`
  - optional `customer_id`
  - `customer_snapshot_name`
  - `is_quick_return`
  - `return_datetime`
  - `total_amount`
  - `handling_mode`
  - items snapshot product/unit/price/quantity.

#### `Customer` / `CustomerBalanceLedger`

- File: `modules/customer/models.py`
- Tables:
  - `customers`
  - `customer_balance_ledgers`
- `Customer` fields:
  - `customer_name`
  - `phone`
  - `address`
  - `note`
  - `current_balance`
  - `total_sales`
  - `is_walk_in`
  - `is_active`
- `CustomerBalanceLedger` fields:
  - `customer_id`
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
- Ledger order/source fields were added to avoid ref-id collision and preserve invoice/debt-payment ordering.

#### `OrderRequest` / `OrderRequestItem`

- File: `modules/orders/models.py`
- Tables:
  - `order_requests`
  - `order_request_items`
- Orders store requested products/quantities and optional link to source invoice.
- Creating orders does not directly mutate inventory.

### 2. Attendance DB

Base: `modules.attendance.db.AttendanceBase`.

#### `Employee`

- File: `modules/attendance/models.py`
- Table: `employees`
- Fields:
  - `id`
  - `name` unique
  - `team`: `Team.BLOW` or `Team.CUT`
  - `is_active`
- Delete behavior:
  - hard delete if no `DailyRecord`.
  - deactivate if has `DailyRecord`.

#### `Period` / `EmployeeShiftPeriod`

- Tables:
  - `periods`
  - `employee_shift_periods`
- `Period` has `start_date`, `end_date`, `locked`, `created_at`.
- Unique period date range.

#### `DailyRecord`

- Table: `daily_records`
- Fields:
  - `employee_id`
  - `date`
  - `period_id`
  - `is_absent`
  - `status`: `DRAFT` or `DONE`
  - `total_amount_snapshot`
- Unique: `(employee_id, date)`.
- Relationships:
  - `work_logs`
  - `cut_logs`
  - `extra_cut_work_logs`.

#### `WorkType` / `WorkLog`

- Tables:
  - `work_types`
  - `work_logs`
- `WorkType`:
  - BLOW-only.
  - `input_type`: `QUANTITY` or `TICK`.
  - `unit_price`.
  - `config_json`.
  - `is_active`.
  - Unique `(team, name)`.
- `WorkLog`:
  - `work_type_id`
  - integer `quantity`
  - `unit_price_snapshot`
  - `amount_snapshot`.

#### `BagType`

- Table: `bag_types`.
- Current meaning: CUT work item, now product-linked.
- Fields:
  - `name`
  - legacy `unit_price`
  - `quota_quantity`
  - `excess_unit_price`
  - `is_active`
  - `is_product_linked`
  - `source_product_id`
  - `source_product_name_snapshot`
  - `is_excluded_from_attendance`
  - `is_legacy`
- Partial unique index on `source_product_id` where non-null.
- Product-linked names come from `Product.product_name`.

#### `CutLog`

- Table: `cut_logs`.
- Fields:
  - `daily_record_id`
  - `bag_type_id`
  - `quantity`: `Numeric(12, 3)`, Decimal-capable.
  - `unit_price_snapshot`
  - `quota_quantity_snapshot`
  - `excess_unit_price_snapshot`
  - `amount_snapshot`.
- Unique `(daily_record_id, bag_type_id)`.
- Quantity may be decimal, e.g. `10.5`.

#### `ExtraCutWorkLog`

- Table: `extra_cut_work_logs`.
- Used for BLOW employees doing extra CUT/VK work.
- Fields:
  - `daily_record_id`
  - `bag_type_id`
  - `quantity`: `Numeric(12, 3)`.
  - `excess_unit_price_snapshot`
  - `amount_snapshot`
  - timestamps.
- Formula is `quantity * excess_unit_price_snapshot`, not CUT tiered formula.

## D. Inventory / Hàng Hóa Module

### 1. Product create/update/delete

Files:

- `modules/inventory/service.py`
- `modules/inventory/repository.py`
- `modules/inventory/controller.py`
- `modules/inventory/ui/product_list_view.py`

`InventoryService.create_product(...)`:

- Normalizes code via `validate_product_code_base`.
- Normalizes name via `validate_product_name`.
- Validates price payload.
- Checks existing `product_code_base`, including inactive products.

`InventoryService.update_product(...)`:

- Allows product name/price updates.
- Does not support changing `unit_mode`; raises `ValidationError`.

`InventoryService.delete_product(product_id)`:

- Uses `_has_product_history(product.id)`.
- If history exists: sets `is_active = False`, returns `ProductDeleteResult(action="deactivated")`.
- If no history: hard deletes product, returns `ProductDeleteResult(action="hard_deleted")`.

### 2. Product reactivation behavior

Implemented per `docs/PRODUCT_REACTIVATE_ON_RECREATE.md`.

Behavior:

- If user creates product with same `product_code_base` as an active product:
  - reject as duplicate.
- If same code matches inactive product:
  - if normalized name is same and `unit_mode` is same:
    - reactivate existing row (`is_active=True`);
    - preserve same `Product.id`;
    - preserve history and attendance links;
    - sync prices from payload.
  - if name differs:
    - raise friendly `ValidationError`.
  - if unit mode differs:
    - raise friendly `ValidationError`.

This fixes the old `sqlite3.IntegrityError: UNIQUE constraint failed: products.product_code_base` when recreating inactive products.

### 3. Active/inactive listing

- `InventoryService.list_products(include_inactive=False)` hides inactive by default.
- Product list UI has checkbox “Hiện cả hàng ngừng sử dụng”.

### 4. Stock model

- `BAO_KG`: canonical stock is bao count in `InventoryBalance.on_hand_bao_decimal`.
- KG is derived using `BAO_TO_KG_RATIO`.
- `BICH`: canonical stock is `on_hand_bich_integer` but stored as Decimal-compatible numeric.
- Decimal support exists for quantities.
- Negative stock is allowed.

### 5. Receipts

- `InventoryService.create_receipt(items)` creates `InventoryReceipt` and `InventoryReceiptItem`.
- Increases stock via `increase_stock(...)`.

### 6. Adjustments

- `InventoryService.create_adjustment(items)` stores old/new/delta.
- Applies delta to canonical stock.

### 7. Product delete mode

- `InventoryController.get_delete_mode(product_id)` returns:
  - `hard_delete`
  - `deactivate`
- Product list batch delete uses this to preview before executing.

### 8. Product link to attendance

- `Product.id` maps externally to `BagType.source_product_id`.
- Product rename updates linked `BagType.name` on next sync.
- Product inactive/delete deactivates linked `BagType` on next sync.
- Product reactivation reactivates existing linked BagType if no conflict.

### 9. UI status

`modules/inventory/ui/product_list_view.py`:

- Product search suggestions match/display product name only.
- Add/edit/delete/receipt/adjustment/refresh buttons.
- Multi-delete Batch 2 implemented:
  - shared `TableSelectionModeController`;
  - checkbox column;
  - selected count;
  - pre-confirm hard-delete/deactivate summary;
  - per-product `InventoryController.delete_product(...)`;
  - partial-failure summary;
  - search/filter exits selection mode.

### 10. Tests

- `tests/test_inventory_service.py`
- `tests/test_product_search_ui.py`
- `tests/test_attendance_product_sync.py`

Recent verification after Batch 2:

- `python -m unittest tests.test_inventory_service` passed 25 tests.
- `python -m unittest tests.test_product_search_ui` passed 8 tests.
- `python -m unittest tests.test_attendance_product_sync` passed 14 tests.
- Full discovery passed 489 tests.

## E. Sales / Returns / Customer Debt

### 1. Sales invoices

Files:

- `modules/sales/models.py`
- `modules/sales/service.py`
- `modules/sales/controller.py`
- `modules/sales/ui/*`

Behavior:

- Creating invoice decreases inventory via `InventoryService.decrease_stock(...)`.
- Stores product snapshots on `InvoiceItem`.
- If customer selected, writes customer ledger effects.
- `paid_amount` may be greater than invoice total; overpayment can be applied to older debt.
- Paid amount creates debt-payment style ledger rows when relevant.
- Edit/delete uses rollback/apply style:
  - rollback old inventory/customer effects;
  - apply new state;
  - service-level transaction ensures consistency inside main DB.

### 2. Returns

Files:

- `modules/returns/models.py`
- `modules/returns/service.py`
- `modules/returns/controller.py`
- `modules/returns/ui/*`

Behavior:

- Returns create standalone `ReturnInvoice`.
- Stock increases for returned quantity.
- Customer effects depend on handling mode.
- Delete/edit roll back return effects.

### 3. Customer debt/payment

Files:

- `modules/customer/models.py`
- `modules/customer/service.py`
- `modules/customer/repository.py`
- `modules/customer/ui/*`

Important behavior:

- Customer balance changes are tracked by `CustomerBalanceLedger`.
- Standalone debt payments use generated `ref_id`.
- Generated invoice-payment/overpayment rows use `source_ref_type`, `source_ref_id`, `display_order`.
- Balance recomputation occurs when ledger references are removed/updated.
- Migration `migrate_customer_invoice_payments_to_debt_payment_v1(...)` backs up before transforming old invoice-payment rows.

### 4. History page

Files:

- `shell/history_page.py`
- `modules/sales/ui/transaction_history_view.py`
- `modules/sales/ui/invoice_list_view.py`
- `modules/returns/ui/return_list_view.py`
- `modules/customer/ui/debt_payment_list_view.py`

Structure:

- Transaction history combined view.
- Invoice list.
- Return list.
- Debt payment list.

Delete behavior:

- Single-row delete currently routes to correct controller/service:
  - invoice -> `SalesController.delete_invoice(...)`;
  - return -> `ReturnController.delete_return_invoice(...)`;
  - debt payment -> `CustomerController.delete_debt_payment(...)`.

Why history multi-delete is deferred:

- Rows may affect stock and customer balances.
- Mixed transaction types need ordered rollback.
- Multiple rows for same customer/product may require careful recompute.
- Needs separate design for atomicity and partial success.

### 5. Tests

- `tests/test_sales_service.py`
- `tests/test_return_service.py`
- `tests/test_customer_service.py`
- `tests/test_history_delete_actions.py`
- `tests/test_customer_invoice_payment_migration.py`
- `tests/test_overpayment_ordering_pipeline.py`
- `tests/test_transaction_history_timestamps.py`

## F. Orders / Reports / History

### 1. Orders

Files:

- `modules/orders/models.py`
- `modules/orders/service.py`
- `modules/orders/controller.py`
- `modules/orders/ui/page.py`
- `modules/orders/ui/order_draft_page.py`

Behavior:

- Orders are requests, not stock mutations.
- `OrderRequest` and `OrderRequestItem` store snapshots and requested quantity.
- Creating an order does not touch inventory, invoices, or ledgers.
- Order can later be opened as sales draft/editor flow.

### 2. Reports

Files:

- `modules/reporting/*`
- Attendance reports separately in `modules/attendance/report_service.py` and `modules/attendance/ui/report_tab.py`.

Business reporting reads main DB aggregates.

### 3. History

- `HistoryPage.reload_all_views()` refreshes transaction/list views.
- `AppWindow._handle_data_changed_from_pages()` refreshes history, customer list, inventory list, orders page, reporting dirty state.
- Current limitation: no multi-delete in history.

## G. Attendance / Chấm Công Module Overview

### Subtabs

Main attendance page uses subtabs roughly:

- Nhân viên
- Chấm công
- Báo cáo

Attendance price settings are exposed through main `Cài đặt` page, not necessarily inside attendance tab.

### Employee management

Files:

- `modules/attendance/ui/employee_tab.py`
- `modules/attendance/service.py`

Behavior:

- Create/update employees.
- `Team.BLOW` and `Team.CUT`.
- Delete:
  - no `DailyRecord` -> hard delete;
  - has `DailyRecord` -> `is_active=False`.
- Multi-delete Batch 1 implemented:
  - shared `TableSelectionModeController`;
  - checkbox column;
  - selected count;
  - per-employee `AttendanceEmployeeService.delete_or_deactivate_employee(...)`;
  - hard-delete/deactivate/failure summary;
  - search/filter exits selection mode.

### Day entry

Files:

- `modules/attendance/ui/day_entry_tab.py`
- `modules/attendance/service.py`
- `modules/attendance/repository.py`
- DTOs in `modules/attendance/dto.py`.

Behavior:

- Select date/employee.
- Load `DayEntryDTO`.
- Supports `DRAFT` and `DONE`.
- Absent day clears/ignores work lines.
- `save_attendance(payload, finalize=False)` saves draft.
- `save_attendance(payload, finalize=True)` finalizes to `DONE`.
- Editing finalized records rebuilds logs and recalculates snapshots.

Inventory effect integration:

- After logs are rebuilt and attendance session is flushed, `AttendanceDayEntryService` builds `AttendanceInventoryEffectSnapshot`.
- Calls `AttendanceInventoryEffectService.reconcile_daily_record_effects(snapshot)`.
- DRAFT/absent rollback any previous effects and apply none.
- DONE applies current CUT/VK production to inventory.

### BLOW team day entry

- Uses `WorkType` rows.
- `WorkInputType.QUANTITY`: numeric quantity.
- `WorkInputType.TICK`: checkbox/tick.
- `Phụ găng 1 máy`, `Phụ găng 2 máy` have special handling in code/tests.
- `Thừa máy` is the only quantity work using quota `-3` behavior in `calculate_blow_work_amount(...)`.
- BLOW can optionally add extra CUT/VK work via “Có làm thêm việc cắt” / “Việc cắt làm thêm”.

### CUT team day entry

- Uses product-linked `BagType` rows.
- CUT quantities are Decimal-capable.
- Available list for new selection is filtered:
  - `is_active == True`
  - `is_product_linked == True`
  - `is_excluded_from_attendance == False`
  - `is_legacy == False`
  - `quota_quantity > 0`
  - `excess_unit_price > 0`
- Historical existing rows can still reload even if now inactive/legacy/excluded/incomplete.

### Reports

Attendance reports:

- 10-day report.
- 30-day report.
- Decimal CUT quantities display cleanly.
- Integer decimals display as integer text.
- VK money totals aggregate decimal-derived amounts.

### Attendance settings

File: `modules/attendance/ui/settings_tab.py`.

Current status:

- `AttendancePriceSettingsTab` runs product-to-CUT sync on reload.
- Dropdown section switcher implemented:
  - `Công việc tổ thổi`
  - `Loại bao tổ cắt`
- Only one section/table shown at a time.
- CUT manual add button removed/hidden from UI; BLOW add remains.
- Product-linked CUT names are read-only.
- Editable:
  - `quota_quantity`
  - `excess_unit_price`
  - `Không dùng cho chấm công`
- Incomplete product-linked rows have light red highlight.
- Sync warning banner shown for duplicate/conflict warnings.

### Important tests

- `tests/test_attendance_employee_management.py`
- `tests/test_attendance_day_entry.py`
- `tests/test_attendance_settings.py`
- `tests/test_attendance_settings_ui.py`
- `tests/test_attendance_report.py`
- `tests/test_app_window_attendance_sync.py`
- `tests/test_attendance_product_sync.py`
- `tests/test_attendance_inventory_effect_service.py`
- `tests/test_attendance_inventory_integration.py`
- `tests/test_attendance_inventory_diagnostics.py`
- `tests/test_attendance_inventory_diagnostics_ui.py`

## H. BLOW Team / Tổ Thổi Business Rules

### 1. WorkType types

`WorkType.input_type`:

- `WorkInputType.QUANTITY`
- `WorkInputType.TICK`

### 2. Quota behavior

File: `modules/attendance/blow_work.py`.

Actual rule:

- Constant: `BLOW_QUANTITY_WORK_QUOTA = 3`.
- Work name constant: `BLOW_QUANTITY_QUOTA_WORK_NAME = "Thừa máy"` (source file may show mojibake in some terminal output; intended Vietnamese is “Thừa máy”).
- Only `Thừa máy` applies `max(0, quantity - 3) * unit_price`.
- Other quantity work uses `quantity * unit_price`.
- Tick work pays `unit_price` if quantity/tick > 0, else 0.

Important correction: not all numeric machine work has `-3`; only `Thừa máy`.

### 3. Quantity defaults

- Normal BLOW quantity work uses integer quantity in `WorkLog.quantity`.
- UI defaults are compact and no spinbox arrows where previously adjusted.

### 4. Checkbox work

- Tick work like `Phụ găng` behaves as single checked/unchecked amount.

### 5. BLOW extra CUT / VK

- UI section: `Có làm thêm việc cắt` / `Việc cắt làm thêm`.
- Uses product-linked configured `BagType` list.
- Quantity can be Decimal.
- Formula:

```text
amount = quantity * excess_unit_price_snapshot
```

- Does not apply CUT tiered formula.
- Does not apply BLOW `Thừa máy -3` rule.
- When record is `DONE`, quantity increases inventory for linked product.

### 6. Reports

- VK money appears in BLOW reports.
- Monthly/period totals include VK amount.

## I. CUT Team / Tổ Cắt Business Rules

### 1. Product-linked CUT items

CUT work items are `BagType` rows linked from inventory products:

- `BagType.is_product_linked = True`
- `BagType.source_product_id = Product.id`
- `BagType.name = Product.product_name`

### 2. Manual CUT item add

Manual CUT add from attendance price settings has been removed from UI. CUT items now come from inventory products.

### 3. BagType config

Each product-linked `BagType` has:

- `quota_quantity`
- `excess_unit_price`
- `is_excluded_from_attendance`

Checkbox label: `Không dùng cho chấm công`.

Semantics:

- checked -> intentionally not used for attendance.
- unchecked -> expected to be configured and available.

### 4. Incomplete config

Incomplete if:

```text
is_product_linked == true
AND is_active == true
AND is_excluded_from_attendance == false
AND (quota_quantity == 0 OR excess_unit_price == 0)
```

Behavior:

- warning popup when entering large `Chấm công` tab;
- red highlight in price settings;
- hidden from day-entry new selection until configured;
- excluded rows do not trigger popup.

### 5. CUT calculation

File: `modules/attendance/cut_bonus.py`.

`calculate_cut_employee_bonus(items)`:

- Converts quantity/quota/price to `Decimal`.
- Ignores zero-quantity items.
- If no active items -> 0.
- Computes:
  - `total_quantity`
  - `quota_avg = sum(quota) / item_count`
- If `total_quantity <= quota_avg` -> 0.
- If any item reaches its own quota:
  - for each item:
    - if `quantity >= quota`: `(quantity - quota) * price`
    - else: `quantity * price`
- Otherwise:
  - sum `max(0, quantity - quota/item_count) * price`.
- Decimal quantities supported.
- No penalty below quota.

### 6. Inventory effect

- DONE `CutLog.quantity` increases linked product stock.
- DRAFT no effect.
- Editing DONE uses rollback/apply.
- DONE -> DRAFT/absent rolls back old effects.

### 7. Reports

- 10-day and 30-day reports display decimal quantities cleanly.
- Monthly totals sum decimal quantities without float artifacts.

## J. Product ↔ Attendance Link Feature

### 1. Sync service

File: `modules/attendance/product_sync_service.py`.

Class: `AttendanceProductSyncService`.

Fields added to `BagType`:

- `is_product_linked`
- `source_product_id`
- `source_product_name_snapshot`
- `is_excluded_from_attendance`
- `is_legacy`

No cross-database FK. `source_product_id` is external reference to main DB `products.id`.

### 2. Sync triggers

- Attendance price settings reload.
- Entering large `Chấm công` tab.
- Settings popup navigation reload/focus.

There is no need to sync on every keystroke/search.

### 3. Product create

Active product without linked BagType creates:

- `name = product.product_name`
- `quota_quantity = 0`
- `excess_unit_price = 0`
- `is_active = True`
- `is_product_linked = True`
- `source_product_id = product.id`
- `source_product_name_snapshot = product.product_name`
- `is_excluded_from_attendance = False`
- `is_legacy = False`

### 4. Product rename

Updates linked `BagType.name` and `source_product_name_snapshot`, preserving quota/price/exclusion/history.

### 5. Product inactive/delete

- Linked BagType deactivated.
- If has history or missing product, mark `is_legacy=True`.
- No hard delete of historical BagTypes.

### 6. Old manual BagType

- Manual non-product-linked active rows are deactivated by sync.
- With history: mark legacy/inactive.
- Without history: deactivate, no hard delete in sync service.

### 7. Conflict policy

- Duplicate active product names are warnings and skipped.
- Product name conflict with existing manual `BagType.name` is warning and skipped.
- Product rename conflict is warning and skipped.
- No suffix auto-append.

### 8. Incomplete config popup

`AppWindow._handle_enter_attendance_tab()`:

- Runs sync.
- If `sync_result.incomplete_items` non-empty, show warning popup.
- Buttons:
  - `Đi tới cài đặt`
  - `Để sau`
- “Đi tới cài đặt” navigates to `Cài đặt` and focuses Attendance price settings/CUT row.

### 9. Day-entry filtering

New selection list only includes active/product-linked/not-excluded/not-legacy/configured BagTypes.

Historical reload:

- Existing saved `bag_type_id`s are included for display/editing even if no longer valid for new selection.

### 10. Save-time validation

Batch 5 added service-level validation:

- Newly added CUT/VK rows must satisfy configured product-linked rule.
- Existing historical rows in original record may be saved again for compatibility.
- Invalid new item raises `ValidationError` with user-friendly message.

### 11. Docs/tests

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

## K. Attendance CUT/VK → Inventory Feature

### 1. Requirement

Finalized attendance production should update inventory:

- CUT employee `CutLog.quantity` increases linked product stock.
- BLOW extra CUT/VK `ExtraCutWorkLog.quantity` also increases linked product stock.
- DRAFT does not update stock.
- Old historical DONE records are not auto-backfilled.
- If user explicitly saves/finalizes an old record after feature exists, it reconciles from that save onward.

### 2. `inventory_stock_effects`

File: `modules/inventory/models.py`.

Class/table:

- `InventoryStockEffect`
- `inventory_stock_effects`

Constants from `modules/attendance/inventory_effect_service.py`:

- `ATTENDANCE_DAILY_RECORD_SOURCE_TYPE = "ATTENDANCE_DAILY_RECORD"`
- `CUT_LOG_SOURCE_LINE_TYPE = "CUT_LOG"`
- `EXTRA_CUT_WORK_LOG_SOURCE_LINE_TYPE = "EXTRA_CUT_WORK_LOG"`

Key fields:

- `source_type = ATTENDANCE_DAILY_RECORD`
- `source_id = DailyRecord.id`
- `source_line_type = CUT_LOG` or `EXTRA_CUT_WORK_LOG`
- `source_line_id = CutLog.id` or `ExtraCutWorkLog.id`
- `product_id`
- `quantity_delta`
- `unit_type`
- attendance snapshots.

Hardening:

- `source_line_id` is required/non-null.
- Duplicate `(source_type, source_id, source_line_type, source_line_id)` rejected.
- Service validates unsupported `source_line_type`.

### 3. `AttendanceInventoryEffectService`

File: `modules/attendance/inventory_effect_service.py`.

DTOs:

- `AttendanceInventoryEffectLine`
- `AttendanceInventoryEffectSnapshot`
- `AttendanceInventoryEffectResult`
- `AttendanceInventoryEffectProductDelta`

Method:

- `reconcile_daily_record_effects(snapshot)`

Behavior:

1. Validate snapshot identity.
2. Open main DB transaction.
3. Validate lines before apply.
4. Load old effects by `(source_type, source_id)`.
5. Roll back old effects by decreasing stock and deleting old effect rows.
6. If snapshot is not DONE or is absent: commit rollback only.
7. If DONE/non-absent:
   - increase stock for each prepared line;
   - insert `InventoryStockEffect` rows.
8. Return counts/deltas.

Unit mapping:

- `Product.unit_mode == BAO_KG` -> `UnitType.BAO`.
- `Product.unit_mode == BICH` -> `UnitType.BICH`.
- No KG conversion is applied for attendance production.

Decimal:

- Uses `Decimal`, no float.

### 4. Integration into `AttendanceDayEntryService.save_attendance`

File: `modules/attendance/service.py`.

Call order:

1. Open attendance session/transaction.
2. Load/create `DailyRecord`.
3. Capture existing bag ids for historical validation.
4. Clear/rebuild logs.
5. Set `status` to `DONE` if finalize else `DRAFT`.
6. Flush attendance session so `CutLog.id` and `ExtraCutWorkLog.id` exist.
7. Build `AttendanceInventoryEffectSnapshot`.
8. Call `AttendanceInventoryEffectService.reconcile_daily_record_effects(snapshot)`.
9. Return success only if reconcile succeeds.

Error propagation:

- Inventory effect failures propagate; UI should not claim save success.
- Logs include `daily_record_id`, `employee_id`, date.

Cross-DB caveat:

- Attendance and main DB are separate SQLite files.
- Full atomicity across both DBs is not guaranteed.
- Diagnostic/reconcile service mitigates stale/missing effects.

### 5. `AttendanceInventoryDiagnosticService`

File: `modules/attendance/inventory_diagnostic_service.py`.

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

Scan is read-only. Reconcile is explicit/manual, one selected daily record at a time. No automatic backfill.

### 6. Admin diagnostics UI

Implemented in `modules/settings/ui/page.py`:

- `AttendanceInventoryDiagnosticsPanel`.
- Button to scan issues.
- Table/list of issues with Vietnamese labels.
- Selected issue can run `reconcile_daily_record(daily_record_id)` after confirmation.
- Missing-source issues are not auto-cleaned.

Report: `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH4.md`.

### 7. Docs/tests

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

Files:

- `modules/settings/ui/page.py`
- `modules/settings/service.py`

Settings has:

- General settings.
- UI scale preset.
- Update check button/status.
- Backup button.
- Open logs button.
- Export diagnostics button.
- Attendance inventory diagnostics panel.
- Attendance price settings tab via `AttendancePriceSettingsTab`.

### 2. Backup

File: `modules/settings/backup_service.py`.

`UserBackupService.create_user_backup()`:

- Creates zip in `settings.backup_dir`.
- Includes `app.db` if present.
- Includes `attendance.db` if present.
- Adds `manifest.json` with included/missing files and source paths.

Caveat:

- Because product-attendance/inventory links span both DBs, restore both DBs together.

### 3. Diagnostics

File: `modules/diagnostics/service.py`.

`DiagnosticsService.export_diagnostics()` creates zip under `exports/diagnostics` with:

- `app_info.json`
- `ui_environment.json`
- `recent_log.txt`

It does not include DB files.

### 4. Auto-update

Files:

- `core/version.py`
- `version.json`
- `modules/update/service.py`
- `modules/update/ui/update_dialog.py`
- `scripts/check_version.ps1`
- GitHub release workflow.

Manifest fields:

- `version`
- `installer_url`
- `notes`
- `min_required_version`

Default manifest URL:

- `core.config.DEFAULT_UPDATE_MANIFEST_URL`
- currently `https://raw.githubusercontent.com/antongduy2307/QuanLyHangHoa/main/version.json`.

Release flow:

1. Update `core/version.py`.
2. Update `version.json`.
3. Build PyInstaller app.
4. Build installer.
5. Publish GitHub Release.
6. Verify `installer_url` is direct `.exe` URL and matches release artifact.
7. Commit/push `version.json`.

Common failure:

- `version.json` raw URL points to old repo/link or installer URL not direct `.exe`.

### 5. Background image feature

Current repo inspection did not find a central implemented app-background image helper via `rg` for `_MEIPASS`, `BACKGROUND`, or `image/`. There is a root `.jpg` file in the repo root, but no root `image/` folder in the current listing. Treat background image behavior as uncertain/not active unless verified in latest branch.

If reintroduced, requirement from prior prompts was:

- root `image/*.jpg` optional;
- no crash if missing/invalid;
- PyInstaller optional data include if folder exists;
- opacity around 20%;
- broad containers semi-transparent enough for readability.

## M. UI Changes Và Current UX State

### 1. Main tab order

`HistoryPage` is inserted before `Chấm công` and `Cài đặt`, so `Lịch sử` appears before those tabs.

### 2. Attendance reports

Reports have 10-day and 30-day views. Prior UI work focused on flexible width, spacer behavior between employees, total rows, decimal quantity display, and readable tables.

### 3. Numeric input style

- CUT and VK quantity inputs allow decimal.
- Avoid float.
- Compact line-edit style preferred over spinbox arrows for day-entry quantities.
- Integer decimals display without `.0`.

### 4. CUT/VK search/add behavior

- Search lists configured product-linked CUT items.
- Excluded/incomplete/legacy items hidden from new selection.
- Existing saved rows reload even if later invalid.

### 5. Multi-delete

Shared helper:

- `shared/widgets/table_selection_mode.py`
- Class: `TableSelectionModeController`.

Implemented:

- Attendance employees: `docs/MULTI_DELETE_EMPLOYEE_BATCH1.md`.
- Inventory products: `docs/MULTI_DELETE_PRODUCT_BATCH2.md`.

Deferred:

- `Lịch sử` multi-delete due high business risk.

### 6. Known UI caveats

- Some source files have mojibake in Vietnamese string literals because earlier code already contained mojibake in places. Do not mass-normalize unrelated files casually; only fix strings in touched UI where tests/UX require it.
- Existing dialogs can be modal; tests patch message boxes to avoid offscreen hangs.

## N. Testing Và CI/CD Status

### 1. Test framework

- `unittest`.
- PyQt tests run with `QApplication` and `QT_QPA_PLATFORM=offscreen`.

### 2. Important commands

```powershell
python -m unittest discover -s tests -p "test*.py" -t .
python -m compileall core modules tests shell
```

With local venv:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -t .
.\.venv\Scripts\python.exe -m compileall core modules tests shell
```

### 3. Current test count

Most recent full discovery after product multi-delete Batch 2:

- `Ran 489 tests`
- `OK`

### 4. CI/CD workflows

`.github/workflows/ci.yml`:

- Windows latest.
- Sets `QT_QPA_PLATFORM=offscreen`.
- Sets `LOCALAPPDATA=$RUNNER_TEMP\QuanLyHangHoaTest`.
- Installs `requirements.txt`.
- Runs:
  - `python -m unittest discover -s tests -p "test*.py" -t .`
  - `python -m compileall core modules tests shell`.

`.github/workflows/release.yml`:

- On tags `v*` or workflow dispatch.
- Checks tag matches app version.
- Runs tests/compileall.
- Builds PyInstaller app.
- Installs Inno Setup.
- Builds installer.
- Uploads artifacts and publishes GitHub Release.

### 5. Previous CI issues fixed

Docs:

- `docs/CI_DB_INIT_UI_RELOAD_FIX.md`
- `docs/CI_NO_SUCH_TABLE_INVOICES_INVESTIGATION.md`
- `docs/CI_TEST_RUNTIME_STABILITY_SECOND_PASS.md`

Issues:

- `ImportError: Start directory is not importable: 'tests'` fixed by making `tests/` importable and using `-s tests -p "test*.py" -t .`.
- UI smoke DB init fixed: call `init_db()` before DB-backed UI construction.
- Test temp dirs moved away from tracked repo where possible; ignore safety net for `tests/_tmp/`, `tests/_diagnostics_tmp/`.
- Avoid modal hangs by patching `MessageBox` in UI tests.

### 6. Test helpers

- `tests/helpers/runtime.py` exists for temp runtime/DB init patterns.
- Many tests patch env `LOCALAPPDATA`, reset settings cache, reset DB engines, and use fake/no-op services.
- Attendance report/day-entry tests often inject `_NoopInventoryEffectService` to avoid main DB effects when not under test.

### 7. Guidance

- Always run focused tests for changed module.
- Then run full discovery and compileall.
- Do not let tests write long-lived temp DB/log dirs under repo.
- Restore tracked generated `.pyc` if compileall touches tracked pycache files.

## O. Important Decisions / Design Rationale

1. Keep two DBs for now.
   - Merging `app.db` and `attendance.db` is high-risk and needs dedicated migration.

2. Do not auto-backfill old attendance DONE records.
   - Inventory effects apply going forward or on explicit save/reconcile.

3. Product-linked `BagType` names come from `Product.product_name`.
   - Attendance settings should not freely rename linked CUT work.

4. CUT manual add removed.
   - Source of truth is inventory product list.

5. Use `inventory_stock_effects`, not blind stock increments.
   - Enables rollback/apply and idempotence.

6. Rollback/apply by attendance daily record source.
   - Attendance logs are cleared/recreated on edit; old line IDs can change.

7. Defer `Lịch sử` multi-delete.
   - Stock/debt rollback and ordering risks are nontrivial.

8. Product recreate same code/name reactivates inactive product.
   - Preserves product id, history, and attendance links.

9. Backup/restore must treat both DBs together.
   - Cross-DB external references exist.

10. `version.json` must be manually checked.
    - Raw manifest and installer URLs are not automatically guaranteed correct.

## P. Current Open Tasks / Next Steps

### 1. Product reactivation on recreate same code/name

Status: implemented.

Report: `docs/PRODUCT_REACTIVATE_ON_RECREATE.md`.

Keep tests around:

- inactive same code/name reactivates.
- same code/different name rejects.
- same code/name/different unit mode rejects.
- attendance sync sees reactivated product.

### 2. Attendance price settings UI cleanup

Status: implemented.

Report: `docs/ATTENDANCE_PRICE_SETTINGS_UI_BATCH1.md`.

Implemented:

- Dropdown:
  - `Công việc tổ thổi`
  - `Loại bao tổ cắt`
- Only one section visible at a time.
- CUT add button removed from UI.
- Product-linked CUT rows still editable for quota/price/exclusion.

### 3. Multi-delete

Status:

- Investigation done: `docs/MULTI_DELETE_UI_INVESTIGATION.md`.
- Employee tab done: `docs/MULTI_DELETE_EMPLOYEE_BATCH1.md`.
- Product list done: `docs/MULTI_DELETE_PRODUCT_BATCH2.md`.
- History deferred.

Next if needed:

- Dedicated investigation/design for history bulk delete atomicity and ordering.

### 4. Admin UI for Attendance inventory diagnostics

Status: implemented in settings page.

Report: `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH4.md`.

Current behavior:

- manual scan;
- issue table;
- manual reconcile selected daily record;
- no auto-backfill or missing-source cleanup.

### 5. Optional manual backfill tool

Pending.

Recommended design:

- Preview old DONE records without effects.
- Show expected product deltas.
- Manual apply only with confirmation.
- No automatic startup backfill.

### 6. Future DB unification

Pending/not recommended now.

Needs dedicated migration plan:

- copy attendance tables into main DB or attach DBs;
- preserve IDs and snapshots;
- verify backup/restore;
- test all reports and inventory effects.

### 7. Web/online attendance idea

Discussed conceptually only.

Potential future:

- separate backend/web app for employee QR attendance;
- desktop remains admin/config/report app;
- do not mix into current desktop code without new architecture plan.

### 8. Known caveats

- Two DBs mean cross-DB partial commit risk remains.
- `AttendanceInventoryDiagnosticService` mitigates but does not make transactions atomic.
- Some older DBs may have gone through migrations; always test existing DB upgrade paths.
- Some terminal output shows mojibake for Vietnamese; inspect files with UTF-8-capable editor.
- Do not broad-catch DB errors to hide setup mistakes.

## Q. How To Continue In A New Chat Session

### 1. Files to provide first

If future assistant needs context, provide/read:

- `docs/PROJECT_HANDOFF_SUMMARY.md` first.
- The latest feature report related to the task, e.g.:
  - product-attendance: `docs/ATTENDANCE_PRODUCT_CUT_SYNC_*.md`
  - CUT/VK inventory: `docs/ATTENDANCE_CUT_TO_INVENTORY_*.md`
  - multi-delete: `docs/MULTI_DELETE_*.md`
  - CI stability: `docs/CI_*.md`
- Relevant screenshots/logs.
- Latest failing command output.

### 2. What not to assume

- Do not assume DB merge happened.
- Do not assume old attendance DONE records are backfilled.
- Do not assume `Lịch sử` multi-delete is safe.
- Do not assume `version.json` updates automatically.
- Do not assume product-linked BagTypes can be renamed in attendance.
- Do not assume DRAFT attendance affects inventory.

### 3. Prompting future Codex sessions

Prefer small batches:

- Investigation/design batch first for risky work.
- Implementation batch with narrow scope.
- Require docs report output for each feature batch.
- Require focused tests, full discovery, and compileall.

Example pattern:

```text
Implement Batch N only.
Do not change unrelated modules.
Create docs/FEATURE_BATCH_N.md.
Run focused tests, unittest discover, compileall.
```

### 4. Commands before release

```powershell
python -m unittest discover -s tests -p "test*.py" -t .
python -m compileall core modules tests shell
.\scripts\check_version.ps1 -Tag v0.8.0
.\scripts\build_exe.ps1
.\scripts\build_installer.ps1
```

Also manually verify:

- `core/version.py`
- `version.json`
- GitHub Release artifact name
- direct installer URL.

### 5. Critical safety rules

- Do not change attendance formulas casually.
- Do not change sales/return/customer rollback logic casually.
- Do not bulk mutate inventory without source reference.
- Do not auto-backfill attendance inventory effects.
- Do not skip/delete tests.
- Do not hide DB errors with broad try/except.
- Do not hard-delete historical products/employees/BagTypes.
- Do not merge DBs without dedicated migration plan.

## R. Appendix: Documents And Test Files Index

### Generated docs present

- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_INVESTIGATION.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH1.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH2.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH3.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH4.md`
- `docs/ATTENDANCE_PRODUCT_CUT_SYNC_BATCH5.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_INVESTIGATION.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH1.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_PREFLIGHT.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH2.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH3.md`
- `docs/ATTENDANCE_CUT_TO_INVENTORY_BATCH4.md`
- `docs/ATTENDANCE_PRICE_SETTINGS_UI_BATCH1.md`
- `docs/MULTI_DELETE_UI_INVESTIGATION.md`
- `docs/MULTI_DELETE_EMPLOYEE_BATCH1.md`
- `docs/MULTI_DELETE_PRODUCT_BATCH2.md`
- `docs/PRODUCT_REACTIVATE_ON_RECREATE.md`
- `docs/CI_DB_INIT_UI_RELOAD_FIX.md`
- `docs/CI_NO_SUCH_TABLE_INVOICES_INVESTIGATION.md`
- `docs/CI_TEST_RUNTIME_STABILITY_SECOND_PASS.md`
- `docs/PROJECT_HANDOFF_SUMMARY.md`

### Important tests

- `tests/test_smoke.py`
- `tests/test_schema_invariants.py`
- `tests/test_inventory_service.py`
- `tests/test_inventory_transactions.py`
- `tests/test_product_search_ui.py`
- `tests/test_sales_service.py`
- `tests/test_return_service.py`
- `tests/test_customer_service.py`
- `tests/test_customer_ui.py`
- `tests/test_customer_list_search.py`
- `tests/test_customer_invoice_payment_migration.py`
- `tests/test_history_delete_actions.py`
- `tests/test_order_service.py`
- `tests/test_order_ui.py`
- `tests/test_sales_pos_layout.py`
- `tests/test_reporting_service.py`
- `tests/test_attendance_batch1.py`
- `tests/test_attendance_employee_management.py`
- `tests/test_attendance_day_entry.py`
- `tests/test_attendance_settings.py`
- `tests/test_attendance_settings_ui.py`
- `tests/test_attendance_product_sync.py`
- `tests/test_app_window_attendance_sync.py`
- `tests/test_attendance_report.py`
- `tests/test_attendance_inventory_effect_service.py`
- `tests/test_attendance_inventory_integration.py`
- `tests/test_attendance_inventory_diagnostics.py`
- `tests/test_attendance_inventory_diagnostics_ui.py`
- `tests/test_settings_backup.py`
- `tests/test_diagnostics_service.py`
- `tests/test_update_service.py`

### Recent verification snapshot

From latest multi-delete Batch 2 run:

```text
python -m unittest tests.test_inventory_service        # OK, 25 tests
python -m unittest tests.test_product_search_ui        # OK, 8 tests
python -m unittest tests.test_attendance_product_sync  # OK, 14 tests
python -m unittest discover -s tests -p "test*.py" -t . # OK, 489 tests
python -m compileall core modules tests shell          # OK
```
