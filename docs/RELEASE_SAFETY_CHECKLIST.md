# Release Safety Checklist

Use this checklist before pushing a release tag or updating the production update manifest.

## Version

- [ ] `core/version.py` has the intended `APP_VERSION`.
- [ ] The release tag matches `APP_VERSION` with a leading `v`.
  - Example: `APP_VERSION = "0.7.3"` uses tag `v0.7.3`.

## Update Manifest

- [ ] Root `version.json` exists in the GitHub repository.
- [ ] Root `version.json` is on branch `main`.
- [ ] Root `version.json` contains:
  - [ ] `version`
  - [ ] `installer_url`
  - [ ] `notes`
  - [ ] `min_required_version`
- [ ] `installer_url` points to a direct downloadable `.exe`.
- [ ] The raw manifest URL still works:

```text
https://raw.githubusercontent.com/antongduy2307/QuanLyHangHoa/main/version.json
```

## Repository Safety

- [ ] Do not rename the repository unless the app update URL is migrated first.
- [ ] Do not change the default branch away from `main` unless the app update URL is migrated first.
- [ ] Do not delete existing installer files during the initial source-code migration.
- [ ] Do not delete existing GitHub Releases or tags.
- [ ] Do not commit local database files.
- [ ] Do not commit logs, backups, exports, build output, or temp/update download files.

## Verification

- [ ] Run the relevant automated tests before release.
- [ ] Build the PyInstaller app.
- [ ] Build the Inno Setup installer.
- [ ] Confirm the installer launches on a clean Windows environment.
- [ ] Verify an installed app can check for updates.
- [ ] Verify the app downloads the installer from `installer_url`.
