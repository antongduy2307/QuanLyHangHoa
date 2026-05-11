from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import text
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
    ensure_directories([db_path.parent])
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
    _upgrade_attendance_schema(engine)
    with AttendanceSessionLocal() as session:
        seed_attendance_defaults(session)
        session.commit()


def _upgrade_attendance_schema(engine: Engine) -> None:
    """Apply small idempotent SQLite upgrades for existing attendance databases."""
    with engine.begin() as connection:
        bag_columns = _table_columns(connection, "bag_types")
        if "quota_quantity" not in bag_columns:
            connection.execute(text("ALTER TABLE bag_types ADD COLUMN quota_quantity NUMERIC DEFAULT 0 NOT NULL"))
        if "excess_unit_price" not in bag_columns:
            connection.execute(text("ALTER TABLE bag_types ADD COLUMN excess_unit_price NUMERIC DEFAULT 0 NOT NULL"))
            connection.execute(text("UPDATE bag_types SET excess_unit_price = unit_price WHERE excess_unit_price = 0"))

        cut_columns = _table_columns(connection, "cut_logs")
        if "quota_quantity_snapshot" not in cut_columns:
            connection.execute(text("ALTER TABLE cut_logs ADD COLUMN quota_quantity_snapshot NUMERIC"))
        if "excess_unit_price_snapshot" not in cut_columns:
            connection.execute(text("ALTER TABLE cut_logs ADD COLUMN excess_unit_price_snapshot NUMERIC"))


def _table_columns(connection: object, table_name: str) -> set[str]:
    rows = connection.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
    return {str(row["name"]) for row in rows}
