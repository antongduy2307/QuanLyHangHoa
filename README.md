# Desktop App Skeleton

Skeleton desktop app Python theo kien truc modular monolith, dung `PyQt6`, `SQLAlchemy 2.x`, `SQLite`, dinh huong `offline-first`.

## Version hien tai

- Version app client duoc khai bao tai `core/version.py` qua `APP_VERSION`.
- URL manifest update online duoc doc tu `core/config.py` (`APP_UPDATE_MANIFEST_URL` hoac `Settings.update_manifest_url`).
- Official source repo: `https://github.com/antongduy2307/QuanLyHangHoa`.
- Official update manifest: `https://raw.githubusercontent.com/antongduy2307/QuanLyHangHoa/main/version.json`.
- Release assets: `https://github.com/antongduy2307/QuanLyHangHoa/releases`.

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

Lan chay dau tien ung dung se tu tao thu muc du lieu runtime va SQLite DB trong `%LOCALAPPDATA%\\QuanLyHangHoa\\app.db` tren Windows. Neu moi truong khong co `LOCALAPPDATA`, app se fallback an toan ve `data/app.db` trong project.

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

Ban build van doc local database tu `%LOCALAPPDATA%\\QuanLyHangHoa\\app.db`, khong phu thuoc vao working directory cua source project.

## Build Installer (Inno Setup)

Installer hien tai dong goi truc tiep output `onedir` tu PyInstaller.

1. Build PyInstaller truoc:

```bash
pyinstaller --noconfirm desktop_app.spec
```

2. Mo file script Inno Setup:

- `installer\QuanLyHangHoa.iss`

3. Compile bang Inno Setup:

- Cach GUI:
  - mo Inno Setup Compiler
  - mo `installer\QuanLyHangHoa.iss`
  - bam `Build` / `Compile`
- Cach command line neu da co `ISCC` trong PATH:

```bash
ISCC installer\QuanLyHangHoa.iss
```

4. Output installer:

- `dist\installer\QuanLyHangHoa-Setup-0.1.0.exe`

5. Chay thu installer:

- cai app vao `Program Files\QuanLyHangHoa`
- shortcut duoc tao:
  - Start Menu
  - Desktop (neu user tick task desktop icon)

## Semi-auto Update V1

App desktop da co flow semi-auto update v1:

- Sau khi mo app mot vai giay, client se check manifest update online o `APP_UPDATE_MANIFEST_URL`.
- Trong tab `Cai dat` co nut `Kiem tra cap nhat` de user kiem tra thu cong.
- Neu co ban moi, app hien dialog thong bao version hien tai, version moi, release notes, va cho user chon `Tai va cap nhat`.
- App se tai installer moi vao `%LOCALAPPDATA%\QuanLyHangHoa\temp\`.
- Sau khi tai xong, app tao launcher `.cmd` tam, dong app hien tai, roi launcher moi goi installer moi.
- V1 khong ghi de binary dang chay trong process hien tai. App chi handoff sang installer sau khi app da thoat.
- Runtime DB van nam o `%LOCALAPPDATA%\QuanLyHangHoa\app.db` va khong bi copy/move/xoa trong update flow.

Manifest JSON toi thieu:

```json
{
  "version": "0.3.0",
  "installer_url": "https://example.com/downloads/QuanLyHangHoa-Setup-0.3.0.exe",
  "notes": [
    "Sua loi stretch bang",
    "Cai thien popup detail"
  ],
  "min_required_version": "0.2.5"
}
```

Manifest chinh thuc cua repo hien tai nam tai:

```text
https://raw.githubusercontent.com/antongduy2307/QuanLyHangHoa/main/version.json
```

Hanh vi v1:

- `version` duoc so sanh theo semver so hoc (`0.10.0` > `0.9.9`).
- `min_required_version` danh dau update bat buoc neu local version nho hon nguong toi thieu.
- Neu startup auto-check that bai vi offline / loi mang / manifest loi, app bo qua nhe va khong crash.

## Release / Update Flow

Moi lan phat hanh ban moi:

1. Tang `APP_VERSION` trong `core/version.py`.
2. Neu can, cap nhat `MyAppVersion` trong `installer/QuanLyHangHoa.iss`.
3. Build PyInstaller:

```bash
pyinstaller --noconfirm desktop_app.spec
```

4. Build installer Inno Setup:

```bash
ISCC installer\QuanLyHangHoa.iss
```

5. Upload file installer `.exe` moi len host download.
6. Upload/replace manifest JSON moi voi `version`, `installer_url`, `notes`, `min_required_version`.
7. Dam bao `APP_UPDATE_MANIFEST_URL` tren client tro toi manifest online dung.

Luu y release:

- Update flow chi cap nhat binary app/installer.
- Update flow khong migrate schema va khong can thiep vao `%LOCALAPPDATA%\QuanLyHangHoa\app.db`.
- Neu muon doi chinh sach installer (silent / very silent / restart), can review rieng vi V1 dang uu tien installer co UI de an toan va de debug.

## Ghi chu

- Day la skeleton sach de bat dau phat trien, chua trien khai nghiep vu sau.
- Khi mo rong, giu nguyen nguyen tac: business rules nam o `service`, UI chi goi service va hien thi ket qua.

## Schema Notes

- Xem `docs/schema_invariants.md` de biet rule nao dang duoc enforce o DB, rule nao chi la helper muc model, va rule nao duoc defer sang service layer.
- Ton kho chuan cho `BAO_KG` chi luu theo bao decimal. KG la don vi quy doi/bao cao, khong luu ton kho rieng.
- Neu truoc do ban dang dung DB cu trong thu muc project, app se khong tu dong copy sang AppData. Neu muon giu du lieu cu, hay copy file DB cu thu cong sang vi tri moi hoac reset DB dev sach.
