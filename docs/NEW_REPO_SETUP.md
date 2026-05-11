# Official Source Repository Setup

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

## Prepare the local source tree

Before the first push, commit source and release metadata only.

Commit:

- `core/`, `modules/`, `shared/`, `shell/`, `main.py`
- `tests/`
- `docs/`
- `scripts/`
- `.github/`
- `desktop_app.spec`
- `installer/QuanLyHangHoa.iss`
- `requirements.txt`
- `.gitignore`
- root `version.json`
- `.env.example`
- `README.md`

Do not commit:

- `.venv/` or `venv/`
- `build/`, `dist/`, or `installer/dist/`
- local databases such as `*.db`, `*.sqlite`, `*.sqlite3`
- logs, backups, exports, temp folders, or downloaded update installers
- `.env`
- OS/editor files such as `.DS_Store`, `Thumbs.db`, `.vscode/`, `.idea/`

## Verify update metadata

The official source repository must contain `version.json` at the repository root. After pushing, verify that this file is visible at:

```text
https://github.com/antongduy2307/QuanLyHangHoa/blob/main/version.json
```

After the first GitHub Release has an installer asset, replace `version.json` field `installer_url` with the direct installer download URL, for example:

```text
https://github.com/antongduy2307/QuanLyHangHoa/releases/download/v0.7.3/QuanLyHangHoa-Setup-v0.7.3.exe
```

## Update manifest URL

The app defaults to the official raw root manifest URL in `core/config.py`:

```text
https://raw.githubusercontent.com/antongduy2307/QuanLyHangHoa/main/version.json
```

Keep `APP_UPDATE_MANIFEST_URL` override support for tests, staging, and emergency bridge releases.

## Keep the old repository as an update bridge

Old installed clients may still read `version.json` from the old repository. Keep the old repository manifest available temporarily and point its `installer_url` to the new repository release installer.

Do not delete the old repository manifest immediately. Keep it for one or two successful versions so existing installed clients can update into a build that uses the new source repository manifest URL.
