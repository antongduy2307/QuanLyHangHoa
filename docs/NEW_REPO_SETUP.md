# New Source Repository Setup

This project is being prepared for a brand-new GitHub source repository. The old repository remains separate and should not be reused as the canonical source repository.

## Create the new GitHub repository

1. Create an empty GitHub repository.
2. Do not initialize it with a README, license, or `.gitignore` if this local repository will be pushed first.
3. Copy the new repository URL for the local `origin` remote.

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

The new source repository must contain `version.json` at the repository root. After pushing, verify that this file is visible at:

```text
https://github.com/<OWNER>/<NEW_REPO>/blob/main/version.json
```

After the first GitHub Release has an installer asset, replace `version.json` field `installer_url` with the direct installer download URL.

## Update manifest URL

The app currently defaults to the old repository manifest URL in `core/config.py`. Do not guess the new URL before the new repository exists.

After the new repository is created and `version.json` is present on `main`, update `DEFAULT_UPDATE_MANIFEST_URL` to the new raw URL:

```text
https://raw.githubusercontent.com/<OWNER>/<NEW_REPO>/main/version.json
```

Keep `APP_UPDATE_MANIFEST_URL` override support for tests, staging, and emergency bridge releases.

## Keep the old repository as an update bridge

Old installed clients may still read `version.json` from the old repository. Keep the old repository manifest available temporarily and point its `installer_url` to the new repository release installer.

Do not delete the old repository manifest immediately. Keep it for one or two successful versions so existing installed clients can update into a build that uses the new source repository manifest URL.
