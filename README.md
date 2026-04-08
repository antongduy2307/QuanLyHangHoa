# Desktop App Skeleton

Skeleton desktop app Python theo kien truc modular monolith, dung `PyQt6`, `SQLAlchemy 2.x`, `SQLite`, dinh huong `offline-first`.

## Kien truc

- `core/`: cau hinh dung chung, duong dan, DB, exceptions, logging.
- `shared/`: formatter, widget helper, style dung lai nhieu noi.
- `shell/`: bootstrap app, main window, navigation.
- `modules/`: tung domain tach `models`, `repository`, `service`, `dto`, `validators`, `mappers`, `ui`.

Nguyen tac chinh:

- UI khong chua business logic.
- `service.py` khong phu thuoc PyQt.
- `repository.py` chi xu ly truy xuat du lieu.
- Module co contract doc lap va co the gan vao shell qua registry.

## Module hien co

- `inventory`
- `sales`
- `returns`
- `customer`
- `reporting`
- `settings`

Shell mac dinh dang gan cac tab: `Hang hoa`, `Ban hang`, `Khach hang`, `Bao cao`.

## Cach chay

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Lan chay dau tien ung dung se tu tao thu muc du lieu runtime va SQLite DB trong `%LOCALAPPDATA%\\<AppName>\\app.db` tren Windows. Neu moi truong khong co `LOCALAPPDATA`, app se fallback an toan ve `data/app.db` trong project.

## Build Windows (PyInstaller)

Build hien tai uu tien `onedir` de de debug va on dinh hon cho V1.

1. Cai dependency build:

```bash
pip install -r requirements.txt
```

2. Chay build:

```bash
pyinstaller --noconfirm desktop_app.spec
```

3. Output sau build:

- thu muc app build: `dist\QuanLyHangHoa\`
- file chay chinh: `dist\QuanLyHangHoa\QuanLyHangHoa.exe`

4. Chay thu ban build:

```bash
dist\QuanLyHangHoa\QuanLyHangHoa.exe
```

Ban build van doc local database tu `%LOCALAPPDATA%\\<AppName>\\app.db`, khong phu thuoc vao working directory cua source project.

## Ghi chu

- Day la skeleton sach de bat dau phat trien, chua trien khai nghiep vu sau.
- Khi mo rong, giu nguyen nguyen tac: business rules nam o `service`, UI chi goi service va hien thi ket qua.

## Schema Notes

- Xem `docs/schema_invariants.md` de biet rule nao dang duoc enforce o DB, rule nao chi la helper muc model, va rule nao duoc defer sang service layer.
- Ton kho chuan cho `BAO_KG` chi luu theo bao decimal. KG la don vi quy doi/bao cao, khong luu ton kho rieng.
- Neu truoc do ban dang dung DB cu trong thu muc project, app se khong tu dong copy sang AppData. Neu muon giu du lieu cu, hay copy file DB cu thu cong sang vi tri moi hoac reset DB dev sach.
