# Tổng quan kiến trúc dự án `chamcong`

## 1. Project Overview

- **Tên app:** `chamcong`.
- **Mục đích:** ứng dụng desktop nội bộ để chấm công và tính tiền cho các công việc phụ/công việc phát sinh của nhân viên theo từng ngày và từng kỳ công 10 ngày.
- **Nền tảng mục tiêu:** desktop Windows, chạy cục bộ cho chủ cơ sở hoặc người quản trị.
- **Giả định vận hành:** offline/local-first. Dữ liệu lưu trong file SQLite cục bộ `chamcong.db`, không phụ thuộc server.
- **Tech stack hiện tại:**
  - Python.
  - PyQt6 cho giao diện desktop.
  - SQLAlchemy ORM cho model và truy vấn dữ liệu.
  - SQLite làm database local.
- **Trạng thái hiện tại:** app đã chạy được các luồng chính: quản lý nhân viên, chấm công theo ngày, lưu nháp/chốt ngày, đánh dấu nghỉ, tính tiền snapshot, và xem báo cáo từ dữ liệu thật trong DB. Tuy nhiên kiến trúc vẫn còn monolithic, nhiều logic vẫn nằm trong `main_window.py`.

## 2. Business Context

- Ứng dụng dùng cho **chấm công/tính tiền nội bộ**, không phải hệ thống self-service cho công nhân.
- Người dùng chính là **chủ cơ sở/admin**, nhập công thay cho nhân viên.
- App không tập trung vào việc chính hằng ngày của công nhân. App theo dõi các khoản **làm thêm/công phụ/công đặc biệt có trả tiền riêng**.
- Có hai tổ nghiệp vụ:
  - **Tổ thổi**: nhập các loại việc phát sinh như thừa máy, máy nhỏ, máy to, phụ cắt, phụ găng.
  - **Tổ cắt**: nhập số lượng theo từng loại bao/hàng.
- Báo cáo và thanh toán dựa trên **kỳ công 10 ngày**:
  - Ngày 1-10.
  - Ngày 11-20.
  - Ngày 21 đến cuối tháng.

## 3. Core Business Rules

- Mỗi nhân viên thuộc đúng một tổ qua enum `Team`:
  - `Team.BLOW` với giá trị DB `"blow"`.
  - `Team.CUT` với giá trị DB `"cut"`.
- Mỗi nhân viên có ID nội bộ `Employee.id`. ID này dùng cho quan hệ DB và selection trong table, nhưng không hiển thị như định danh nghiệp vụ trong UI.
- Tên hiển thị `Employee.name` là định danh người dùng nhìn thấy trong app.
- Nhân viên có trạng thái `Employee.is_active`:
  - `True`: đang sử dụng, hiện trong danh sách chấm công.
  - `False`: ngưng sử dụng, vẫn có thể xuất hiện trong báo cáo nếu có lịch sử trong kỳ.
- Không được tạo/trùng tên nhân viên. Logic kiểm tra trùng dựa trên `Employee.name` sau khi `strip()`.
- Khi xóa nhân viên:
  - Nếu chưa có `DailyRecord`, app hard delete khỏi DB.
  - Nếu đã có lịch sử chấm công, app không xóa cứng mà chuyển `is_active = False`.
- Chấm công được nhập/sửa cho bất kỳ ngày đang chọn trong `QDateEdit`.
- Ngày cũ có thể mở lại và chỉnh sửa. Trong UI/service hiện tại, nếu record đang `DONE`, app đổi tạm về `DRAFT`, xóa log cũ, rồi ghi lại dữ liệu mới.
- **“Chốt ngày” hiện tại không phải khóa vĩnh viễn.** Nó chỉ lưu record với `DailyRecord.status = DONE`.
- **“Lưu nháp”** lưu record với `DailyRecord.status = DRAFT`.
- Nghỉ được biểu diễn rõ bằng `DailyRecord.is_absent = True`.
- Ngày nghỉ:
  - Không có `WorkLog`.
  - Không có `CutLog`.
  - `DailyRecord.total_amount_snapshot = 0`.
  - UI hiển thị trạng thái “Nghỉ”.
- Trạng thái hiển thị chính:
  - “Chưa chấm”: không có `DailyRecord` cho nhân viên/ngày đó.
  - “Nháp”: có record `DRAFT`, không nghỉ.
  - “Đã lưu”: có record `DONE`, không nghỉ.
  - “Nghỉ”: có record với `is_absent = True`.

## 4. Payroll Period Logic

- Kỳ công dựa trên chu kỳ 10 ngày trong tháng:
  - Ngày 1-10: `start_date = YYYY-MM-01`, `end_date = YYYY-MM-10`.
  - Ngày 11-20: `start_date = YYYY-MM-11`, `end_date = YYYY-MM-20`.
  - Ngày 21-cuối tháng: `start_date = YYYY-MM-21`, `end_date = ngày cuối tháng`.
- `MainWindow.ensure_period_for_date()` và `attendance_service.ensure_period_for_date()` tự tạo `Period` nếu ngày được chọn chưa thuộc kỳ nào.
- `services.create_period()` không cho tạo kỳ chồng lấn, có `UniqueConstraint(start_date, end_date)`.
- Dropdown kỳ báo cáo được load từ bảng `periods` qua `load_report_periods_from_db()`.
- Label kỳ có dạng “Kì dd/mm/yyyy - dd/mm/yyyy” và được parse lại bằng regex trong `_parse_report_period_bounds()`.
- Khi render báo cáo, app chỉ hiển thị các ngày từ đầu kỳ đến `min(end_date, date.today())`. Các ngày tương lai trong kỳ bị ẩn khỏi report UI.

## 5. Database / Models

### `Employee`

- **Bảng:** `employees`.
- **Mục đích:** lưu nhân viên tham gia chấm công phụ.
- **Field quan trọng:**
  - `id`: khóa chính nội bộ.
  - `name`: tên hiển thị, unique, không null.
  - `team`: enum `Team`, xác định tổ `BLOW` hoặc `CUT`.
  - `is_active`: trạng thái đang dùng/ngưng dùng.
- **Quan hệ:**
  - `shift_periods`: nhiều `EmployeeShiftPeriod`.
  - `daily_records`: nhiều `DailyRecord`.

### `Period`

- **Bảng:** `periods`.
- **Mục đích:** đại diện kỳ công.
- **Field quan trọng:**
  - `id`: khóa chính.
  - `start_date`, `end_date`: khoảng ngày của kỳ.
  - `locked`: cờ khóa kỳ, hiện model/service có kiểm tra nhưng UI chưa triển khai luồng khóa kỳ đầy đủ.
  - `created_at`: thời điểm tạo.
- **Constraint:**
  - `start_date <= end_date`.
  - Unique theo cặp `start_date`, `end_date`.
- **Quan hệ:**
  - `employee_shift_periods`.
  - `daily_records`.

### `EmployeeShiftPeriod`

- **Bảng:** `employee_shift_periods`.
- **Mục đích:** gán ca cho nhân viên trong một kỳ.
- **Field quan trọng:**
  - `employee_id`.
  - `period_id`.
  - `shift`: enum `Shift.DAY` hoặc `Shift.NIGHT`.
- **Quan hệ:**
  - Nhiều bản ghi thuộc một `Employee`.
  - Nhiều bản ghi thuộc một `Period`.
- **Ghi chú:** UI hiện chỉ đọc để hiển thị “Ca ngày”/“Ca đêm” hoặc “-”; chưa có UI quản lý ca hoàn chỉnh.

### `DailyRecord`

- **Bảng:** `daily_records`.
- **Mục đích:** record chấm công của một nhân viên trong một ngày.
- **Field quan trọng:**
  - `employee_id`: nhân viên.
  - `date`: ngày chấm công.
  - `period_id`: kỳ công chứa ngày đó.
  - `is_absent`: nghỉ hay không.
  - `status`: enum `DailyRecordStatus.DRAFT` hoặc `DailyRecordStatus.DONE`.
  - `total_amount_snapshot`: tổng tiền đã snapshot tại thời điểm lưu.
- **Constraint:**
  - Unique theo `employee_id`, `date`.
  - `total_amount_snapshot >= 0`.
- **Quan hệ:**
  - Một `DailyRecord` thuộc một `Employee`.
  - Một `DailyRecord` thuộc một `Period`.
  - Có nhiều `WorkLog` cho tổ thổi.
  - Có nhiều `CutLog` cho tổ cắt.

### `WorkType`

- **Bảng:** `work_types`.
- **Mục đích:** cấu hình loại việc của tổ thổi.
- **Field quan trọng:**
  - `name`: tên việc.
  - `team`: hiện bị ràng buộc là `Team.BLOW`.
  - `input_type`: enum `WorkInputType.TICK` hoặc `WorkInputType.QUANTITY`.
  - `unit_price`: đơn giá hiện hành.
  - `config_json`: chỗ mở rộng cấu hình, hiện chưa dùng đáng kể.
  - `is_active`: bật/tắt loại việc.
- **Constraint:**
  - `team = 'blow'`.
  - `unit_price >= 0`.
  - Unique theo `team`, `name`.
- **Quan hệ:** một `WorkType` có nhiều `WorkLog`.

### `WorkLog`

- **Bảng:** `work_logs`.
- **Mục đích:** dòng việc tổ thổi cho một `DailyRecord`.
- **Field quan trọng:**
  - `daily_record_id`.
  - `work_type_id`.
  - `quantity`: số lượng, với việc tick thì lưu 1.
  - `unit_price_snapshot`: đơn giá chụp lại khi lưu.
  - `amount_snapshot`: thành tiền chụp lại khi lưu.
- **Constraint:**
  - `quantity >= 1`.
  - Unique theo `daily_record_id`, `work_type_id`.
  - snapshot không âm.
- **Quan hệ:** thuộc `DailyRecord`, tham chiếu `WorkType`.

### `BagType`

- **Bảng:** `bag_types`.
- **Mục đích:** cấu hình loại bao/hàng cho tổ cắt.
- **Field quan trọng:**
  - `name`: tên loại bao, unique.
  - `unit_price`: đơn giá.
  - `is_active`: bật/tắt loại bao.
- **Constraint:** `unit_price >= 0`.
- **Quan hệ:** một `BagType` có nhiều `CutLog`.

### `CutLog`

- **Bảng:** `cut_logs`.
- **Mục đích:** dòng sản lượng tổ cắt cho một `DailyRecord`.
- **Field quan trọng:**
  - `daily_record_id`.
  - `bag_type_id`.
  - `quantity`: số lượng.
  - `unit_price_snapshot`: đơn giá chụp lại khi lưu.
  - `amount_snapshot`: thành tiền chụp lại khi lưu.
- **Constraint:**
  - Unique theo `daily_record_id`, `bag_type_id`.
  - `quantity >= 0`.
  - snapshot không âm.
- **Quan hệ:** thuộc `DailyRecord`, tham chiếu `BagType`.

### Enums

- `Team`:
  - `BLOW = "blow"`.
  - `CUT = "cut"`.
- `Shift`:
  - `DAY = "day"`.
  - `NIGHT = "night"`.
- `DailyRecordStatus`:
  - `DRAFT = "draft"`.
  - `DONE = "done"`.
- `WorkInputType`:
  - `TICK = "tick"`.
  - `QUANTITY = "quantity"`.

## 6. Work Logic: Tổ Thổi

- Tổ thổi dùng bảng `WorkType` để cấu hình loại việc.
- Dữ liệu seed mặc định hiện có:
  - `Thừa máy` -> mã báo cáo `TM`, kiểu `QUANTITY`, đơn giá 80,000.
  - `Máy nhỏ` -> `MN`, kiểu `QUANTITY`, đơn giá 30,000.
  - `Máy to` -> `MT`, kiểu `QUANTITY`, đơn giá 40,000.
  - `Phụ cắt` -> `PC`, kiểu `QUANTITY`, đơn giá 50,000.
  - `Phụ găng 1 máy` -> `PG1`, kiểu `TICK`, đơn giá 30,000.
  - `Phụ găng 2 máy` -> `PG2`, kiểu `TICK`, đơn giá 50,000.
- Với việc `QUANTITY`, người dùng tick việc rồi nhập số lượng bằng `QSpinBox`; service yêu cầu số lượng lớn hơn 0.
- Với việc `TICK`, người dùng chỉ tick checkbox; service lưu `quantity = 1`.
- `PG1` và `PG2` loại trừ nhau trong cùng một ngày:
  - UI tự bỏ tick lựa chọn còn lại khi chọn một mức phụ găng.
  - Service cũng kiểm tra để không thể lưu cả hai.
- Một ngày chỉ có `PG1` hoặc chỉ có `PG2` vẫn hợp lệ vì đó là một `WorkLog` có tiền.
- Khi lưu, app xóa log cũ của record rồi ghi log mới. Mỗi log lưu `unit_price_snapshot` và `amount_snapshot`, nên báo cáo không phụ thuộc vào đơn giá hiện hành sau này.
- Tổng ngày lưu vào `DailyRecord.total_amount_snapshot`.

## 7. Work Logic: Tổ Cắt

- Tổ cắt dùng bảng `BagType` để cấu hình loại bao/hàng.
- Dữ liệu seed mặc định hiện có:
  - `Bao 25kg`, đơn giá 3,500, đang dùng.
  - `Bao 50kg`, đơn giá 4,200, đang dùng.
  - `Bao PP`, đơn giá 3,900, mặc định ngưng dùng.
- UI nhập tổ cắt bằng nhiều dòng trong `cut_table`.
- Mỗi dòng gồm:
  - Combo chọn `BagType`.
  - `QSpinBox` nhập `quantity`.
- Một nhân viên có thể làm nhiều loại bao trong cùng một ngày.
- `collect_cut_form_data()` chỉ lấy các dòng có `quantity > 0`.
- Service `add_cut_work()` tính `amount_snapshot = quantity * unit_price` và lưu `unit_price_snapshot`.
- Trong DB có unique theo `daily_record_id`, `bag_type_id`, vì vậy mỗi loại bao chỉ nên có một dòng kết quả sau khi lưu.

## 8. Attendance UI

- Tab chấm công dùng `QDateEdit` để chọn ngày.
- Panel trái là table nhân viên đang active, gồm:
  - Tên.
  - Tổ.
  - Trạng thái của ngày đang chọn.
- Panel phải hiển thị thông tin record đang chọn:
  - Nhân viên.
  - Tổ.
  - Ngày.
  - Ca trong kỳ.
  - Trạng thái record.
- Form nhập liệu đổi theo tổ:
  - Nhân viên `Tổ thổi` hiển thị group nhập việc thổi.
  - Nhân viên `Tổ cắt` hiển thị group nhập dòng bao/hàng.
- Checkbox nghỉ `absent_checkbox`:
  - Khi tick, disable các group nhập việc.
  - Khi lưu, xóa toàn bộ `WorkLog`/`CutLog`, set tổng tiền 0.
- Nút **Lưu nháp** gọi `_persist_current_attendance(finalize=False)` và lưu `status = DRAFT`.
- Nút **Chốt ngày** gọi `_persist_current_attendance(finalize=True)` và lưu `status = DONE`.
- Cả “Lưu nháp” và “Chốt ngày” đều persist DB thật, commit session, refresh lại danh sách trạng thái và báo cáo.
- Nút **Copy hôm qua** hiện chỉ là placeholder.
- Nút **Làm mới form** reload form theo record đang chọn.
- Trạng thái UI hiện dùng:
  - “Chưa chấm”.
  - “Nháp”.
  - “Đã lưu”.
  - “Nghỉ”.

## 9. Employee Management UI

- Tab “Danh sách nhân viên” hiển thị table nhân viên gồm:
  - Tên.
  - Tổ.
  - Trạng thái.
- Có ô tìm kiếm theo tên nhân viên.
- Dialog `EmployeeDialog` dùng cho cả thêm và sửa:
  - Nhập tên.
  - Chọn tổ.
  - Checkbox đang sử dụng.
- Thêm nhân viên:
  - Trim tên.
  - Không cho tên rỗng.
  - Không cho trùng `Employee.name`.
  - Insert `Employee`.
- Sửa nhân viên:
  - Cho đổi tên, tổ, trạng thái active.
  - Không cho trùng tên với nhân viên khác.
- Xóa nhân viên:
  - Có confirmation dialog.
  - Nếu nhân viên chưa có `DailyRecord`, xóa cứng.
  - Nếu đã có lịch sử, chuyển `is_active = False` và báo cho người dùng.
- Attendance tab chỉ hiển thị nhân viên active, nhưng report vẫn có logic đưa nhân viên inactive vào nếu có record trong kỳ được chọn.

## 10. Report UI

- Báo cáo hiện đã đọc dữ liệu thật từ DB, không còn phụ thuộc mock data cho UI chính.
- Tab báo cáo có:
  - Combo chọn tổ: “Tổ thổi” hoặc “Tổ cắt”.
  - Combo chọn kỳ từ bảng `periods`.
  - Nút “Xem báo cáo”.
  - Nút “Xuất Excel” placeholder.
  - Nút “In bảng công” placeholder.
- Báo cáo được trình bày kiểu bảng giấy:
  - Cột đầu tiên là ngày (`dd/mm`).
  - Mỗi nhân viên là một group header ở hàng header trên.
  - Dưới mỗi nhân viên có các cột con động.
  - Mỗi group nhân viên luôn có cột cuối `Tổng`.
  - Cột ngoài cùng bên phải là `Tổng tiền cả ngày`.
- Cột con được ẩn theo từng nhân viên nếu nhân viên đó không dùng loại việc/loại bao trong phần ngày đang hiển thị của kỳ.
  - Ví dụ tổ thổi: nhân viên nào chỉ có `MN` thì group của người đó chỉ có `MN` và `Tổng`.
  - Ví dụ tổ cắt: nhân viên nào có `25kg`, `50kg`, `PP` thì chỉ các cột đó hiện cho người đó.
- Report chỉ render đến ngày hiện tại. Nếu kỳ tương lai hoàn toàn, số dòng có thể là 0 nhưng group nhân viên active vẫn tồn tại.
- Vùng summary hiển thị:
  - Tổng số nhân viên trong report.
  - Tổng số ngày công có tiền (`amount > 0`, tính theo từng employee-day).
  - Tổng số tiền toàn kỳ hiển thị.
- Sau khi lưu chấm công, `_persist_current_attendance()` gọi `refresh_report_table()`, vì vậy báo cáo cập nhật ngay.
- Report bao gồm:
  - Nhân viên active của tổ được chọn.
  - Nhân viên inactive nếu có `DailyRecord` trong kỳ được chọn.

## 11. Report Data Pipeline

- UI lấy `team_label` từ combo và chuyển thành key bằng `_report_team_key()`:
  - Label chứa “cắt” -> `"cut"`.
  - Ngược lại -> `"blow"`.
- Label kỳ được parse bằng `_parse_report_period_bounds()` để lấy `start_date`, `end_date`.
- `visible_end_date = min(end_date, date.today())`.
- Danh sách ngày hiển thị được tạo bằng `_daterange(start_date, visible_end_date)`.
- Query lấy danh sách nhân viên:
  - Lọc theo `Employee.team`.
  - Nếu có nhân viên có record trong kỳ, query bao gồm employee active hoặc employee có record.
  - Nếu không có record nào, chỉ lấy employee active.
- Query `DailyRecord` theo:
  - `employee_id` trong danh sách nhân viên.
  - `date >= start_date`.
  - `date <= visible_end_date`.
- Query eager-load:
  - `DailyRecord.work_logs -> WorkLog.work_type`.
  - `DailyRecord.cut_logs -> CutLog.bag_type`.
- Với tổ thổi:
  - `_report_work_values_for_record()` chuyển `WorkLog.work_type.name` thành mã `TM`, `MN`, `MT`, `PC`, `PG1`, `PG2`.
  - Tick work hiển thị `"1"`.
  - Quantity work hiển thị số lượng.
- Với tổ cắt:
  - `_abbreviate_cut_report_label()` rút gọn `BagType.name` thành nhãn như `25kg`, `50kg`, `PP`.
  - Giá trị cell là số lượng.
- Amount dùng snapshot:
  - `WorkLog.amount_snapshot`.
  - `CutLog.amount_snapshot`.
  - Nếu nghỉ hoặc không có record thì amount = 0.
- Render model là dict gồm:
  - `team_key`.
  - `employee_count`.
  - `employee_groups`.
  - `columns`.
  - `rows`.
  - `total_amount`.
  - `total_workdays`.
- UI consume render model để:
  - Set số dòng/cột `QTableWidget`.
  - Render cell.
  - Tạo header hai tầng bằng QLabel trong `report_header_scroll`.
  - Đồng bộ horizontal scroll giữa table và header.

## 12. Settings UI

- Tab cài đặt hiện hiển thị hai bảng:
  - Cấu hình việc tổ thổi từ `WorkType`.
  - Cấu hình loại bao tổ cắt từ `BagType`.
- Bảng tổ thổi hiển thị:
  - Tên việc.
  - Kiểu nhập.
  - Đơn giá.
  - Trạng thái.
- Bảng tổ cắt hiển thị:
  - Loại bao.
  - Đơn giá.
  - Trạng thái.
- Các bảng đang `NoEditTriggers`, tức là gần như read-only.
- CRUD/config editing cho đơn giá, thêm loại việc mới, thêm loại bao mới, bật/tắt cấu hình chưa hoàn thiện.

## 13. Current Known Limitations / TODO

- Settings CRUD chưa hoàn thiện.
- Xuất Excel đang là placeholder.
- In báo cáo đang là placeholder.
- Copy hôm qua đang là placeholder.
- Kiến trúc vẫn còn quá nhiều logic trong `main_window.py`.
- Report service nên được extract sạch hơn. Hiện có `report_service.py` với dataclass/render helpers và mock helpers, nhưng UI chính vẫn build report thật ngay trong `MainWindow`.
- Employee service và attendance service đã bắt đầu được tách (`employee_service.py`, `attendance_service.py`) nhưng `main_window.py` vẫn còn bản logic tương tự trực tiếp.
- Unicode/encoding cần giữ UTF-8 sạch. Một số text trong source hiện có dấu hiệu mojibake khi đọc bằng môi trường shell, cần tránh làm bẩn thêm chuỗi tiếng Việt.
- Monthly KPI bonus cho Tổ thổi chưa được tích hợp UI/report. Trong `services.calculate_kpi()` có logic tính KPI theo số ngày `DONE` có tiền, nhưng chưa thành feature hoàn chỉnh trong app.
- `Period.locked` đã tồn tại ở model/service nhưng UI chưa có luồng khóa/mở khóa kỳ.
- `EmployeeShiftPeriod` có model và service `assign_shift()` nhưng UI quản lý ca chưa hoàn chỉnh.

## 14. Architecture Notes

- App hiện **functional nhưng monolithic**.
- `main_window.py` vẫn chứa cùng lúc:
  - Khởi tạo DB engine/session.
  - Seed dữ liệu mặc định.
  - UI construction.
  - DB queries.
  - Business orchestration khi lưu chấm công.
  - Report building.
  - Employee CRUD.
  - Settings table rendering.
- Đã có bước tách đầu tiên:
  - `services.py`: domain/service functions nền tảng.
  - `attendance_service.py`: wrapper lưu chấm công theo payload.
  - `employee_service.py`: CRUD nhân viên dạng service.
  - `report_service.py`: dataclass/render helpers, nhưng chưa phải nguồn chính của report UI.
- Mục tiêu kiến trúc tiếp theo nên là modular monolith:
  - `core/`.
  - `shared/`.
  - `shell/`.
  - `modules/attendance/`.
- Module hiện tại nên được chuyển thành `modules/attendance` khi merge vào app lớn.

## 15. Suggested Future Modular Structure

Target structure:

```text
modules/attendance/
- models.py
- repository.py
- service.py
- report_service.py
- validators.py
- dto.py
- mappers.py
- ui/tab.py
- ui/dialogs.py
- ui/forms.py
- ui/widgets.py
```

- `models.py`:
  - Chứa SQLAlchemy models và enums: `Employee`, `Period`, `DailyRecord`, `WorkType`, `WorkLog`, `BagType`, `CutLog`, `EmployeeShiftPeriod`, `Team`, `Shift`, `DailyRecordStatus`, `WorkInputType`.
- `repository.py`:
  - Chứa truy vấn DB thuần: load employee, load period, load records by date/range, load work types, load bag types.
  - Không chứa PyQt.
- `service.py`:
  - Chứa nghiệp vụ chấm công: tạo period, get/create daily record, lưu draft/done, set absent, add blow/cut work, delete/deactivate employee.
  - Không import PyQt.
- `report_service.py`:
  - Chứa toàn bộ pipeline build report render model từ DB.
  - Nhận session, team, period, today.
  - Trả DTO/render model thuần Python để UI render.
- `validators.py`:
  - Validate tên nhân viên, duplicate name, payload tổ thổi, payload tổ cắt, glove exclusivity, quantity > 0.
- `dto.py`:
  - Dataclass cho input/output: `AttendanceSavePayload`, `AttendanceSaveResult`, `EmployeeDTO`, `ReportRenderModel`, `ReportColumn`, `ReportRow`, `ReportEmployeeGroup`.
- `mappers.py`:
  - Map enum <-> label UI.
  - Map `WorkType.name` -> code report (`TM`, `MN`, `MT`, `PC`, `PG1`, `PG2`).
  - Map `BagType.name` -> label ngắn (`25kg`, `50kg`, `PP`).
- `ui/tab.py`:
  - Expose widget chính `AttendanceTab`.
  - Compose các tab con hoặc panel chính.
- `ui/dialogs.py`:
  - `EmployeeDialog`, dialog cấu hình work/bag type sau này.
- `ui/forms.py`:
  - Form nhập tổ thổi, form nhập tổ cắt, form filter report.
- `ui/widgets.py`:
  - Custom report table/header widget, reusable table helpers.

## 16. Merge Guidance

- Khi merge vào app desktop lớn, giữ DB models attendance nằm dưới attendance module, tránh trộn vào module khác.
- Module nên expose một widget cấp cao như `AttendanceTab` hoặc `AttendanceModuleWidget`.
- Shell app chỉ nên import và mount widget đó vào main window/tab container.
- Sử dụng shared DB session/engine từ `core/db.py`; không để attendance tự tạo engine hardcoded từ `chamcong.db`.
- Services phải PyQt-free để test dễ và tái sử dụng được.
- UI chỉ làm nhiệm vụ:
  - Thu input.
  - Gọi service.
  - Render DTO/result.
  - Hiển thị lỗi/notification.
- Tránh dependency chéo giữa attendance và các module khác. Nếu cần dữ liệu dùng chung, đưa contract vào `shared/` hoặc service boundary rõ ràng.
- Không để module attendance import shell app. Chiều phụ thuộc nên là shell import module.

## 17. Files to Inspect

- `main_window.py`
  - File lớn nhất hiện tại.
  - Chứa `MainWindow`, `EmployeeDialog`, setup database, seed dữ liệu, toàn bộ UI tabs, employee CRUD, attendance save flow, report render thật từ DB, settings table.
- `models.py`
  - Chứa SQLAlchemy `Base`, enums và toàn bộ models DB.
  - Là nguồn chính để hiểu schema và relationships.
- `services.py`
  - Chứa service/domain functions nền tảng: tạo kỳ, gán ca, get/create daily record, add blow/cut work, finalize, set absent, tính period total, tính KPI.
  - Có exceptions: `ServiceError`, `NotFoundError`, `ValidationError`, `LockedPeriodError`.
- `attendance_service.py`
  - Chứa `AttendanceSaveResult`.
  - Chứa helper đảm bảo period theo ngày, lấy status, và `save_attendance()` theo payload.
  - Có logic cho phép chỉnh lại record `DONE` bằng cách đưa về `DRAFT` rồi ghi lại.
- `employee_service.py`
  - Chứa service CRUD nhân viên: list, create, update, delete-or-deactivate.
  - Có `EmployeeDeleteResult`.
- `report_service.py`
  - Chứa dataclass render model và helper build report, nhưng phần nhiều hiện vẫn phục vụ/mock hoặc chưa được `main_window.py` dùng làm pipeline chính.
  - Nên là điểm xuất phát để extract report thật khỏi `MainWindow`.
- `tests/test_attendance_workflow.py`
  - Test selected date, trạng thái theo ngày, chỉnh lại record đã lưu, và absent round-trip.
- `tests/test_employee_management.py`
  - Test thêm/sửa/xóa nhân viên và deactivate khi có history.
- `tests/test_report_ui.py`
  - Test report thật từ DB, ẩn ngày tương lai, dynamic columns, inactive employee with history.

## 18. Final Implementation Summary

- Hiện app đã làm được:
  - Khởi tạo SQLite local và seed dữ liệu mặc định.
  - Quản lý nhân viên với active/inactive và duplicate name prevention.
  - Chấm công theo ngày cho Tổ thổi và Tổ cắt.
  - Lưu nháp/chốt ngày vào DB.
  - Mở lại ngày cũ để sửa.
  - Đánh dấu nghỉ bằng `is_absent`, clear logs và set tổng 0.
  - Tính tiền bằng snapshot tại từng log.
  - Tạo kỳ công 10 ngày tự động.
  - Báo cáo đọc dữ liệu thật từ DB, group theo nhân viên, cột con động, ẩn ngày tương lai, tính summary.
- Còn pending:
  - CRUD cấu hình work type/bag type.
  - Xuất Excel.
  - In bảng công.
  - Copy hôm qua.
  - UI quản lý ca/kỳ/khóa kỳ.
  - KPI tháng cho Tổ thổi.
- Refactor tiếp theo nên làm:
  - Chuyển report pipeline khỏi `main_window.py` sang `report_service.py`.
  - Chuyển employee CRUD UI sang gọi `employee_service.py`.
  - Chuyển attendance save UI sang gọi `attendance_service.py`.
  - Tách UI thành module `modules/attendance/ui`.
  - Tách DB/session ra `core/db.py` khi merge vào app lớn.
