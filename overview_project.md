# TỔNG QUAN DỰ ÁN: QUẢN LÝ HÀNG HÓA

## 1. Mục tiêu hệ thống

Ứng dụng được xây dựng nhằm phục vụ quản lý bán hàng cho mô hình kinh doanh nhỏ–trung bình với các yêu cầu thực tế:

* Quản lý hàng hóa và tồn kho
* Quản lý khách hàng và công nợ
* Ghi nhận bán hàng, trả hàng, trả nợ
* Theo dõi lịch sử giao dịch
* Báo cáo doanh thu và sản phẩm
* Hoạt động offline với database local
* Có khả năng đóng gói và update tự động

Hệ thống được thiết kế theo hướng module hóa rõ ràng: service → repository → UI.

---

## 2. Kiến trúc tổng thể

### 2.1 Layer chính

* **UI Layer (PyQt)**: hiển thị, tương tác
* **Controller Layer**: trung gian UI ↔ Service
* **Service Layer**: xử lý nghiệp vụ
* **Repository Layer**: truy cập database
* **Core Layer**: config, DB, path

### 2.2 Database

* SQLite
* Lưu tại: `%LOCALAPPDATA%/<AppName>/app.db`
* Tách khỏi thư mục cài đặt → đảm bảo không mất dữ liệu khi update

---

## 3. Module chức năng chính

## 3.1 Hàng hóa (Inventory)

### Chức năng

* Tạo / sửa / xóa sản phẩm
* Quản lý đơn vị (bao, kg, ...)
* Nhập kho
* Điều chỉnh kho
* Trạng thái: đang dùng / ngừng sử dụng

### Logic quan trọng

* Không xóa cứng nếu đã có lịch sử
* Cho phép tồn kho âm (thiết kế mới)
* Điều chỉnh kho dùng bảng `inventory_adjustment_items`

### Fix quan trọng

* Bỏ constraint `old_quantity >= 0`
  → cho phép điều chỉnh khi tồn kho đang âm

---

## 3.2 Bán hàng (Sales)

### Flow

1. Chọn khách (khách lẻ / khách quen)
2. Tìm sản phẩm (autocomplete dropdown)
3. Nhập số lượng / giá
4. Tính tổng
5. Thanh toán

### Đặc điểm thiết kế

* Giá có thể override (custom price)
* Delay khi nhập giá → tránh lag UI
* Autocomplete dropdown thay cho list cố định

### Công nợ

* Nếu khách trả < tổng tiền:
  → tạo công nợ
* Sau mỗi hóa đơn:
  → hiển thị công nợ hiện tại

---

## 3.3 Khách hàng (Customer)

### Chức năng

* CRUD khách hàng
* Theo dõi công nợ
* Lịch sử giao dịch

### Cải tiến

* Lịch sử bao gồm:

  * Hóa đơn
  * Trả hàng
  * Trả nợ

---

## 3.4 Trả hàng (Returns)

### 2 chế độ

* Trả theo hóa đơn
* Trả nhanh

### Logic chính

* Không sửa hóa đơn gốc
* Phiếu trả có `source_invoice_id`

### Update semantics (quan trọng)

Sử dụng chiến lược:
→ rollback → apply lại

Cụ thể:

1. Rollback phiếu cũ

   * giảm tồn kho
   * hoàn lại công nợ
   * remove ledger

2. Apply phiếu mới

   * cập nhật item
   * apply inventory
   * apply ledger

### Ledger strategy

* Remove old effect
* Apply new effect
  → tránh double counting

---

## 3.5 Trả nợ (Debt Payment)

### Chức năng

* Khách thanh toán công nợ

### Logic

* Ghi ledger
* Giảm current_balance

---

## 3.6 Lịch sử giao dịch (Transaction History)

### Bao gồm

* Hóa đơn
* Trả hàng
* Trả nợ

### Cải tiến

* Tìm theo tên khách (không theo mã)
* Có thể chỉnh timestamp

### Vấn đề đã fix

* Sai lệch thời gian → chuẩn hóa timezone

---

## 3.7 Báo cáo (Reporting)

### Bao gồm

* Doanh thu theo thời gian
* Top sản phẩm

### Thay đổi

* Bỏ cột "số lượng ròng"

---

## 4. UI/UX System

## 4.1 Scaling system

### Preset

* Chuẩn (0.85)
* To (1.0)
* Rất to (1.25)

### Đặc điểm

* Lưu bằng QSettings
* Apply runtime
* Mở rộng dần sang toàn app

---

## 4.2 Table system (quan trọng)

### Mục tiêu

* Full width
* Resize được
* Không vỡ layout

### Behavior

* Default: equal width
* Không nhỏ hơn header
* Stretch toàn bảng
* User resize được nhưng:

  * không nhỏ hơn min

### Persistence

* Lưu width theo từng bảng
* Key: `table_widths/<persistence_key>`

---

## 4.3 Autocomplete system

### Áp dụng

* Search sản phẩm
* Search khách hàng

### Behavior

* Dropdown popup
* Không hiển thị khi không search

### Bug đã fix

* Crash do object bị delete

---

## 4.4 Popup system

### Vấn đề

* Font lớn → popup bị che

### Giải pháp

* Resize popup theo content
* Hoặc giảm font riêng popup

---

## 5. Data & Runtime

## 5.1 AppData structure

```
%LOCALAPPDATA%/<AppName>/
  ├── app.db
  ├── exports/
  ├── backups/
  └── temp/
```

### Ưu điểm

* Không mất dữ liệu khi uninstall
* Phù hợp installer

---

## 6. Packaging & Deployment

## 6.1 Build

* PyInstaller (onedir)

## 6.2 Installer

* Inno Setup
* Install vào Program Files

## 6.3 Behavior

* AppData không bị xóa khi uninstall

---

## 7. Auto Update System (v1)

### Flow

1. Check version.json
2. So sánh version
3. Download installer
4. Chạy installer

### Lỗi đã phát hiện

* Download fail nhưng vẫn run exe

### Fix

* Check file tồn tại
* Retry
* Timeout hợp lý

---

## 8. Các vấn đề đã xử lý

### Backend

* Ledger double-count
* Constraint inventory âm
* Timestamp sai

### UI

* Dropdown mất focus
* Resize bảng
* Scale không đồng bộ

### Deployment

* Path DB sai
* Installer path lỗi

---

## 9. Các điểm thiết kế quan trọng

### 1. Không sửa dữ liệu gốc

→ mọi update đều rollback + apply

### 2. Ledger là nguồn sự thật

→ không tính toán lại từ invoice

### 3. UI responsive theo scale

→ hỗ trợ nhiều máy

### 4. Local-first architecture

→ không phụ thuộc server

---

## 10. Hạn chế hiện tại

* Auto update chưa robust hoàn toàn
* UI scale chưa apply toàn app
* Chưa có logging system chuẩn
* Chưa có migration DB tự động

---

## 11. Hướng phát triển tiếp

* Hoàn thiện auto update
* Logging + crash report
* Cloud sync (optional)
* Multi-user
* Role permission

---

## 12. Kết luận

Hệ thống hiện tại đã đạt:

* Nghiệp vụ core hoàn chỉnh
* UI usable thực tế
* Có installer + update nền tảng

Các bước tiếp theo chủ yếu là:

* ổn định
* chuẩn hóa
* scale

---

## Project Structure Overview

### 3.1 Tree structure

```text
.
├── core/
│   ├── config.py
│   ├── db.py
│   ├── enums.py
│   ├── exceptions.py
│   ├── logging.py
│   ├── paths.py
│   ├── utils.py
│   └── version.py
├── modules/
│   ├── sales/
│   │   ├── controller.py
│   │   ├── dto.py
│   │   ├── mappers.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   ├── validators.py
│   │   └── ui/
│   │       ├── sales_page.py
│   │       ├── invoice_items_table.py
│   │       ├── invoice_list_view.py
│   │       ├── invoice_detail_popup.py
│   │       ├── invoice_edit_dialog.py
│   │       ├── product_search_widget.py
│   │       ├── customer_picker_widget.py
│   │       ├── transaction_history_view.py
│   │       └── page.py
│   ├── inventory/
│   │   ├── controller.py
│   │   ├── dto.py
│   │   ├── mappers.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   ├── validators.py
│   │   └── ui/
│   │       ├── page.py
│   │       ├── product_list_view.py
│   │       ├── product_dialog.py
│   │       ├── inventory_receipt_dialog.py
│   │       └── inventory_adjustment_dialog.py
│   ├── customer/
│   │   ├── controller.py
│   │   ├── dto.py
│   │   ├── mappers.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   ├── validators.py
│   │   └── ui/
│   │       ├── page.py
│   │       ├── customer_list_view.py
│   │       ├── customer_dialog.py
│   │       ├── customer_detail_popup.py
│   │       ├── debt_payment_dialog.py
│   │       └── debt_payment_list_view.py
│   ├── returns/
│   │   ├── controller.py
│   │   ├── dto.py
│   │   ├── mappers.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   ├── validators.py
│   │   └── ui/
│   │       ├── return_page.py
│   │       ├── return_list_view.py
│   │       ├── return_edit_dialog.py
│   │       ├── return_detail_popup.py
│   │       ├── source_invoice_items_table.py
│   │       ├── source_invoice_search_widget.py
│   │       ├── product_search_widget.py
│   │       └── page.py
│   ├── reporting/
│   │   ├── controller.py
│   │   ├── dto.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   └── ui/
│   │       ├── report_page.py
│   │       ├── date_range_selector_widget.py
│   │       ├── revenue_timeseries_widget.py
│   │       ├── sales_summary_widget.py
│   │       ├── top_products_table_widget.py
│   │       └── page.py
│   ├── settings/
│   │   ├── service.py
│   │   └── ui/
│   │       └── page.py
│   ├── diagnostics/
│   │   └── service.py
│   └── update/
│       ├── service.py
│       └── ui/
│           └── update_dialog.py
├── shared/
│   ├── formatting/
│   │   ├── dates.py
│   │   ├── money.py
│   │   ├── quantity.py
│   │   └── text.py
│   ├── styles/
│   │   ├── palette.py
│   │   └── theme.py
│   └── widgets/
│       ├── autocomplete_line_edit.py
│       ├── common_dialogs.py
│       ├── message_box.py
│       ├── numeric_inputs.py
│       ├── table_helpers.py
│       ├── transaction_datetime_dialog.py
│       └── ui_scale.py
├── shell/
│   ├── app_window.py
│   ├── bootstrap.py
│   ├── history_page.py
│   └── navigation.py
├── tests/
│   ├── test_inventory_service.py
│   ├── test_sales_service.py
│   ├── test_customer_service.py
│   ├── test_return_service.py
│   ├── test_reporting_service.py
│   ├── test_update_service.py
│   ├── test_diagnostics_service.py
│   ├── test_schema_invariants.py
│   ├── test_smoke.py
│   └── test_ui_scale_settings.py
├── installer/
│   └── QuanLyHangHoa.iss
├── README.md
└── main.py
```

Ghi chú:

- Cấu trúc trên tập trung vào thư mục và file chính của ứng dụng.
- Repo hiện còn có `docs/`, `data/`, `build/`, `dist/`, `.omx/`, `.venv/`, `__pycache__/` và một số thư mục tạm trong `tests/`, nhưng đây không phải phần lõi của runtime/business flow nên không bung chi tiết trong tree chính.

### 3.2 Mô tả vai trò từng folder

- `core/`
  → chứa hạ tầng nền tảng như config, DB bootstrap, path runtime, logging, enum, exception và version.
- `modules/`
  → chứa toàn bộ business domain theo từng mảng nghiệp vụ tách riêng.
- `modules/sales`, `modules/inventory`, `modules/customer`, `modules/returns`, `modules/reporting`
  → các domain chính, đa số đi theo cấu trúc `controller.py` + `service.py` + `repository.py` + `ui/`.
- `modules/settings`
  → quản lý preference ứng dụng như UI scale và màn hình cài đặt.
- `modules/diagnostics`
  → gom logic xuất gói chẩn đoán/log để hỗ trợ vận hành.
- `modules/update`
  → xử lý check manifest, tải installer và handoff sang flow cập nhật.
- `shared/`
  → reusable components dùng chung: formatter, theme, widget helper, table helper, input helper.
- `shell/`
  → entrypoint application shell: bootstrap app, main window, navigation tab, history page.
- `tests/`
  → test cho service, schema invariant, smoke flow, UI scale và một số tương tác UI/domain quan trọng.
- `installer/`
  → script Inno Setup để đóng gói installer Windows.
- `README.md`
  → tài liệu chạy app, build PyInstaller, build installer và flow update.
- `main.py`
  → entrypoint tối giản, tạo `QApplication` rồi gọi `shell.bootstrap.bootstrap_application()`.

### 3.3 Mô tả flow dependency

Luồng chuẩn:

`UI → Controller → Service → Repository → DB`

Giải thích ngắn:

- `UI`
  → nhận input người dùng, render dữ liệu, phát signal và hiển thị dialog/widget.
- `Controller`
  → lớp điều phối giữa UI và nghiệp vụ; chuyển dữ liệu từ UI sang lời gọi service phù hợp, đồng thời gom các read model cho màn hình.
- `Service`
  → nơi đặt business rule, validation, orchestration transaction, và phối hợp nhiều repository/domain khác nhau.
- `Repository`
  → lớp truy cập dữ liệu với SQLAlchemy; thực hiện query, load aggregate và persist entity.
- `DB`
  → SQLite local, được khởi tạo qua `core/db.py`, lưu dữ liệu runtime ở AppData.

Ghi chú thêm:

- Không phải module nào cũng cần đủ mọi layer. Ví dụ `settings`, `diagnostics`, `update` đi theo flow nhẹ hơn, chủ yếu `UI/Window → Service`.
- `shell/bootstrap.py` là lớp ghép hệ thống: load settings, apply theme, init DB, đăng ký module page và khởi tạo `AppWindow`.

### 3.4 Ghi chú thiết kế

- Module hóa theo domain
  → mỗi domain nghiệp vụ được tách thư mục riêng để cô lập model, repository, service, UI; dễ mở rộng và giảm việc sửa chéo.
- Separation of concerns
  → UI không ôm business logic; service không phụ thuộc PyQt; repository tập trung vào persistence/query; shell chỉ làm composition.
- Dùng SQLite local
  → phù hợp mô hình desktop offline-first, triển khai đơn giản, không cần server riêng, backup/copy dữ liệu dễ và đủ tốt cho bài toán đơn máy hoặc cửa hàng nhỏ.
- Tách AppData khỏi thư mục cài đặt
  → DB, log, export, backup, temp được đưa về `%LOCALAPPDATA%\<AppName>\...` để không mất dữ liệu khi update/uninstall binary, đồng thời tránh ghi dữ liệu mutable vào `Program Files` hoặc thư mục source.
