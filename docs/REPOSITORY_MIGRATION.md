# Repository Migration Plan

The existing GitHub repository `antongduy2307/App_Kiem_soat_hang_hoa_cho_doanh_nghiep` should be reused as the main source-code repository.

Current installed clients check this update manifest:

```text
https://raw.githubusercontent.com/antongduy2307/App_Kiem_soat_hang_hoa_cho_doanh_nghiep/main/version.json
```

For backward compatibility, `version.json` must remain at the repository root on the `main` branch unless a separate client update migrates `APP_UPDATE_MANIFEST_URL`.

## Migration Rules

- Keep the repository owner/name unchanged during the initial migration.
- Keep the default branch named `main`.
- Keep root `version.json` in place.
- Do not delete existing installer files during the initial migration.
- Do not delete existing GitHub Releases or tags.
- Add the application source code into the existing repository.
- Track source and release automation files, including:
  - `core/`
  - `modules/`
  - `shared/`
  - `shell/`
  - `tests/`
  - `docs/`
  - `scripts/`
  - `.github/`
  - `desktop_app.spec`
  - `installer/QuanLyHangHoa.iss`
  - `requirements.txt`

## Files That Must Not Be Committed

Runtime and generated files should stay out of git:

- virtual environments: `.venv/`, `venv/`
- build output: `build/`, `dist/`, `installer/dist/`
- local databases: `*.db`, `*.sqlite`, `*.sqlite3`
- logs
- backups
- exports
- temp/update download folders
- local editor/OS files

## Installer Hosting Direction

Existing installer files should not be deleted during the first migration because they may be referenced by current `version.json` or GitHub Release history.

For future releases, prefer uploading installers to GitHub Releases instead of committing new installer `.exe` files to the repository root. The root `version.json` should point `installer_url` to a direct downloadable `.exe` URL.

## CI/CD Direction

CI/CD can later build the PyInstaller app, compile the Inno Setup installer, upload installer artifacts to GitHub Releases, and update or validate release metadata. That work should preserve the root `version.json` compatibility contract.
