from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from os import getenv
from pathlib import Path

from core.paths import (
    PROJECT_ROOT,
    DEFAULT_APP_DIR_NAME,
    get_default_app_data_dir,
    get_default_backup_dir,
    get_default_db_path,
    get_default_export_dir,
    get_default_log_dir,
    get_default_temp_dir,
    get_legacy_app_data_dir,
    migrate_legacy_runtime_dir,
    sanitize_app_dir_name,
)


DEFAULT_APP_NAME = "QuanLyHangHoa"
DEFAULT_RUNTIME_DIR_NAME = DEFAULT_APP_DIR_NAME
MAX_MONEY_INPUT = 10_000_000_000_000
# TODO(new-source-repo): after the clean GitHub source repo exists, change this
# default to that repo's raw root version.json URL. Keep APP_UPDATE_MANIFEST_URL
# available as the local/runtime override for tests, staging, and bridge releases.
DEFAULT_UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/antongduy2307/App_Kiem_soat_hang_hoa_cho_doanh_nghiep/main/version.json"
DEFAULT_UPDATE_CHECK_TIMEOUT_MS = 10_000
DEFAULT_UPDATE_DOWNLOAD_TIMEOUT_MS = 180_000
DEFAULT_UPDATE_DOWNLOAD_RETRY_COUNT = 3
DEFAULT_UPDATE_STARTUP_DELAY_MS = 3_000


def _resolve_path(raw_value: str | None, fallback: Path) -> Path:
    if not raw_value:
        return fallback

    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


def _resolve_int(raw_value: str | None, fallback: int) -> int:
    if not raw_value:
        return fallback
    try:
        value = int(raw_value)
    except ValueError:
        return fallback
    return value if value > 0 else fallback


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_data_dir: Path
    db_path: Path
    log_dir: Path
    export_dir: Path
    backup_dir: Path
    temp_dir: Path
    log_level: str
    update_manifest_url: str
    update_check_timeout_ms: int
    update_download_timeout_ms: int
    update_download_retry_count: int
    update_startup_delay_ms: int
    runtime_dir_name: str = DEFAULT_RUNTIME_DIR_NAME


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    app_name = getenv("APP_NAME", DEFAULT_APP_NAME)
    runtime_dir_name = sanitize_app_dir_name(getenv("APP_RUNTIME_DIR_NAME", DEFAULT_RUNTIME_DIR_NAME))
    app_data_dir = get_default_app_data_dir(runtime_dir_name)
    legacy_app_data_dir = get_legacy_app_data_dir(app_name)
    migrate_legacy_runtime_dir(current_dir=app_data_dir, legacy_dir=legacy_app_data_dir)
    return Settings(
        app_name=app_name,
        app_data_dir=app_data_dir,
        db_path=_resolve_path(getenv("APP_DB_PATH"), get_default_db_path(runtime_dir_name)),
        log_dir=_resolve_path(getenv("APP_LOG_DIR"), get_default_log_dir(runtime_dir_name)),
        export_dir=_resolve_path(getenv("APP_EXPORT_DIR"), get_default_export_dir(runtime_dir_name)),
        backup_dir=_resolve_path(getenv("APP_BACKUP_DIR"), get_default_backup_dir(runtime_dir_name)),
        temp_dir=_resolve_path(getenv("APP_TEMP_DIR"), get_default_temp_dir(runtime_dir_name)),
        log_level=getenv("APP_LOG_LEVEL", "INFO").upper(),
        update_manifest_url=getenv("APP_UPDATE_MANIFEST_URL", DEFAULT_UPDATE_MANIFEST_URL).strip(),
        update_check_timeout_ms=_resolve_int(getenv("APP_UPDATE_TIMEOUT_MS"), DEFAULT_UPDATE_CHECK_TIMEOUT_MS),
        update_download_timeout_ms=_resolve_int(getenv("APP_UPDATE_DOWNLOAD_TIMEOUT_MS"), DEFAULT_UPDATE_DOWNLOAD_TIMEOUT_MS),
        update_download_retry_count=_resolve_int(getenv("APP_UPDATE_DOWNLOAD_RETRY_COUNT"), DEFAULT_UPDATE_DOWNLOAD_RETRY_COUNT),
        update_startup_delay_ms=_resolve_int(getenv("APP_UPDATE_STARTUP_DELAY_MS"), DEFAULT_UPDATE_STARTUP_DELAY_MS),
        runtime_dir_name=runtime_dir_name,
    )
