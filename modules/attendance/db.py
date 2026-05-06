from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from core.config import get_settings
from core.utils import ensure_directories


class AttendanceBase(DeclarativeBase):
    """Declarative base for the standalone attendance database."""


def get_attendance_db_path() -> Path:
    return get_settings().app_data_dir / "attendance.db"


@lru_cache(maxsize=1)
def get_attendance_engine() -> Engine:
    db_path = get_attendance_db_path().resolve()
    return create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", echo=False)


AttendanceSessionLocal: Final[sessionmaker] = sessionmaker(
    bind=get_attendance_engine(),
    autoflush=False,
    expire_on_commit=False,
)


def reset_attendance_engine_cache() -> None:
    """Test helper for environment-isolated database paths."""
    get_attendance_engine.cache_clear()
    AttendanceSessionLocal.configure(bind=get_attendance_engine())


def init_attendance_db() -> None:
    from modules.attendance import models  # noqa: F401
    from modules.attendance.seed import seed_attendance_defaults

    ensure_directories([get_attendance_db_path().parent])
    engine = get_attendance_engine()
    AttendanceBase.metadata.create_all(bind=engine)
    with AttendanceSessionLocal() as session:
        seed_attendance_defaults(session)
        session.commit()
