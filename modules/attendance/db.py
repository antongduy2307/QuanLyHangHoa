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
        if "is_product_linked" not in bag_columns:
            connection.execute(text("ALTER TABLE bag_types ADD COLUMN is_product_linked BOOLEAN DEFAULT 0 NOT NULL"))
        if "source_product_id" not in bag_columns:
            connection.execute(text("ALTER TABLE bag_types ADD COLUMN source_product_id INTEGER"))
        if "source_product_name_snapshot" not in bag_columns:
            connection.execute(text("ALTER TABLE bag_types ADD COLUMN source_product_name_snapshot VARCHAR(255)"))
        if "is_excluded_from_attendance" not in bag_columns:
            connection.execute(text("ALTER TABLE bag_types ADD COLUMN is_excluded_from_attendance BOOLEAN DEFAULT 0 NOT NULL"))
        if "is_legacy" not in bag_columns:
            connection.execute(text("ALTER TABLE bag_types ADD COLUMN is_legacy BOOLEAN DEFAULT 0 NOT NULL"))
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_bag_types_source_product_id_unique "
                "ON bag_types (source_product_id) WHERE source_product_id IS NOT NULL"
            )
        )

        cut_columns = _table_columns(connection, "cut_logs")
        if "quota_quantity_snapshot" not in cut_columns:
            connection.execute(text("ALTER TABLE cut_logs ADD COLUMN quota_quantity_snapshot NUMERIC"))
        if "excess_unit_price_snapshot" not in cut_columns:
            connection.execute(text("ALTER TABLE cut_logs ADD COLUMN excess_unit_price_snapshot NUMERIC"))
        _rebuild_cut_logs_quantity_if_needed(connection)
        _rebuild_extra_cut_work_logs_quantity_if_needed(connection)


def _table_columns(connection: object, table_name: str) -> set[str]:
    rows = _table_column_info(connection, table_name)
    return {str(row["name"]) for row in rows}


def _table_column_info(connection: object, table_name: str):
    return connection.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()


def _column_type(connection: object, table_name: str, column_name: str) -> str:
    for row in _table_column_info(connection, table_name):
        if str(row["name"]) == column_name:
            return str(row["type"]).upper()
    return ""


def _rebuild_cut_logs_quantity_if_needed(connection: object) -> None:
    if "NUMERIC" in _column_type(connection, "cut_logs", "quantity"):
        return
    connection.execute(text("PRAGMA foreign_keys=OFF"))
    connection.execute(
        text(
            """
            CREATE TABLE cut_logs_new (
                id INTEGER NOT NULL,
                daily_record_id INTEGER NOT NULL,
                bag_type_id INTEGER NOT NULL,
                quantity NUMERIC(12, 3) NOT NULL,
                unit_price_snapshot INTEGER NOT NULL,
                quota_quantity_snapshot NUMERIC,
                excess_unit_price_snapshot NUMERIC,
                amount_snapshot INTEGER NOT NULL,
                PRIMARY KEY (id),
                CONSTRAINT uq_cut_log_daily_record_bag_type UNIQUE (daily_record_id, bag_type_id),
                CONSTRAINT ck_cut_log_quantity_non_negative CHECK (quantity >= 0),
                CONSTRAINT ck_cut_log_unit_price_non_negative CHECK (unit_price_snapshot >= 0),
                CONSTRAINT ck_cut_log_quota_quantity_non_negative CHECK (quota_quantity_snapshot IS NULL OR quota_quantity_snapshot >= 0),
                CONSTRAINT ck_cut_log_excess_unit_price_non_negative CHECK (excess_unit_price_snapshot IS NULL OR excess_unit_price_snapshot >= 0),
                CONSTRAINT ck_cut_log_amount_non_negative CHECK (amount_snapshot >= 0),
                FOREIGN KEY(daily_record_id) REFERENCES daily_records (id) ON DELETE CASCADE,
                FOREIGN KEY(bag_type_id) REFERENCES bag_types (id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO cut_logs_new (
                id, daily_record_id, bag_type_id, quantity, unit_price_snapshot,
                quota_quantity_snapshot, excess_unit_price_snapshot, amount_snapshot
            )
            SELECT
                id, daily_record_id, bag_type_id, quantity, unit_price_snapshot,
                quota_quantity_snapshot, excess_unit_price_snapshot, amount_snapshot
            FROM cut_logs
            """
        )
    )
    connection.execute(text("DROP TABLE cut_logs"))
    connection.execute(text("ALTER TABLE cut_logs_new RENAME TO cut_logs"))
    connection.execute(text("PRAGMA foreign_keys=ON"))


def _rebuild_extra_cut_work_logs_quantity_if_needed(connection: object) -> None:
    if "NUMERIC" in _column_type(connection, "extra_cut_work_logs", "quantity"):
        return
    connection.execute(text("PRAGMA foreign_keys=OFF"))
    connection.execute(
        text(
            """
            CREATE TABLE extra_cut_work_logs_new (
                id INTEGER NOT NULL,
                daily_record_id INTEGER NOT NULL,
                bag_type_id INTEGER NOT NULL,
                quantity NUMERIC(12, 3) NOT NULL,
                excess_unit_price_snapshot NUMERIC(12, 2) NOT NULL,
                amount_snapshot INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                CONSTRAINT uq_extra_cut_work_daily_bag_type UNIQUE (daily_record_id, bag_type_id),
                CONSTRAINT ck_extra_cut_work_quantity_positive CHECK (quantity > 0),
                CONSTRAINT ck_extra_cut_work_excess_price_non_negative CHECK (excess_unit_price_snapshot >= 0),
                CONSTRAINT ck_extra_cut_work_amount_non_negative CHECK (amount_snapshot >= 0),
                FOREIGN KEY(daily_record_id) REFERENCES daily_records (id) ON DELETE CASCADE,
                FOREIGN KEY(bag_type_id) REFERENCES bag_types (id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO extra_cut_work_logs_new (
                id, daily_record_id, bag_type_id, quantity, excess_unit_price_snapshot,
                amount_snapshot, created_at, updated_at
            )
            SELECT
                id, daily_record_id, bag_type_id, quantity, excess_unit_price_snapshot,
                amount_snapshot, created_at, updated_at
            FROM extra_cut_work_logs
            """
        )
    )
    connection.execute(text("DROP TABLE extra_cut_work_logs"))
    connection.execute(text("ALTER TABLE extra_cut_work_logs_new RENAME TO extra_cut_work_logs"))
    connection.execute(text("PRAGMA foreign_keys=ON"))
