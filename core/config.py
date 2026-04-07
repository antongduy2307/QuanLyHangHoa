from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from os import getenv
from pathlib import Path

from core.paths import DEFAULT_BACKUP_DIR, DEFAULT_DB_PATH, DEFAULT_EXPORT_DIR, PROJECT_ROOT



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
    db_path: Path
    export_dir: Path
    backup_dir: Path
    log_level: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name=getenv("APP_NAME", "Quản lý Hàng hóa"),
        db_path=_resolve_path(getenv("APP_DB_PATH"), DEFAULT_DB_PATH),
        export_dir=_resolve_path(getenv("APP_EXPORT_DIR"), DEFAULT_EXPORT_DIR),
        backup_dir=_resolve_path(getenv("APP_BACKUP_DIR"), DEFAULT_BACKUP_DIR),
        log_level=getenv("APP_LOG_LEVEL", "INFO").upper(),
    )
