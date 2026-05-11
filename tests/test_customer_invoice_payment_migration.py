from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import InvoiceStatus, UnitMode, UnitType
from core.exceptions import NotFoundError
from core.migrations import migrate_customer_invoice_payments_to_debt_payment_v1
from modules.customer.models import Customer
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.models import Product, ProductPrice
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
import modules.returns.models  # noqa: F401
from modules.sales.models import Invoice, InvoiceItem
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService


class CustomerInvoicePaymentMigrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.session = self.Session()
        self.customer_repository = CustomerRepository(self.Session)
        self.inventory_repository = InventoryRepository(self.Session)
        self.sales_repository = SalesRepository(self.Session)
        self.customer_service = CustomerService(self.customer_repository)
        self.inventory_service = InventoryService(self.inventory_repository)
        self.sales_service = SalesService(
            self.sales_repository,
            inventory_service=self.inventory_service,
            customer_service=self.customer_service,
        )

    def tearDown(self) -> None:
        self.session.close()
        self.customer_repository.session.close()
        self.engine.dispose()

    def test_legacy_partial_paid_invoice_creates_full_source_linked_payment_idempotently(self) -> None:
        customer_id = self._insert_customer()
        invoice_id = self._insert_invoice(customer_id=customer_id, total_amount="5000", paid_amount="3000")
        self._insert_legacy_invoice_ledgers(customer_id, invoice_id, total_amount="5000", paid_amount="3000")

        result = migrate_customer_invoice_payments_to_debt_payment_v1(self.engine)

        self.assertEqual(result.invoices_scanned, 1)
        self.assertEqual(result.invoices_migrated, 1)
        self.assertEqual(result.embedded_invoice_payments_removed, 1)
        self.assertEqual(result.generated_payments_created, 1)
        ledgers = self._timeline_ledgers(customer_id)
        self.assertEqual([row["event_type"] for row in ledgers], ["INVOICE_CHARGE", "DEBT_PAYMENT"])
        self.assertEqual([self._decimal(row["amount_delta"]) for row in ledgers], [Decimal("5000"), Decimal("-3000")])
        self.assertEqual([self._decimal(row["balance_after"]) for row in ledgers], [Decimal("5000"), Decimal("2000")])
        self.assertEqual(self._customer_balance(customer_id), Decimal("2000"))

        second = migrate_customer_invoice_payments_to_debt_payment_v1(self.engine)

        self.assertEqual(second.invoices_scanned, 1)
        self.assertEqual(second.invoices_migrated, 0)
        self.assertEqual(second.changed_rows, 0)
        self.assertEqual(len(self._generated_payments(invoice_id)), 1)
        self.assertEqual(self._customer_balance(customer_id), Decimal("2000"))

    def test_legacy_full_paid_invoice_nets_balance_to_zero(self) -> None:
        customer_id = self._insert_customer()
        invoice_id = self._insert_invoice(customer_id=customer_id, total_amount="5000", paid_amount="5000")
        self._insert_legacy_invoice_ledgers(customer_id, invoice_id, total_amount="5000", paid_amount="5000")

        migrate_customer_invoice_payments_to_debt_payment_v1(self.engine)

        ledgers = self._timeline_ledgers(customer_id)
        self.assertEqual([self._decimal(row["amount_delta"]) for row in ledgers], [Decimal("5000"), Decimal("-5000")])
        self.assertEqual([self._decimal(row["balance_after"]) for row in ledgers], [Decimal("5000"), Decimal("0")])
        self.assertEqual(self._customer_balance(customer_id), Decimal("0"))

    def test_legacy_overpaid_invoice_syncs_existing_overpayment_to_full_paid_amount(self) -> None:
        customer_id = self._insert_customer()
        invoice_id = self._insert_invoice(customer_id=customer_id, total_amount="5000", paid_amount="10000")
        self._insert_legacy_invoice_ledgers(customer_id, invoice_id, total_amount="5000", paid_amount="5000")
        self._insert_generated_payment(
            customer_id,
            invoice_id,
            ref_id=880001,
            amount_delta="-5000",
            note="Overpayment from invoice HD20260401-001",
        )

        result = migrate_customer_invoice_payments_to_debt_payment_v1(self.engine)

        self.assertEqual(result.embedded_invoice_payments_removed, 1)
        self.assertEqual(result.generated_payments_updated, 1)
        self.assertEqual(result.generated_payments_created, 0)
        ledgers = self._timeline_ledgers(customer_id)
        self.assertEqual([self._decimal(row["amount_delta"]) for row in ledgers], [Decimal("5000"), Decimal("-10000")])
        self.assertEqual([self._decimal(row["balance_after"]) for row in ledgers], [Decimal("5000"), Decimal("-5000")])
        self.assertEqual(ledgers[1]["note"], "Auto payment from invoice HD20260401-001")
        self.assertEqual(self._customer_balance(customer_id), Decimal("-5000"))

    def test_already_migrated_invoice_is_not_duplicated(self) -> None:
        customer_id = self._insert_customer()
        invoice_id = self._insert_invoice(customer_id=customer_id, total_amount="5000", paid_amount="3000")
        self._insert_charge(customer_id, invoice_id, amount_delta="5000", display_order=10)
        self._insert_generated_payment(
            customer_id,
            invoice_id,
            ref_id=880002,
            amount_delta="-3000",
            note="Invoice payment HD20260401-001",
        )
        self._recompute_for_test(customer_id)

        result = migrate_customer_invoice_payments_to_debt_payment_v1(self.engine)

        self.assertEqual(result.invoices_scanned, 1)
        self.assertEqual(result.invoices_migrated, 0)
        self.assertEqual(result.changed_rows, 0)
        generated = self._generated_payments(invoice_id)
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated[0]["note"], "Invoice payment HD20260401-001")
        self.assertEqual(self._customer_balance(customer_id), Decimal("2000"))

    def test_walk_in_invoice_is_ignored(self) -> None:
        invoice_id = self._insert_invoice(customer_id=None, total_amount="5000", paid_amount="3000")

        result = migrate_customer_invoice_payments_to_debt_payment_v1(self.engine)

        self.assertEqual(result.invoices_scanned, 0)
        self.assertEqual(self._generated_payments(invoice_id), [])

    def test_multiple_invoices_recompute_customer_timeline(self) -> None:
        customer_id = self._insert_customer()
        invoice_a = self._insert_invoice(
            customer_id=customer_id,
            total_amount="5000",
            paid_amount="3000",
            code="HD20260401-001",
            invoice_datetime=datetime(2026, 4, 1, 9, 0, 0),
        )
        invoice_b = self._insert_invoice(
            customer_id=customer_id,
            total_amount="2000",
            paid_amount="500",
            code="HD20260401-002",
            invoice_datetime=datetime(2026, 4, 1, 10, 0, 0),
        )
        self._insert_legacy_invoice_ledgers(customer_id, invoice_a, total_amount="5000", paid_amount="3000", transaction_datetime=datetime(2026, 4, 1, 9, 0, 0))
        self._insert_legacy_invoice_ledgers(customer_id, invoice_b, total_amount="2000", paid_amount="500", transaction_datetime=datetime(2026, 4, 1, 10, 0, 0))

        migrate_customer_invoice_payments_to_debt_payment_v1(self.engine)

        ledgers = self._timeline_ledgers(customer_id)
        self.assertEqual(
            [(row["event_type"], self._decimal(row["amount_delta"]), self._decimal(row["balance_after"])) for row in ledgers],
            [
                ("INVOICE_CHARGE", Decimal("5000"), Decimal("5000")),
                ("DEBT_PAYMENT", Decimal("-3000"), Decimal("2000")),
                ("INVOICE_CHARGE", Decimal("2000"), Decimal("4000")),
                ("DEBT_PAYMENT", Decimal("-500"), Decimal("3500")),
            ],
        )
        self.assertEqual(self._customer_balance(customer_id), Decimal("3500"))

    def test_edit_invoice_after_migration_removes_generated_payment_when_paid_becomes_zero(self) -> None:
        customer = self._create_customer_model()
        product = self._create_product_with_price()
        invoice = self._create_legacy_invoice_model(
            customer.id,
            product.id,
            total_amount=Decimal("5000"),
            paid_amount=Decimal("3000"),
        )
        self._insert_legacy_invoice_ledgers(customer.id, invoice.id, total_amount="5000", paid_amount="3000")
        migrate_customer_invoice_payments_to_debt_payment_v1(self.engine)

        updated = self.sales_service.update_invoice(
            invoice.id,
            items=[{"product_id": product.id, "unit_type": UnitType.BAO, "quantity": Decimal("1"), "line_total": Decimal("5000")}],
            paid_amount=Decimal("0"),
        )

        self.assertEqual(updated.paid_amount, Decimal("0"))
        self.assertEqual(self._generated_payments(invoice.id), [])
        self.assertEqual(self._customer_balance(customer.id), Decimal("5000"))

    def test_delete_invoice_after_migration_removes_source_linked_generated_payment(self) -> None:
        customer = self._create_customer_model()
        product = self._create_product_with_price()
        invoice = self._create_legacy_invoice_model(
            customer.id,
            product.id,
            total_amount=Decimal("5000"),
            paid_amount=Decimal("3000"),
        )
        self._insert_legacy_invoice_ledgers(customer.id, invoice.id, total_amount="5000", paid_amount="3000")
        migrate_customer_invoice_payments_to_debt_payment_v1(self.engine)

        self.sales_service.delete_invoice(invoice.id)

        with self.assertRaises(NotFoundError):
            self.sales_repository.get_invoice(invoice.id)
        self.assertEqual(self._generated_payments(invoice.id), [])
        self.assertEqual(self._timeline_ledgers(customer.id), [])
        self.assertEqual(self._customer_balance(customer.id), Decimal("0"))

    def test_duplicate_generated_payments_are_collapsed(self) -> None:
        customer_id = self._insert_customer()
        invoice_id = self._insert_invoice(customer_id=customer_id, total_amount="5000", paid_amount="3000")
        self._insert_charge(customer_id, invoice_id, amount_delta="5000", display_order=10)
        self._insert_generated_payment(customer_id, invoice_id, ref_id=880003, amount_delta="-1000")
        self._insert_generated_payment(customer_id, invoice_id, ref_id=880004, amount_delta="-2000")

        result = migrate_customer_invoice_payments_to_debt_payment_v1(self.engine)

        self.assertEqual(result.generated_payments_updated, 1)
        self.assertEqual(result.duplicate_generated_payments_removed, 1)
        generated = self._generated_payments(invoice_id)
        self.assertEqual(len(generated), 1)
        self.assertEqual(self._decimal(generated[0]["amount_delta"]), Decimal("-3000"))
        self.assertEqual(self._customer_balance(customer_id), Decimal("2000"))

    def _insert_customer(self, name: str = "Khach quen") -> int:
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    "INSERT INTO customers (customer_name, current_balance, total_sales, is_walk_in) "
                    "VALUES (:name, 0, 0, 0)"
                ),
                {"name": name},
            )
            return int(result.lastrowid)

    def _insert_invoice(
        self,
        *,
        customer_id: int | None,
        total_amount: str,
        paid_amount: str,
        code: str = "HD20260401-001",
        invoice_datetime: datetime = datetime(2026, 4, 1, 9, 0, 0),
    ) -> int:
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    "INSERT INTO invoices "
                    "(invoice_code, customer_id, customer_snapshot_name, invoice_datetime, total_amount, paid_amount, status) "
                    "VALUES (:code, :customer_id, 'Khach quen', :invoice_datetime, :total_amount, :paid_amount, :status)"
                ),
                {
                    "code": code,
                    "customer_id": customer_id,
                    "invoice_datetime": invoice_datetime,
                    "total_amount": total_amount,
                    "paid_amount": paid_amount,
                    "status": InvoiceStatus.COMPLETED.value,
                },
            )
            return int(result.lastrowid)

    def _insert_legacy_invoice_ledgers(
        self,
        customer_id: int,
        invoice_id: int,
        *,
        total_amount: str,
        paid_amount: str,
        transaction_datetime: datetime = datetime(2026, 4, 1, 9, 0, 0),
    ) -> None:
        self._insert_charge(customer_id, invoice_id, amount_delta=total_amount, display_order=10, transaction_datetime=transaction_datetime)
        self._insert_invoice_payment(customer_id, invoice_id, amount_delta=f"-{paid_amount}", transaction_datetime=transaction_datetime)

    def _insert_charge(
        self,
        customer_id: int,
        invoice_id: int,
        *,
        amount_delta: str,
        display_order: int,
        transaction_datetime: datetime = datetime(2026, 4, 1, 9, 0, 0),
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO customer_balance_ledgers "
                    "(customer_id, event_type, ref_type, ref_id, source_ref_type, source_ref_id, display_order, "
                    "amount_delta, balance_after, transaction_datetime, note) "
                    "VALUES (:customer_id, 'INVOICE_CHARGE', 'INVOICE', :invoice_id, 'INVOICE', :invoice_id, "
                    ":display_order, :amount_delta, 0, :transaction_datetime, 'Invoice charge HD20260401-001')"
                ),
                {
                    "customer_id": customer_id,
                    "invoice_id": invoice_id,
                    "display_order": display_order,
                    "amount_delta": amount_delta,
                    "transaction_datetime": transaction_datetime,
                },
            )

    def _insert_invoice_payment(
        self,
        customer_id: int,
        invoice_id: int,
        *,
        amount_delta: str,
        transaction_datetime: datetime = datetime(2026, 4, 1, 9, 0, 0),
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO customer_balance_ledgers "
                    "(customer_id, event_type, ref_type, ref_id, source_ref_type, source_ref_id, display_order, "
                    "amount_delta, balance_after, transaction_datetime, note) "
                    "VALUES (:customer_id, 'INVOICE_PAYMENT', 'INVOICE', :invoice_id, 'INVOICE', :invoice_id, "
                    "10, :amount_delta, 0, :transaction_datetime, 'Legacy embedded invoice payment')"
                ),
                {
                    "customer_id": customer_id,
                    "invoice_id": invoice_id,
                    "amount_delta": amount_delta,
                    "transaction_datetime": transaction_datetime,
                },
            )

    def _insert_generated_payment(
        self,
        customer_id: int,
        invoice_id: int,
        *,
        ref_id: int,
        amount_delta: str,
        note: str = "Auto payment from invoice HD20260401-001",
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO customer_balance_ledgers "
                    "(customer_id, event_type, ref_type, ref_id, source_ref_type, source_ref_id, display_order, "
                    "amount_delta, balance_after, transaction_datetime, note) "
                    "VALUES (:customer_id, 'DEBT_PAYMENT', 'DEBT_PAYMENT', :ref_id, 'INVOICE', :invoice_id, "
                    "20, :amount_delta, 0, :transaction_datetime, :note)"
                ),
                {
                    "customer_id": customer_id,
                    "invoice_id": invoice_id,
                    "ref_id": ref_id,
                    "amount_delta": amount_delta,
                    "transaction_datetime": datetime(2026, 4, 1, 9, 0, 0),
                    "note": note,
                },
            )

    def _recompute_for_test(self, customer_id: int) -> None:
        with self.engine.begin() as connection:
            running_balance = Decimal("0")
            rows = (
                connection.execute(
                    text(
                        "SELECT id, amount_delta FROM customer_balance_ledgers "
                        "WHERE customer_id = :customer_id "
                        "ORDER BY transaction_datetime ASC, display_order ASC, id ASC"
                    ),
                    {"customer_id": customer_id},
                )
                .mappings()
                .all()
            )
            for row in rows:
                running_balance += self._decimal(row["amount_delta"])
                connection.execute(
                    text("UPDATE customer_balance_ledgers SET balance_after = :balance_after WHERE id = :id"),
                    {"balance_after": str(running_balance), "id": row["id"]},
                )
            connection.execute(
                text("UPDATE customers SET current_balance = :balance WHERE id = :id"),
                {"balance": str(running_balance), "id": customer_id},
            )

    def _timeline_ledgers(self, customer_id: int) -> list[dict[str, object]]:
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    text(
                        "SELECT id, event_type, ref_type, ref_id, source_ref_type, source_ref_id, display_order, "
                        "amount_delta, balance_after, note "
                        "FROM customer_balance_ledgers "
                        "WHERE customer_id = :customer_id "
                        "ORDER BY transaction_datetime ASC, display_order ASC, id ASC"
                    ),
                    {"customer_id": customer_id},
                )
                .mappings()
                .all()
            ]

    def _generated_payments(self, invoice_id: int) -> list[dict[str, object]]:
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    text(
                        "SELECT id, amount_delta, balance_after, source_ref_type, source_ref_id, display_order, note "
                        "FROM customer_balance_ledgers "
                        "WHERE event_type = 'DEBT_PAYMENT' AND ref_type = 'DEBT_PAYMENT' "
                        "AND source_ref_type = 'INVOICE' AND source_ref_id = :invoice_id "
                        "ORDER BY id ASC"
                    ),
                    {"invoice_id": invoice_id},
                )
                .mappings()
                .all()
            ]

    def _customer_balance(self, customer_id: int) -> Decimal:
        with self.engine.connect() as connection:
            value = connection.execute(
                text("SELECT current_balance FROM customers WHERE id = :customer_id"),
                {"customer_id": customer_id},
            ).scalar_one()
        return self._decimal(value)

    def _create_customer_model(self) -> Customer:
        customer = Customer(customer_name="Khach quen", phone=None, current_balance=Decimal("0"), total_sales=Decimal("0"))
        self.session.add(customer)
        self.session.commit()
        return customer

    def _create_product_with_price(self) -> Product:
        product = Product(product_code_base="P-BAO", product_name="P-BAO", unit_mode=UnitMode.BAO_KG, is_active=True)
        self.session.add(product)
        self.session.flush()
        self.session.add(ProductPrice(product_id=product.id, unit_type=UnitType.BAO, price=Decimal("5000"), is_enabled=True))
        self.session.commit()
        return product

    def _create_legacy_invoice_model(
        self,
        customer_id: int,
        product_id: int,
        *,
        total_amount: Decimal,
        paid_amount: Decimal,
    ) -> Invoice:
        invoice = Invoice(
            invoice_code="HD20260401-009",
            customer_id=customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 1, 9, 0, 0),
            total_amount=total_amount,
            paid_amount=paid_amount,
            status=InvoiceStatus.COMPLETED,
        )
        self.session.add(invoice)
        self.session.flush()
        invoice.items.append(
            InvoiceItem(
                product_id=product_id,
                unit_type=UnitType.BAO,
                quantity=Decimal("1"),
                unit_price=total_amount,
                line_total=total_amount,
                product_code_snapshot="P-BAO",
                product_name_snapshot="P-BAO",
            )
        )
        customer = self.session.get(Customer, customer_id)
        if customer is not None:
            customer.total_sales = total_amount
        self.session.commit()
        return invoice

    @staticmethod
    def _decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))


if __name__ == "__main__":
    unittest.main()
