from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from os import getenv
from pathlib import Path

from core.paths import (
    PROJECT_ROOT,
    get_default_app_data_dir,
    get_default_backup_dir,
    get_default_db_path,
    get_default_export_dir,
    get_default_temp_dir,
)


DEFAULT_APP_NAME = "Quản lý Hàng hóa"


def _resolve_path(raw_value: str | None, fallback: Path) -> Path:
    if not raw_value:
        return fallback

    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_data_dir: Path
    db_path: Path
    export_dir: Path
    backup_dir: Path
    temp_dir: Path
    log_level: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    app_name = getenv("APP_NAME", DEFAULT_APP_NAME)
    app_data_dir = get_default_app_data_dir(app_name)
    return Settings(
        app_name=app_name,
        app_data_dir=app_data_dir,
        db_path=_resolve_path(getenv("APP_DB_PATH"), get_default_db_path(app_name)),
        export_dir=_resolve_path(getenv("APP_EXPORT_DIR"), get_default_export_dir(app_name)),
        backup_dir=_resolve_path(getenv("APP_BACKUP_DIR"), get_default_backup_dir(app_name)),
        temp_dir=_resolve_path(getenv("APP_TEMP_DIR"), get_default_temp_dir(app_name)),
        log_level=getenv("APP_LOG_LEVEL", "INFO").upper(),
    )
