from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import shutil

from sqlalchemy import Engine, RowMapping, text
from sqlalchemy.exc import OperationalError

from core.logging import get_logger


LOGGER = get_logger(__name__)
MIGRATION_INVOICE_PAYMENT_V1 = "migrate_customer_invoice_payments_to_debt_payment_v1"
DEBT_PAYMENT_REF_ID_BASE = 8_100_000_000_000_000


@dataclass(slots=True)
class CustomerInvoicePaymentMigrationResult:
    invoices_scanned: int = 0
    invoices_migrated: int = 0
    invoice_charges_created: int = 0
    invoice_charges_updated: int = 0
    embedded_invoice_payments_removed: int = 0
    generated_payments_created: int = 0
    generated_payments_updated: int = 0
    duplicate_generated_payments_removed: int = 0
    customers_recomputed: int = 0
    backup_path: Path | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def changed_rows(self) -> int:
        return (
            self.invoice_charges_created
            + self.invoice_charges_updated
            + self.embedded_invoice_payments_removed
            + self.generated_payments_created
            + self.generated_payments_updated
            + self.duplicate_generated_payments_removed
        )


def migrate_customer_invoice_payments_to_debt_payment_v1(
    engine: Engine,
    *,
    db_path: Path | None = None,
    backup_dir: Path | None = None,
) -> CustomerInvoicePaymentMigrationResult:
    """Backfill legacy customer invoice payments into source-linked debt payments.

    Legacy rows may store the received amount as an INVOICE_PAYMENT ledger under the
    invoice reference. The current ledger semantics require invoice rows to represent
    only the merchandise charge and the actual received amount to be represented by a
    separate DEBT_PAYMENT linked back to the invoice.
    """

    result = CustomerInvoicePaymentMigrationResult()
    try:
        with engine.begin() as connection:
            _ensure_required_columns(connection)
            invoices = _list_customer_paid_invoices(connection)
            result.invoices_scanned = len(invoices)
            if not invoices:
                LOGGER.info("%s | no candidate invoices", MIGRATION_INVOICE_PAYMENT_V1)
                return result

            result.backup_path = _create_database_backup(db_path, backup_dir, result)
            affected_customers: set[int] = set()
            migrated_invoice_ids: set[int] = set()

            for invoice in invoices:
                customer_id = int(invoice["customer_id"])
                changed = _migrate_invoice(connection, invoice, result)
                if changed:
                    affected_customers.add(customer_id)
                    migrated_invoice_ids.add(int(invoice["id"]))

            for customer_id in sorted(affected_customers):
                _recompute_customer_balance(connection, customer_id)
                result.customers_recomputed += 1

            result.invoices_migrated = len(migrated_invoice_ids)
    except OperationalError as exc:
        if "readonly" not in str(exc).lower():
            raise
        result.warnings.append("Database is readonly; customer invoice payment migration was skipped.")
        LOGGER.warning("%s | readonly database, skipped", MIGRATION_INVOICE_PAYMENT_V1)
        return result

    LOGGER.info(
        "%s | scanned=%s | migrated=%s | charge_created=%s | charge_updated=%s | "
        "embedded_removed=%s | payment_created=%s | payment_updated=%s | duplicates_removed=%s | "
        "customers_recomputed=%s | backup=%s | warnings=%s",
        MIGRATION_INVOICE_PAYMENT_V1,
        result.invoices_scanned,
        result.invoices_migrated,
        result.invoice_charges_created,
        result.invoice_charges_updated,
        result.embedded_invoice_payments_removed,
        result.generated_payments_created,
        result.generated_payments_updated,
        result.duplicate_generated_payments_removed,
        result.customers_recomputed,
        result.backup_path,
        len(result.warnings),
    )
    return result


def _ensure_required_columns(connection: object) -> None:
    table_info = connection.execute(text("PRAGMA table_info(customer_balance_ledgers)")).mappings().all()
    column_names = {str(row["name"]) for row in table_info}
    missing = {"source_ref_type", "source_ref_id", "display_order"} - column_names
    if missing:
        raise RuntimeError(f"Missing required migration columns: {', '.join(sorted(missing))}")


def _list_customer_paid_invoices(connection: object) -> list[RowMapping]:
    return list(
        connection.execute(
            text(
                "SELECT id, customer_id, invoice_code, invoice_datetime, total_amount, "
                "COALESCE(paid_amount, 0) AS paid_amount "
                "FROM invoices "
                "WHERE customer_id IS NOT NULL AND COALESCE(paid_amount, 0) > 0 "
                "ORDER BY customer_id ASC, invoice_datetime ASC, id ASC"
            )
        )
        .mappings()
        .all()
    )


def _create_database_backup(
    db_path: Path | None,
    backup_dir: Path | None,
    result: CustomerInvoicePaymentMigrationResult,
) -> Path | None:
    if db_path is None or backup_dir is None:
        LOGGER.info("%s | backup skipped because db_path or backup_dir is missing", MIGRATION_INVOICE_PAYMENT_V1)
        return None

    resolved_db_path = db_path.resolve()
    if not resolved_db_path.exists():
        result.warnings.append(f"Database file does not exist for backup: {resolved_db_path}")
        LOGGER.warning("%s | backup skipped because database file does not exist: %s", MIGRATION_INVOICE_PAYMENT_V1, resolved_db_path)
        return None

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_dir / f"{resolved_db_path.stem}-before-invoice-payment-migration-v1-{timestamp}{resolved_db_path.suffix}"
        shutil.copy2(resolved_db_path, backup_path)
        LOGGER.info("%s | database backup created at %s", MIGRATION_INVOICE_PAYMENT_V1, backup_path)
        return backup_path
    except OSError as exc:
        result.warnings.append(f"Database backup failed: {exc}")
        LOGGER.warning("%s | database backup failed: %s", MIGRATION_INVOICE_PAYMENT_V1, exc)
        return None


def _migrate_invoice(
    connection: object,
    invoice: RowMapping,
    result: CustomerInvoicePaymentMigrationResult,
) -> bool:
    invoice_id = int(invoice["id"])
    customer_id = int(invoice["customer_id"])
    invoice_code = str(invoice["invoice_code"])
    invoice_datetime = _to_datetime(invoice["invoice_datetime"])
    invoice_total = _to_decimal(invoice["total_amount"])
    paid_amount = _to_decimal(invoice["paid_amount"])

    changed = False
    expected_charge_note = f"Invoice charge {invoice_code}"
    expected_payment_note = f"Auto payment from invoice {invoice_code}"
    invoice_ledgers = _list_invoice_ledgers(connection, customer_id, invoice_id)
    charge_ledgers = [row for row in invoice_ledgers if str(row["event_type"]) == "INVOICE_CHARGE"]
    extra_invoice_ledgers = [row for row in invoice_ledgers if str(row["event_type"]) != "INVOICE_CHARGE"]

    if charge_ledgers:
        keep_charge = charge_ledgers[0]
        if _update_charge_if_needed(
            connection,
            keep_charge,
            invoice_total,
            invoice_datetime,
            invoice_id,
            expected_charge_note,
        ):
            result.invoice_charges_updated += 1
            changed = True
        duplicate_charge_ids = [int(row["id"]) for row in charge_ledgers[1:]]
        if duplicate_charge_ids:
            _delete_ledgers(connection, duplicate_charge_ids)
            result.embedded_invoice_payments_removed += len(duplicate_charge_ids)
            changed = True
    else:
        _insert_invoice_charge(
            connection,
            customer_id,
            invoice_id,
            invoice_total,
            invoice_datetime,
            expected_charge_note,
        )
        result.invoice_charges_created += 1
        changed = True

    extra_invoice_ledger_ids = [int(row["id"]) for row in extra_invoice_ledgers]
    if extra_invoice_ledger_ids:
        _delete_ledgers(connection, extra_invoice_ledger_ids)
        result.embedded_invoice_payments_removed += len(extra_invoice_ledger_ids)
        changed = True

    generated_payments = _list_generated_invoice_payments(connection, customer_id, invoice_id)
    expected_delta = paid_amount * Decimal("-1")
    if generated_payments:
        keep_payment = generated_payments[0]
        if _update_generated_payment_if_needed(
            connection,
            keep_payment,
            expected_delta,
            invoice_datetime,
            invoice_id,
            expected_payment_note,
        ):
            result.generated_payments_updated += 1
            changed = True
        duplicate_ids = [int(row["id"]) for row in generated_payments[1:]]
        if duplicate_ids:
            _delete_ledgers(connection, duplicate_ids)
            result.duplicate_generated_payments_removed += len(duplicate_ids)
            changed = True
    else:
        _insert_generated_payment(
            connection,
            customer_id,
            invoice_id,
            expected_delta,
            invoice_datetime,
            expected_payment_note,
        )
        result.generated_payments_created += 1
        changed = True

    return changed


def _list_invoice_ledgers(connection: object, customer_id: int, invoice_id: int) -> list[RowMapping]:
    return list(
        connection.execute(
            text(
                "SELECT id, event_type, ref_type, ref_id, source_ref_type, source_ref_id, display_order, "
                "amount_delta, transaction_datetime, note "
                "FROM customer_balance_ledgers "
                "WHERE customer_id = :customer_id AND ref_type = 'INVOICE' AND ref_id = :invoice_id "
                "ORDER BY id ASC"
            ),
            {"customer_id": customer_id, "invoice_id": invoice_id},
        )
        .mappings()
        .all()
    )


def _list_generated_invoice_payments(connection: object, customer_id: int, invoice_id: int) -> list[RowMapping]:
    return list(
        connection.execute(
            text(
                "SELECT id, event_type, ref_type, ref_id, source_ref_type, source_ref_id, display_order, "
                "amount_delta, transaction_datetime, note "
                "FROM customer_balance_ledgers "
                "WHERE customer_id = :customer_id "
                "AND event_type = 'DEBT_PAYMENT' "
                "AND ref_type = 'DEBT_PAYMENT' "
                "AND source_ref_type = 'INVOICE' "
                "AND source_ref_id = :invoice_id "
                "ORDER BY id ASC"
            ),
            {"customer_id": customer_id, "invoice_id": invoice_id},
        )
        .mappings()
        .all()
    )


def _update_charge_if_needed(
    connection: object,
    ledger: RowMapping,
    invoice_total: Decimal,
    invoice_datetime: datetime,
    invoice_id: int,
    note: str,
) -> bool:
    updates: dict[str, object] = {}
    if _to_decimal(ledger["amount_delta"]) != invoice_total:
        updates["amount_delta"] = invoice_total
    if _to_datetime(ledger["transaction_datetime"]) != invoice_datetime:
        updates["transaction_datetime"] = invoice_datetime
    if ledger["source_ref_type"] != "INVOICE":
        updates["source_ref_type"] = "INVOICE"
    if ledger["source_ref_id"] != invoice_id:
        updates["source_ref_id"] = invoice_id
    if int(ledger["display_order"] or 0) != 10:
        updates["display_order"] = 10
    if (ledger["note"] or "") != note:
        updates["note"] = note
    if not updates:
        return False

    _update_ledger(connection, int(ledger["id"]), updates)
    return True


def _update_generated_payment_if_needed(
    connection: object,
    ledger: RowMapping,
    expected_delta: Decimal,
    invoice_datetime: datetime,
    invoice_id: int,
    note: str,
) -> bool:
    updates: dict[str, object] = {}
    if _to_decimal(ledger["amount_delta"]) != expected_delta:
        updates["amount_delta"] = expected_delta
    if _to_datetime(ledger["transaction_datetime"]) != invoice_datetime:
        updates["transaction_datetime"] = invoice_datetime
    if ledger["source_ref_type"] != "INVOICE":
        updates["source_ref_type"] = "INVOICE"
    if ledger["source_ref_id"] != invoice_id:
        updates["source_ref_id"] = invoice_id
    if int(ledger["display_order"] or 0) != 20:
        updates["display_order"] = 20
    current_note = ledger["note"] or ""
    if not current_note or current_note.startswith("Overpayment from invoice "):
        updates["note"] = note
    if not updates:
        return False

    _update_ledger(connection, int(ledger["id"]), updates)
    return True


def _update_ledger(connection: object, ledger_id: int, updates: dict[str, object]) -> None:
    assignments = ", ".join(f"{column} = :{column}" for column in updates)
    params = {key: _to_sql_value(value) for key, value in updates.items()}
    params["ledger_id"] = ledger_id
    connection.execute(
        text(f"UPDATE customer_balance_ledgers SET {assignments} WHERE id = :ledger_id"),
        params,
    )


def _insert_invoice_charge(
    connection: object,
    customer_id: int,
    invoice_id: int,
    invoice_total: Decimal,
    invoice_datetime: datetime,
    note: str,
) -> None:
    connection.execute(
        text(
            "INSERT INTO customer_balance_ledgers "
            "(customer_id, event_type, ref_type, ref_id, source_ref_type, source_ref_id, display_order, "
            "amount_delta, balance_after, transaction_datetime, note) "
            "VALUES (:customer_id, 'INVOICE_CHARGE', 'INVOICE', :invoice_id, 'INVOICE', :invoice_id, 10, "
            ":amount_delta, 0, :transaction_datetime, :note)"
        ),
        {
            "customer_id": customer_id,
            "invoice_id": invoice_id,
            "amount_delta": _to_sql_value(invoice_total),
            "transaction_datetime": invoice_datetime,
            "note": note,
        },
    )


def _insert_generated_payment(
    connection: object,
    customer_id: int,
    invoice_id: int,
    amount_delta: Decimal,
    invoice_datetime: datetime,
    note: str,
) -> None:
    ref_id = _next_debt_payment_ref_id(connection, invoice_id)
    connection.execute(
        text(
            "INSERT INTO customer_balance_ledgers "
            "(customer_id, event_type, ref_type, ref_id, source_ref_type, source_ref_id, display_order, "
            "amount_delta, balance_after, transaction_datetime, note) "
            "VALUES (:customer_id, 'DEBT_PAYMENT', 'DEBT_PAYMENT', :ref_id, 'INVOICE', :invoice_id, 20, "
            ":amount_delta, 0, :transaction_datetime, :note)"
        ),
        {
            "customer_id": customer_id,
            "ref_id": ref_id,
            "invoice_id": invoice_id,
            "amount_delta": _to_sql_value(amount_delta),
            "transaction_datetime": invoice_datetime,
            "note": note,
        },
    )


def _next_debt_payment_ref_id(connection: object, invoice_id: int) -> int:
    candidate = DEBT_PAYMENT_REF_ID_BASE + int(invoice_id)
    while True:
        exists = connection.execute(
            text(
                "SELECT 1 FROM customer_balance_ledgers "
                "WHERE ref_type = 'DEBT_PAYMENT' AND ref_id = :ref_id LIMIT 1"
            ),
            {"ref_id": candidate},
        ).scalar_one_or_none()
        if exists is None:
            return candidate
        candidate += 1


def _delete_ledgers(connection: object, ledger_ids: list[int]) -> None:
    for ledger_id in ledger_ids:
        connection.execute(text("DELETE FROM customer_balance_ledgers WHERE id = :ledger_id"), {"ledger_id": ledger_id})


def _recompute_customer_balance(connection: object, customer_id: int) -> None:
    ledgers = (
        connection.execute(
            text(
                "SELECT id, amount_delta "
                "FROM customer_balance_ledgers "
                "WHERE customer_id = :customer_id "
                "ORDER BY transaction_datetime ASC, display_order ASC, id ASC"
            ),
            {"customer_id": customer_id},
        )
        .mappings()
        .all()
    )
    running_balance = Decimal("0")
    for ledger in ledgers:
        running_balance += _to_decimal(ledger["amount_delta"])
        connection.execute(
            text("UPDATE customer_balance_ledgers SET balance_after = :balance_after WHERE id = :ledger_id"),
            {"balance_after": _to_sql_value(running_balance), "ledger_id": int(ledger["id"])},
        )
    connection.execute(
        text("UPDATE customers SET current_balance = :current_balance WHERE id = :customer_id"),
        {"current_balance": _to_sql_value(running_balance), "customer_id": customer_id},
    )


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_sql_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _to_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.replace(microsecond=value.microsecond)
    raw = str(value)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)
