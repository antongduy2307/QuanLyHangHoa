from __future__ import annotations

import re
from os import getenv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGACY_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_APP_DIR_NAME = "QuanLyHangHoa"
_WINDOWS_FORBIDDEN_PATH_CHARS = re.compile(r'[<>:"/\\|?*]')


def sanitize_app_dir_name(app_name: str) -> str:
    normalized = _WINDOWS_FORBIDDEN_PATH_CHARS.sub("_", app_name).strip().strip(".")
    return normalized or DEFAULT_APP_DIR_NAME


def get_local_appdata_root() -> Path | None:
    local_appdata = getenv("LOCALAPPDATA")
    if not local_appdata:
        return None
    return Path(local_appdata)


def get_default_app_data_dir(app_name: str) -> Path:
    local_appdata_root = get_local_appdata_root()
    if local_appdata_root is None:
        return LEGACY_DATA_DIR
    return local_appdata_root / sanitize_app_dir_name(app_name)


def get_default_db_path(app_name: str) -> Path:
    return get_default_app_data_dir(app_name) / "app.db"


def get_default_export_dir(app_name: str) -> Path:
    return get_default_app_data_dir(app_name) / "exports"


def get_default_backup_dir(app_name: str) -> Path:
    return get_default_app_data_dir(app_name) / "backups"


def get_default_temp_dir(app_name: str) -> Path:
    return get_default_app_data_dir(app_name) / "temp"
