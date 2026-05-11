# MERGE_NOTES - chamcong attendance module

## Entrypoint hiện tại

- Entrypoint hiện tại nằm trong `main_window.py`.
- Hàm chạy app là `main()` ở cuối file.
- Class UI chính là `MainWindow(QMainWindow)`.
- App hiện tự tạo SQLite engine bằng:
  - DB path: `Path(__file__).resolve().with_name("chamcong.db")`.
  - URL: `sqlite:///chamcong.db`.
- Khi merge vào app chính, không nên giữ cách tự tạo engine này. Nên dùng shared session/engine từ `core/db.py` của app chính.

## File quan trọng trong gói export

- `main_window.py`
  - UI desktop PyQt6 hiện tại.
  - Chứa `EmployeeDialog`.
  - Chứa construction của các tab: danh sách nhân viên, chấm công, báo cáo, cài đặt.
  - Vẫn chứa nhiều DB query, business orchestration, seed data, report rendering.
- `models.py`
  - SQLAlchemy models và enums.
  - Là file schema chính cần port trước.
- `services.py`
  - Service/domain logic nền tảng: tạo kỳ, gán ca, tạo daily record, thêm work log/cut log, đánh dấu nghỉ, finalize, tính tổng, tính KPI.
- `attendance_service.py`
  - Service lưu chấm công theo payload.
  - Có logic auto-create period, reset record `DONE` về `DRAFT` để chỉnh lại, clear logs cũ rồi ghi logs mới.
- `employee_service.py`
  - Service CRUD nhân viên và delete-or-deactivate.
- `report_service.py`
  - Chứa render model dataclass và helper report.
  - Lưu ý: `main_window.py` hiện vẫn tự build report thật từ DB, chưa dùng hoàn toàn `report_service.py`.
- `requirements.txt`
  - Dependency Python tối thiểu.
- `summary.md`
  - Tài liệu kiến trúc/nghiệp vụ chi tiết hiện tại.
- `tests/`
  - Test hành vi quan trọng để hiểu và kiểm chứng khi port:
    - `test_attendance_workflow.py`.
    - `test_employee_management.py`.
    - `test_report_ui.py`.

## Bảng DB hiện tại

- `employees`
  - Nhân viên, tổ, trạng thái active.
- `periods`
  - Kỳ công 10 ngày, có `locked` nhưng UI khóa kỳ chưa hoàn chỉnh.
- `employee_shift_periods`
  - Gán ca theo nhân viên/kỳ, hiện chủ yếu được đọc để hiển thị.
- `daily_records`
  - Bản ghi chấm công theo nhân viên/ngày/kỳ.
  - Có `is_absent`, `status`, `total_amount_snapshot`.
- `work_types`
  - Cấu hình loại việc Tổ thổi.
- `work_logs`
  - Dòng việc Tổ thổi theo `daily_record`.
  - Có snapshot đơn giá và thành tiền.
- `bag_types`
  - Cấu hình loại bao/hàng Tổ cắt.
- `cut_logs`
  - Dòng sản lượng Tổ cắt theo `daily_record`.
  - Có snapshot đơn giá và thành tiền.

## Nghiệp vụ chính

- App dùng cho admin/chủ cơ sở nhập chấm công phụ, không phải app worker self-service.
- Có hai tổ:
  - `Team.BLOW` / Tổ thổi.
  - `Team.CUT` / Tổ cắt.
- Kỳ công chia theo 10 ngày:
  - 1-10.
  - 11-20.
  - 21-cuối tháng.
- App tự tạo `Period` cho ngày đang chọn nếu chưa có.
- Nhân viên có thể active/inactive.
- Xóa nhân viên:
  - Không có history: hard delete.
  - Có `DailyRecord`: chuyển inactive.
- Ngày nghỉ dùng `DailyRecord.is_absent = True`.
  - Nghỉ thì không có work/cut logs.
  - Tổng tiền bằng 0.
- `Lưu nháp` lưu `DailyRecordStatus.DRAFT`.
- `Chốt ngày` lưu `DailyRecordStatus.DONE`.
- `DONE` hiện không phải khóa vĩnh viễn; UI/service cho phép mở lại ngày cũ và ghi đè.
- Tổ thổi:
  - Dùng `WorkType`.
  - Quantity work nhập số lượng.
  - Tick work lưu quantity 1.
  - `Phụ găng 1 máy` và `Phụ găng 2 máy` loại trừ nhau.
- Tổ cắt:
  - Dùng `BagType`.
  - Nhập nhiều dòng bag type + quantity.
  - Một người có thể làm nhiều loại bao trong một ngày.
- Báo cáo:
  - Đọc dữ liệu thật từ DB.
  - Group cột theo nhân viên.
  - Cột con động theo loại việc/bao có dùng trong kỳ hiển thị.
  - Ẩn ngày tương lai trong kỳ.
  - Bao gồm nhân viên inactive nếu có record trong kỳ.

## Placeholder / chưa hoàn thiện

- Xuất Excel.
- In báo cáo.
- Copy hôm qua.
- CRUD cấu hình `WorkType`.
- CRUD cấu hình `BagType`.
- UI quản lý ca/kỳ/khóa kỳ.
- KPI tháng cho Tổ thổi chưa có UI/report hoàn chỉnh.
- `report_service.py` chưa phải service report thật duy nhất; logic report thật vẫn nằm nhiều trong `main_window.py`.

## Dependency

Dependency hiện tại trong `requirements.txt`:

- `PyQt6`
- `SQLAlchemy`

Khi merge vào app chính:

- Kiểm tra version PyQt6/SQLAlchemy của app chính trước khi pin version mới.
- Không thêm dependency mới nếu không cần.
- Services nên giữ thuần Python/SQLAlchemy, không phụ thuộc PyQt6.

## Những phần không nên copy nguyên xi khi merge

- Không copy `chamcong.db` thật từ repo nguồn.
- Không giữ hardcoded DB path trong `MainWindow`.
- Không bê nguyên toàn bộ `MainWindow` vào shell chính nếu app chính đã có architecture module/tab.
- Không để module attendance tự sở hữu QApplication hoặc main window của app lớn.
- Không giữ business logic trong UI lâu dài. Nên chuyển sang service/repository trước hoặc ngay sau khi port.
- Không giữ duplicated logic giữa `main_window.py`, `attendance_service.py`, `employee_service.py`.
- Không dựa vào mock report helpers trong `report_service.py` làm nguồn dữ liệu production.
- Không copy cache/runtime folders như `.venv`, `__pycache__`, `.tmp_testdata`, build/dist, logs/cache.

## Hướng merge khuyến nghị

1. Port `models.py` vào `modules/attendance/models.py`.
2. Tạo migration hoặc schema registration theo chuẩn DB của app chính.
3. Tách DB session ra khỏi UI, truyền session/session factory từ `core/db.py`.
4. Port service thuần:
   - `services.py`.
   - `attendance_service.py`.
   - `employee_service.py`.
5. Extract report thật từ `main_window.py` sang `modules/attendance/report_service.py`.
6. Tách UI thành một widget cấp module, ví dụ `AttendanceTab`.
7. Shell app chính chỉ import và mount `AttendanceTab`.
8. Chạy lại test hành vi tương đương các file trong `tests/`.
