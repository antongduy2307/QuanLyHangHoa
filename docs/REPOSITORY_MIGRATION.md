# Repository Migration Status

The official GitHub source repository is:

```text
https://github.com/antongduy2307/QuanLyHangHoa
```

The official update manifest is:

```text
https://raw.githubusercontent.com/antongduy2307/QuanLyHangHoa/main/version.json
```

Release assets should live under:

```text
https://github.com/antongduy2307/QuanLyHangHoa/releases
```

## Current Rules

- Keep the default branch named `main`.
- Keep root `version.json` in place.
- Keep `core/config.py` pointed to the official raw root `version.json`.
- Keep `APP_UPDATE_MANIFEST_URL` as the runtime override for tests, staging, and bridge releases.
- Upload installers to GitHub Releases instead of committing installer `.exe` files to the repository.
- Do not delete the old repository update manifest until installed clients have had time to move to a version that checks the official manifest.

## Files That Should Be Committed

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
- root `version.json`

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

## CI/CD Direction

CI/CD builds the PyInstaller app, compiles the Inno Setup installer, uploads installer artifacts to GitHub Releases, and validates version/tag consistency. Release workflow publishing should target the current repository by default.
