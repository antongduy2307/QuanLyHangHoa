from __future__ import annotations

import unittest

from sqlalchemy import create_engine, text

import core.db as db


class LedgerOrderingMigrationTestCase(unittest.TestCase):
    def test_ordering_migration_backfills_legacy_overpayment_source(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_code VARCHAR(64))"))
            connection.execute(
                text(
                    "CREATE TABLE customer_balance_ledgers ("
                    "id INTEGER PRIMARY KEY, "
                    "event_type VARCHAR(50), "
                    "ref_type VARCHAR(50), "
                    "ref_id INTEGER, "
                    "note TEXT"
                    ")"
                )
            )
            connection.execute(text("INSERT INTO invoices (id, invoice_code) VALUES (7, 'HD20260423-001')"))
            connection.execute(
                text(
                    "INSERT INTO customer_balance_ledgers "
                    "(id, event_type, ref_type, ref_id, note) "
                    "VALUES (11, 'DEBT_PAYMENT', 'DEBT_PAYMENT', 9001, 'Overpayment from invoice HD20260423-001')"
                )
            )

        original_engine = db.ENGINE
        db.ENGINE = engine  # type: ignore[misc]
        try:
            db._ensure_customer_balance_ledger_ordering_columns()
        finally:
            db.ENGINE = original_engine  # type: ignore[misc]

        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT source_ref_type, source_ref_id, display_order "
                    "FROM customer_balance_ledgers WHERE id = 11"
                )
            ).mappings().one()

        self.assertEqual(row["source_ref_type"], "INVOICE")
        self.assertEqual(row["source_ref_id"], 7)
        self.assertEqual(row["display_order"], 20)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
