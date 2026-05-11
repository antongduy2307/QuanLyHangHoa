# Old Repository Update Bridge

The old GitHub repository is still part of the update path for already installed clients. Those clients may continue reading the update manifest from the old repository until they install a version that points to the new source repository manifest.

Official source repository:

```text
https://github.com/antongduy2307/QuanLyHangHoa
```

Official update manifest:

```text
https://raw.githubusercontent.com/antongduy2307/QuanLyHangHoa/main/version.json
```

Official release assets:

```text
https://github.com/antongduy2307/QuanLyHangHoa/releases
```

## Bridge strategy

1. Keep the old repository root `version.json` available.
2. When the new repository publishes a GitHub Release, update the old repository `version.json` so `installer_url` points to the new repository release installer asset.
3. Keep `version`, `notes`, and `min_required_version` aligned with the released installer.
4. Release a client version whose `core/config.py` default manifest URL points to the official repository root `version.json`.
5. After one or two successful versions, move fully to the new repository manifest URL.

Do not delete the old repository manifest immediately. Removing it too early can strand installed clients that still know only the old manifest URL.

## Old repository manifest example

Do not edit the old repository from this source tree. In the old repository only, its temporary bridge `version.json` should point to the new repository release installer:

```json
{
  "version": "0.7.3",
  "installer_url": "https://github.com/antongduy2307/QuanLyHangHoa/releases/download/v0.7.3/QuanLyHangHoa-Setup-v0.7.3.exe",
  "notes": [
    "Chuyen sang he thong cap nhat moi."
  ],
  "min_required_version": "0.7.3"
}
```

This lets old clients update into a version that checks the official repository manifest going forward.

## Runtime override

`APP_UPDATE_MANIFEST_URL` remains the supported runtime override for testing, staging, or emergency update bridge work.
