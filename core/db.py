from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from core.config import get_settings
from core.migrations import migrate_customer_invoice_payments_to_debt_payment_v1
from core.utils import ensure_directories


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base."""



def _build_database_url() -> str:
    db_path = get_settings().db_path.resolve()
    ensure_directories([db_path.parent])
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


def _create_engine() -> Engine:
    return create_engine(_build_database_url(), echo=False)


ENGINE = _create_engine()
SessionFactory: sessionmaker = sessionmaker(bind=ENGINE, autoflush=False, expire_on_commit=False)


def reset_engine_cache() -> None:
    """Test helper for environment-isolated database paths."""
    global ENGINE
    ENGINE.dispose()
    ENGINE = _create_engine()
    SessionFactory.configure(bind=ENGINE)



def _import_models() -> None:
    import modules.customer.models  # noqa: F401
    import modules.inventory.models  # noqa: F401
    import modules.orders.models  # noqa: F401
    import modules.returns.models  # noqa: F401
    import modules.sales.models  # noqa: F401



def _ensure_customer_address_column() -> None:
    with ENGINE.begin() as connection:
        table_info = connection.execute(text("PRAGMA table_info(customers)")).mappings().all()
        column_names = {str(row["name"]) for row in table_info}
        if "address" not in column_names:
            connection.execute(text("ALTER TABLE customers ADD COLUMN address VARCHAR(255)"))


def _ensure_customer_note_column() -> None:
    with ENGINE.begin() as connection:
        table_info = connection.execute(text("PRAGMA table_info(customers)")).mappings().all()
        column_names = {str(row["name"]) for row in table_info}
        if "note" not in column_names:
            connection.execute(text("ALTER TABLE customers ADD COLUMN note TEXT"))


def _ensure_customer_active_column() -> None:
    with ENGINE.begin() as connection:
        table_info = connection.execute(text("PRAGMA table_info(customers)")).mappings().all()
        column_names = {str(row["name"]) for row in table_info}
        try:
            if "is_active" not in column_names:
                connection.execute(text("ALTER TABLE customers ADD COLUMN is_active BOOLEAN DEFAULT 1"))
            connection.execute(text("UPDATE customers SET is_active = 1 WHERE is_active IS NULL"))
        except OperationalError as exc:
            if "readonly" not in str(exc).lower():
                raise


def _ensure_customer_balance_ledger_transaction_datetime_column() -> None:
    with ENGINE.begin() as connection:
        table_info = connection.execute(text("PRAGMA table_info(customer_balance_ledgers)")).mappings().all()
        column_names = {str(row["name"]) for row in table_info}
        if "transaction_datetime" not in column_names:
            try:
                connection.execute(text("ALTER TABLE customer_balance_ledgers ADD COLUMN transaction_datetime DATETIME"))
            except OperationalError as exc:
                if "readonly" not in str(exc).lower():
                    raise
                return
        try:
            connection.execute(
                text(
                    "UPDATE customer_balance_ledgers "
                    "SET transaction_datetime = created_at "
                    "WHERE transaction_datetime IS NULL"
                )
            )
        except OperationalError as exc:
            if "readonly" not in str(exc).lower():
                raise


def _ensure_customer_balance_ledger_ordering_columns() -> None:
    with ENGINE.begin() as connection:
        table_info = connection.execute(text("PRAGMA table_info(customer_balance_ledgers)")).mappings().all()
        column_names = {str(row["name"]) for row in table_info}
        try:
            if "source_ref_type" not in column_names:
                connection.execute(text("ALTER TABLE customer_balance_ledgers ADD COLUMN source_ref_type VARCHAR(50)"))
            if "source_ref_id" not in column_names:
                connection.execute(text("ALTER TABLE customer_balance_ledgers ADD COLUMN source_ref_id INTEGER"))
            if "display_order" not in column_names:
                connection.execute(text("ALTER TABLE customer_balance_ledgers ADD COLUMN display_order INTEGER DEFAULT 0"))

            connection.execute(
                text(
                    "UPDATE customer_balance_ledgers "
                    "SET source_ref_type = 'INVOICE', source_ref_id = ref_id, display_order = 10 "
                    "WHERE ref_type = 'INVOICE' AND source_ref_type IS NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE customer_balance_ledgers "
                    "SET display_order = 30 "
                    "WHERE event_type = 'DEBT_PAYMENT' AND ref_type = 'DEBT_PAYMENT' "
                    "AND COALESCE(display_order, 0) = 0"
                )
            )
            connection.execute(
                text(
                    "UPDATE customer_balance_ledgers "
                    "SET source_ref_type = 'INVOICE', "
                    "source_ref_id = ("
                    "  SELECT invoices.id FROM invoices "
                    "  WHERE invoices.invoice_code = substr(customer_balance_ledgers.note, length('Overpayment from invoice ') + 1) "
                    "  LIMIT 1"
                    "), "
                    "display_order = 20 "
                    "WHERE event_type = 'DEBT_PAYMENT' "
                    "AND ref_type = 'DEBT_PAYMENT' "
                    "AND note LIKE 'Overpayment from invoice %' "
                    "AND EXISTS ("
                    "  SELECT 1 FROM invoices "
                    "  WHERE invoices.invoice_code = substr(customer_balance_ledgers.note, length('Overpayment from invoice ') + 1)"
                    ")"
                )
            )
        except OperationalError as exc:
            if "readonly" not in str(exc).lower():
                raise



def init_db() -> None:
    settings = get_settings()
    ensure_directories(
        [
            settings.app_data_dir,
            settings.export_dir,
            settings.backup_dir,
            settings.temp_dir,
            settings.db_path.parent,
        ]
    )
    _import_models()
    Base.metadata.create_all(bind=ENGINE)
    _ensure_customer_address_column()
    _ensure_customer_note_column()
    _ensure_customer_active_column()
    _ensure_customer_balance_ledger_transaction_datetime_column()
    _ensure_customer_balance_ledger_ordering_columns()
    migrate_customer_invoice_payments_to_debt_payment_v1(
        ENGINE,
        db_path=settings.db_path,
        backup_dir=settings.backup_dir,
    )
