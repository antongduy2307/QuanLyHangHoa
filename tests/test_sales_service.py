from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import PaymentMethod, UnitMode, UnitType
from core.exceptions import NotFoundError, ValidationError
from modules.customer.models import Customer, CustomerBalanceLedger
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.models import Product, ProductPrice
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.returns.controller import ReturnController
import modules.returns.models  # noqa: F401
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService


class SalesServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

        self.sales_repository = SalesRepository(self.Session)
        self.inventory_repository = InventoryRepository(self.Session)
        self.customer_repository = CustomerRepository(self.Session)
        self.inventory_service = InventoryService(self.inventory_repository)
        self.customer_service = CustomerService(self.customer_repository)
        self.sales_service = SalesService(
            self.sales_repository,
            inventory_service=self.inventory_service,
            customer_service=self.customer_service,
        )
        self.return_controller = ReturnController(self.Session)

        self.bao_product_id = self._create_product_with_price("P-BAO", UnitMode.BAO_KG, [(UnitType.BAO, "100"), (UnitType.KG, "5")])
        self.bich_product_id = self._create_product_with_price("P-BICH", UnitMode.BICH, [(UnitType.BICH, "20")])
        self.no_price_product_id = self._create_product_with_price("P-NO", UnitMode.BAO_KG, [(UnitType.BAO, "50", False)])
        self.customer_id = self._create_customer("Khach quen")

    def tearDown(self) -> None:
        self.sales_repository.session.close()
        self.engine.dispose()

    def _create_product_with_price(
        self,
        code: str,
        unit_mode: UnitMode,
        prices: list[tuple[UnitType, str] | tuple[UnitType, str, bool]],
    ) -> int:
        session = self.sales_repository.session
        product = Product(product_code_base=code, product_name=code, unit_mode=unit_mode, is_active=True)
        session.add(product)
        session.flush()
        for item in prices:
            unit_type, price, *rest = item
            is_enabled = rest[0] if rest else True
            session.add(
                ProductPrice(
                    product_id=product.id,
                    unit_type=unit_type,
                    price=Decimal(price),
                    is_enabled=is_enabled,
                )
            )
        session.commit()
        return product.id

    def _create_customer(self, name: str) -> int:
        customer = Customer(customer_name=name, phone=None, current_balance=Decimal("0"), total_sales=Decimal("0"))
        self.sales_repository.session.add(customer)
        self.sales_repository.session.commit()
        return customer.id

    def _ledger_for_invoice(self, invoice_id: int) -> list[CustomerBalanceLedger]:
        statement = (
            select(CustomerBalanceLedger)
            .where(CustomerBalanceLedger.ref_type == "INVOICE")
            .where(CustomerBalanceLedger.ref_id == invoice_id)
            .order_by(CustomerBalanceLedger.id.asc())
        )
        return list(self.sales_repository.session.scalars(statement).all())

    def _debt_ledgers_for_invoice(self, invoice_id: int) -> list[CustomerBalanceLedger]:
        statement = (
            select(CustomerBalanceLedger)
            .where(CustomerBalanceLedger.ref_type == "DEBT_PAYMENT")
            .where(CustomerBalanceLedger.event_type == "DEBT_PAYMENT")
            .where(CustomerBalanceLedger.source_ref_type == "INVOICE")
            .where(CustomerBalanceLedger.source_ref_id == invoice_id)
            .order_by(CustomerBalanceLedger.id.asc())
        )
        return list(self.sales_repository.session.scalars(statement).all())

    def test_walk_in_underpayment_fails_and_creates_no_invoice(self) -> None:
        with self.assertRaises(ValidationError):
            self.sales_service.create_invoice(
                customer_id=None,
                customer_snapshot_name="Khach le",
                invoice_datetime=datetime(2026, 4, 7, 9, 0, 0),
                items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
                paid_amount=Decimal("150"),
                payment_method=PaymentMethod.CASH,
            )

        self.assertEqual(len(self.sales_repository.list_invoices()), 0)
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))

    def test_walk_in_exact_payment_succeeds(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 7, 10, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
            payment_method=PaymentMethod.CASH,
        )

        self.assertEqual(invoice.customer_id, None)
        self.assertEqual(invoice.total_amount, Decimal("200"))
        self.assertEqual(invoice.paid_amount, Decimal("200"))
        self.assertEqual(len(invoice.items), 1)
        self.assertEqual(invoice.items[0].product_code_snapshot, "P-BAO")
        self.assertEqual(invoice.items[0].product_name_snapshot, "P-BAO")
        self.assertEqual(invoice.items[0].unit_price, Decimal("100"))
        self.assertEqual(invoice.items[0].line_total, Decimal("200"))
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("-2"))
        self.assertEqual(self._ledger_for_invoice(invoice.id), [])

    def test_invoice_decimal_quantity_keeps_fractional_stock_and_total(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 7, 10, 10, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("4.8")}],
            paid_amount=Decimal("480"),
            payment_method=PaymentMethod.CASH,
        )

        self.assertEqual(invoice.items[0].quantity, Decimal("4.8"))
        self.assertEqual(invoice.items[0].line_total, Decimal("480.0"))
        self.assertEqual(invoice.total_amount, Decimal("480.0"))
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("-4.8"))

    def test_invoice_decimal_bich_quantity_keeps_fractional_stock_and_total(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 7, 10, 12, 0),
            items=[{"product_id": self.bich_product_id, "unit_type": UnitType.BICH, "quantity": Decimal("4.8")}],
            paid_amount=Decimal("96"),
            payment_method=PaymentMethod.CASH,
        )

        self.assertEqual(invoice.items[0].quantity, Decimal("4.8"))
        self.assertEqual(invoice.total_amount, Decimal("96.0"))
        self.assertEqual(self.inventory_service.get_available_quantity(self.bich_product_id, UnitType.BICH), Decimal("-4.8"))

    def test_walk_in_overpayment_succeeds(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 7, 10, 30, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("250"),
            payment_method=PaymentMethod.CASH,
        )

        self.assertEqual(invoice.total_amount, Decimal("200"))
        self.assertEqual(invoice.paid_amount, Decimal("250"))
        self.assertEqual(self._ledger_for_invoice(invoice.id), [])

    def test_create_invoice_with_manually_overridden_unit_price(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 7, 10, 45, 0),
            items=[{
                "product_id": self.bao_product_id,
                "unit_type": UnitType.BAO,
                "quantity": Decimal("2"),
                "unit_price": Decimal("90"),
                "line_total": Decimal("180"),
            }],
            paid_amount=Decimal("180"),
            payment_method=PaymentMethod.CASH,
        )

        self.assertEqual(invoice.total_amount, Decimal("180"))
        self.assertEqual(invoice.items[0].unit_price, Decimal("90"))
        self.assertEqual(invoice.items[0].line_total, Decimal("180"))

    def test_create_invoice_with_manually_overridden_line_total(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 7, 10, 50, 0),
            items=[{
                "product_id": self.bao_product_id,
                "unit_type": UnitType.BAO,
                "quantity": Decimal("3"),
                "unit_price": Decimal("33"),
                "line_total": Decimal("100"),
            }],
            paid_amount=Decimal("100"),
            payment_method=PaymentMethod.CASH,
        )

        self.assertEqual(invoice.total_amount, Decimal("100"))
        self.assertEqual(invoice.items[0].unit_price, Decimal("33"))
        self.assertEqual(invoice.items[0].line_total, Decimal("100"))

    def test_customer_overpayment_with_overridden_line_total_still_uses_total_amount_for_balance(self) -> None:
        self.customer_service.adjust_balance(self.customer_id, Decimal("50"), "MANUAL", 2)
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 7, 10, 55, 0),
            items=[{
                "product_id": self.bao_product_id,
                "unit_type": UnitType.BAO,
                "quantity": Decimal("3"),
                "unit_price": Decimal("33"),
                "line_total": Decimal("100"),
            }],
            paid_amount=Decimal("150"),
            payment_method=PaymentMethod.CASH,
        )

        customer = self.customer_service.get_customer(self.customer_id)
        self.assertEqual(invoice.total_amount, Decimal("100"))
        self.assertEqual(customer.current_balance, Decimal("0"))
        self.assertEqual(invoice.paid_amount, Decimal("150"))

    def test_legacy_default_price_flow_still_works(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 7, 10, 58, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
            payment_method=PaymentMethod.CASH,
        )

        self.assertEqual(invoice.items[0].unit_price, Decimal("100"))
        self.assertEqual(invoice.items[0].line_total, Decimal("200"))

    def test_create_invoice_for_customer_partial_payment_updates_balance_and_sales(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="",
            invoice_datetime=datetime(2026, 4, 7, 11, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")}],
            paid_amount=Decimal("100"),
            payment_method=PaymentMethod.BANK_TRANSFER,
        )

        customer = self.customer_service.get_customer(self.customer_id)
        ledgers = self._ledger_for_invoice(invoice.id)
        debt_ledgers = self._debt_ledgers_for_invoice(invoice.id)
        self.assertEqual(invoice.total_amount, Decimal("300"))
        self.assertEqual(invoice.paid_amount, Decimal("100"))
        self.assertEqual(customer.current_balance, Decimal("200"))
        self.assertEqual(customer.total_sales, Decimal("300"))
        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].event_type, "INVOICE_CHARGE")
        self.assertEqual(ledgers[0].amount_delta, Decimal("300"))
        self.assertEqual(ledgers[0].balance_after, Decimal("300"))
        self.assertEqual(len(debt_ledgers), 1)
        self.assertEqual(debt_ledgers[0].amount_delta, Decimal("-100"))
        self.assertEqual(debt_ledgers[0].balance_after, Decimal("200"))
        self.assertEqual(debt_ledgers[0].source_ref_type, "INVOICE")
        self.assertEqual(debt_ledgers[0].source_ref_id, invoice.id)
        self.assertEqual(debt_ledgers[0].display_order, 20)

    def test_create_invoice_for_customer_overpayment_reduces_old_debt_or_goes_negative(self) -> None:
        self.customer_service.adjust_balance(self.customer_id, Decimal("50"), "MANUAL", 1)
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 7, 12, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("4")}],
            paid_amount=Decimal("500"),
            payment_method=PaymentMethod.CASH,
        )

        customer = self.customer_service.get_customer(self.customer_id)
        ledgers = self._ledger_for_invoice(invoice.id)
        self.assertEqual(invoice.total_amount, Decimal("400"))
        self.assertEqual(invoice.paid_amount, Decimal("500"))
        self.assertEqual(customer.current_balance, Decimal("-50"))
        self.assertEqual(customer.total_sales, Decimal("400"))
        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].amount_delta, Decimal("400"))
        debt_ledgers = list(self.customer_repository.list_ledgers_by_event_type(self.customer_id, "DEBT_PAYMENT"))
        self.assertEqual(len(debt_ledgers), 1)
        self.assertEqual(debt_ledgers[0].amount_delta, Decimal("-500"))
        self.assertEqual(debt_ledgers[0].balance_after, Decimal("-100"))

    def test_customer_overpayment_generates_separate_debt_payment_transaction(self) -> None:
        self.customer_service.adjust_balance(self.customer_id, Decimal("120"), "MANUAL", 3)

        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 7, 12, 30, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("250"),
            payment_method=PaymentMethod.CASH,
        )

        customer = self.customer_service.get_customer(self.customer_id)
        invoice_ledgers = self._ledger_for_invoice(invoice.id)
        debt_ledgers = list(self.customer_repository.list_ledgers_by_event_type(self.customer_id, "DEBT_PAYMENT"))
        self.assertEqual(invoice.total_amount, Decimal("200"))
        self.assertEqual(invoice.paid_amount, Decimal("250"))
        self.assertEqual(customer.current_balance, Decimal("70"))
        self.assertEqual(len(invoice_ledgers), 1)
        self.assertEqual(invoice_ledgers[0].amount_delta, Decimal("200"))
        self.assertEqual(invoice_ledgers[0].balance_after, Decimal("200"))
        self.assertEqual(len(debt_ledgers), 1)
        self.assertEqual(debt_ledgers[0].amount_delta, Decimal("-250"))
        self.assertEqual(debt_ledgers[0].balance_after, Decimal("-50"))
        self.assertEqual(debt_ledgers[0].source_ref_type, "INVOICE")
        self.assertEqual(debt_ledgers[0].source_ref_id, invoice.id)
        self.assertEqual(debt_ledgers[0].display_order, 20)

    def test_create_invoice_for_customer_exact_payment_generates_full_debt_payment(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 7, 12, 40, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("50")}],
            paid_amount=Decimal("5000"),
            payment_method=PaymentMethod.CASH,
        )

        invoice_ledgers = self._ledger_for_invoice(invoice.id)
        debt_ledgers = self._debt_ledgers_for_invoice(invoice.id)
        customer = self.customer_service.get_customer(self.customer_id)
        self.assertEqual(invoice.total_amount, Decimal("5000"))
        self.assertEqual(invoice.paid_amount, Decimal("5000"))
        self.assertEqual(customer.current_balance, Decimal("0"))
        self.assertEqual([(ledger.amount_delta, ledger.balance_after) for ledger in invoice_ledgers], [(Decimal("5000"), Decimal("5000"))])
        self.assertEqual([(ledger.amount_delta, ledger.balance_after) for ledger in debt_ledgers], [(Decimal("-5000"), Decimal("0"))])

    def test_create_invoice_for_customer_without_payment_generates_only_charge(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 7, 12, 45, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("50")}],
            paid_amount=Decimal("0"),
            payment_method=PaymentMethod.CASH,
        )

        customer = self.customer_service.get_customer(self.customer_id)
        self.assertEqual(invoice.total_amount, Decimal("5000"))
        self.assertEqual(invoice.paid_amount, Decimal("0"))
        self.assertEqual(customer.current_balance, Decimal("5000"))
        self.assertEqual([(ledger.amount_delta, ledger.balance_after) for ledger in self._ledger_for_invoice(invoice.id)], [(Decimal("5000"), Decimal("5000"))])
        self.assertEqual(self._debt_ledgers_for_invoice(invoice.id), [])

    def test_bao_kg_sale_by_kg_decreases_bao_stock_correctly(self) -> None:
        self.inventory_service.increase_stock(self.bao_product_id, Decimal("4"), UnitType.BAO)
        self.inventory_repository.session.commit()
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 7, 13, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.KG, "quantity": Decimal("50")}],
            paid_amount=Decimal("250"),
        )

        self.assertEqual(invoice.total_amount, Decimal("250"))
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("2"))

    def test_missing_enabled_price_raises_and_creates_no_invoice(self) -> None:
        with self.assertRaises(ValidationError):
            self.sales_service.create_invoice(
                customer_id=None,
                customer_snapshot_name="Khach le",
                invoice_datetime=datetime(2026, 4, 7, 14, 0, 0),
                items=[{"product_id": self.no_price_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1")}],
            )

        invoices = self.sales_repository.list_invoices()
        self.assertEqual(len(invoices), 0)

    def test_create_invoice_is_atomic_when_one_item_fails(self) -> None:
        starting_balance = self.customer_service.get_customer(self.customer_id).current_balance
        starting_sales = self.customer_service.get_customer(self.customer_id).total_sales
        with self.assertRaises(ValidationError):
            self.sales_service.create_invoice(
                customer_id=self.customer_id,
                customer_snapshot_name="Khach quen",
                invoice_datetime=datetime(2026, 4, 7, 15, 0, 0),
                items=[
                    {"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1")},
                    {"product_id": self.no_price_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1")},
                ],
                paid_amount=Decimal("10"),
            )

        invoices = self.sales_repository.list_invoices()
        customer_after = self.customer_service.get_customer(self.customer_id)
        self.assertEqual(len(invoices), 0)
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(customer_after.current_balance, starting_balance)
        self.assertEqual(customer_after.total_sales, starting_sales)

    def test_update_invoice_for_walk_in_keeps_code_and_datetime_and_reapplies_items(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 8, 9, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
        )

        updated = self.sales_service.update_invoice(
            invoice.id,
            items=[{"product_id": self.bich_product_id, "unit_type": UnitType.BICH, "quantity": Decimal("3")}],
            note="Updated walk-in",
        )

        self.assertEqual(updated.invoice_code, invoice.invoice_code)
        self.assertEqual(updated.invoice_datetime, invoice.invoice_datetime)
        self.assertEqual(updated.customer_id, None)
        self.assertEqual(updated.paid_amount, Decimal("200"))
        self.assertEqual(updated.total_amount, Decimal("60"))
        self.assertEqual(len(updated.items), 1)
        self.assertEqual(updated.items[0].product_id, self.bich_product_id)
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self.inventory_service.get_available_quantity(self.bich_product_id, UnitType.BICH), Decimal("-3"))
        self.assertEqual(self._ledger_for_invoice(invoice.id), [])

    def test_update_invoice_for_customer_rolls_back_and_applies_again(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 8, 10, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")}],
            paid_amount=Decimal("100"),
            payment_method=PaymentMethod.CASH,
        )

        updated = self.sales_service.update_invoice(
            invoice.id,
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("5")}],
            note="Updated customer invoice",
        )

        customer = self.customer_service.get_customer(self.customer_id)
        ledgers = self._ledger_for_invoice(invoice.id)
        debt_ledgers = self._debt_ledgers_for_invoice(invoice.id)
        self.assertEqual(updated.invoice_code, invoice.invoice_code)
        self.assertEqual(updated.invoice_datetime, invoice.invoice_datetime)
        self.assertEqual(updated.customer_id, self.customer_id)
        self.assertEqual(updated.payment_method, PaymentMethod.CASH)
        self.assertEqual(updated.paid_amount, Decimal("100"))
        self.assertEqual(updated.total_amount, Decimal("500"))
        self.assertEqual(customer.total_sales, Decimal("500"))
        self.assertEqual(customer.current_balance, Decimal("400"))
        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].event_type, "INVOICE_CHARGE")
        self.assertEqual(ledgers[0].amount_delta, Decimal("500"))
        self.assertEqual(len(debt_ledgers), 1)
        self.assertEqual(debt_ledgers[0].event_type, "DEBT_PAYMENT")
        self.assertEqual(debt_ledgers[0].amount_delta, Decimal("-100"))

    def test_update_invoice_decimal_quantity_reapplies_fractional_stock(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 8, 10, 2, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("5")}],
            paid_amount=Decimal("500"),
            payment_method=PaymentMethod.CASH,
        )

        updated = self.sales_service.update_invoice(
            invoice.id,
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("4.8")}],
            paid_amount=Decimal("480"),
        )

        self.assertEqual(updated.items[0].quantity, Decimal("4.8"))
        self.assertEqual(updated.total_amount, Decimal("480.0"))
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("-4.8"))

    def test_update_invoice_removes_generated_debt_payment_when_paid_amount_becomes_zero(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 8, 10, 5, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")}],
            paid_amount=Decimal("100"),
            payment_method=PaymentMethod.CASH,
        )
        self.assertEqual(len(self._debt_ledgers_for_invoice(invoice.id)), 1)

        updated = self.sales_service.update_invoice(
            invoice.id,
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")}],
            paid_amount=Decimal("0"),
        )

        customer = self.customer_service.get_customer(self.customer_id)
        self.assertEqual(updated.paid_amount, Decimal("0"))
        self.assertEqual(customer.current_balance, Decimal("300"))
        self.assertEqual([(ledger.amount_delta, ledger.balance_after) for ledger in self._ledger_for_invoice(invoice.id)], [(Decimal("300"), Decimal("300"))])
        self.assertEqual(self._debt_ledgers_for_invoice(invoice.id), [])

    def test_update_invoice_creates_generated_debt_payment_when_paid_amount_becomes_positive(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 8, 10, 8, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")}],
            paid_amount=Decimal("0"),
            payment_method=PaymentMethod.CASH,
        )
        self.assertEqual(self._debt_ledgers_for_invoice(invoice.id), [])

        updated = self.sales_service.update_invoice(
            invoice.id,
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")}],
            paid_amount=Decimal("100"),
        )

        customer = self.customer_service.get_customer(self.customer_id)
        debt_ledgers = self._debt_ledgers_for_invoice(invoice.id)
        self.assertEqual(updated.paid_amount, Decimal("100"))
        self.assertEqual(customer.current_balance, Decimal("200"))
        self.assertEqual([(ledger.amount_delta, ledger.balance_after) for ledger in self._ledger_for_invoice(invoice.id)], [(Decimal("300"), Decimal("300"))])
        self.assertEqual([(ledger.amount_delta, ledger.balance_after) for ledger in debt_ledgers], [(Decimal("-100"), Decimal("200"))])

    def test_update_invoice_with_edited_price_and_line_total(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 8, 10, 15, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
            payment_method=PaymentMethod.CASH,
        )

        updated = self.sales_service.update_invoice(
            invoice.id,
            items=[{
                "product_id": self.bao_product_id,
                "unit_type": UnitType.BAO,
                "quantity": Decimal("3"),
                "unit_price": Decimal("31"),
                "line_total": Decimal("95"),
            }],
            note="Manual pricing",
        )

        self.assertEqual(updated.total_amount, Decimal("95"))
        self.assertEqual(updated.items[0].unit_price, Decimal("31"))
        self.assertEqual(updated.items[0].line_total, Decimal("95"))

    def test_update_invoice_preserves_decimal_unit_price_without_rounding_to_integer(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 8, 10, 20, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
            payment_method=PaymentMethod.CASH,
        )

        updated = self.sales_service.update_invoice(
            invoice.id,
            items=[{
                "product_id": self.bao_product_id,
                "unit_type": UnitType.BAO,
                "quantity": Decimal("2"),
                "unit_price": Decimal("43.5"),
                "line_total": Decimal("87.0"),
            }],
            note="Decimal pricing",
        )

        self.assertEqual(updated.items[0].unit_price, Decimal("43.5"))
        self.assertEqual(updated.items[0].line_total, Decimal("87.0"))
        self.assertEqual(updated.total_amount, Decimal("87.0"))

    def test_update_invoice_is_atomic_when_new_apply_fails(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 8, 11, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("50"),
        )
        original_code = invoice.invoice_code
        original_datetime = invoice.invoice_datetime
        original_total = invoice.total_amount
        original_balance = self.customer_service.get_customer(self.customer_id).current_balance
        original_sales = self.customer_service.get_customer(self.customer_id).total_sales
        original_stock = self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO)

        with self.assertRaises(ValidationError):
            self.sales_service.update_invoice(
                invoice.id,
                items=[
                    {"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1")},
                    {"product_id": self.no_price_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1")},
                ],
            )

        reloaded = self.sales_repository.get_invoice(invoice.id)
        customer_after = self.customer_service.get_customer(self.customer_id)
        self.assertEqual(reloaded.invoice_code, original_code)
        self.assertEqual(reloaded.invoice_datetime, original_datetime)
        self.assertEqual(reloaded.total_amount, original_total)
        self.assertEqual(len(reloaded.items), 1)
        self.assertEqual(customer_after.current_balance, original_balance)
        self.assertEqual(customer_after.total_sales, original_sales)
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), original_stock)

    def test_update_invoice_datetime_syncs_invoice_and_source_linked_ledger_timestamps(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 8, 11, 30, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("260"),
            payment_method=PaymentMethod.CASH,
        )
        original_ledgers = [(ledger.event_type, ledger.amount_delta, ledger.balance_after) for ledger in self._ledger_for_invoice(invoice.id)]
        original_debt_ledgers = list(self.customer_repository.list_ledgers_by_event_type(self.customer_id, "DEBT_PAYMENT"))
        original_balance = self.customer_service.get_customer(self.customer_id).current_balance
        original_sales = self.customer_service.get_customer(self.customer_id).total_sales
        original_stock = self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO)
        self.assertEqual(len(original_debt_ledgers), 1)

        updated = self.sales_service.update_invoice_datetime(invoice.id, datetime(2026, 4, 9, 16, 45, 0))

        reloaded = self.sales_repository.get_invoice(invoice.id)
        updated_ledgers = [(ledger.event_type, ledger.amount_delta, ledger.balance_after) for ledger in self._ledger_for_invoice(invoice.id)]
        updated_debt_ledgers = list(self.customer_repository.list_ledgers_by_event_type(self.customer_id, "DEBT_PAYMENT"))
        customer = self.customer_service.get_customer(self.customer_id)
        self.assertEqual(updated.invoice_datetime, datetime(2026, 4, 9, 16, 45, 0))
        self.assertEqual(reloaded.invoice_datetime, datetime(2026, 4, 9, 16, 45, 0))
        self.assertEqual(reloaded.total_amount, invoice.total_amount)
        self.assertEqual(reloaded.paid_amount, invoice.paid_amount)
        self.assertEqual(len(reloaded.items), 1)
        self.assertEqual(customer.current_balance, original_balance)
        self.assertEqual(customer.total_sales, original_sales)
        self.assertEqual(updated_ledgers, original_ledgers)
        self.assertTrue(all(ledger.transaction_datetime == datetime(2026, 4, 9, 16, 45, 0) for ledger in self._ledger_for_invoice(invoice.id)))
        self.assertEqual(len(updated_debt_ledgers), 1)
        self.assertEqual(updated_debt_ledgers[0].transaction_datetime, datetime(2026, 4, 9, 16, 45, 0))
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), original_stock)

    def test_delete_invoice_for_walk_in_hard_deletes_and_restores_stock(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 8, 12, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
        )

        self.sales_service.delete_invoice(invoice.id)

        with self.assertRaises(NotFoundError):
            self.sales_repository.get_invoice(invoice.id)
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))

    def test_delete_invoice_for_customer_restores_balance_sales_and_removes_active_ledgers(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 8, 13, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")}],
            paid_amount=Decimal("100"),
        )

        self.sales_service.delete_invoice(invoice.id)

        customer = self.customer_service.get_customer(self.customer_id)
        with self.assertRaises(NotFoundError):
            self.sales_repository.get_invoice(invoice.id)
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(customer.current_balance, Decimal("0"))
        self.assertEqual(customer.total_sales, Decimal("0"))
        self.assertEqual(self._ledger_for_invoice(invoice.id), [])

    def test_delete_invoice_removes_generated_debt_payment(self) -> None:
        self.customer_service.adjust_balance(self.customer_id, Decimal("100"), "MANUAL", 91)
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 8, 13, 30, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("4")}],
            paid_amount=Decimal("460"),
            payment_method=PaymentMethod.CASH,
        )
        debt_ledgers = list(self.customer_repository.list_ledgers_by_event_type(self.customer_id, "DEBT_PAYMENT"))
        self.assertEqual(len(debt_ledgers), 1)
        self.assertEqual(debt_ledgers[0].source_ref_id, invoice.id)
        self.assertEqual(debt_ledgers[0].amount_delta, Decimal("-460"))
        self.assertEqual(self.customer_service.get_customer(self.customer_id).current_balance, Decimal("40"))

        self.sales_service.delete_invoice(invoice.id)

        customer = self.customer_service.get_customer(self.customer_id)
        self.assertEqual(customer.current_balance, Decimal("100"))
        self.assertEqual(customer.total_sales, Decimal("0"))
        self.assertEqual(self.customer_repository.list_ledgers_by_event_type(self.customer_id, "DEBT_PAYMENT"), [])

    def test_update_invoice_replaces_generated_debt_payment(self) -> None:
        self.customer_service.adjust_balance(self.customer_id, Decimal("100"), "MANUAL", 92)
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 8, 14, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("4")}],
            paid_amount=Decimal("460"),
            payment_method=PaymentMethod.CASH,
        )

        updated = self.sales_service.update_invoice(
            invoice.id,
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")}],
        )

        customer = self.customer_service.get_customer(self.customer_id)
        debt_ledgers = list(self.customer_repository.list_ledgers_by_event_type(self.customer_id, "DEBT_PAYMENT"))
        self.assertEqual(updated.total_amount, Decimal("300"))
        self.assertEqual(customer.current_balance, Decimal("-60"))
        self.assertEqual(len(debt_ledgers), 1)
        self.assertEqual(debt_ledgers[0].amount_delta, Decimal("-460"))
        self.assertEqual(debt_ledgers[0].source_ref_id, invoice.id)

    def test_delete_invoice_is_atomic_when_rollback_fails(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 8, 14, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
        )
        original_stock = self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO)
        original_increase = self.sales_service._inventory_service.increase_stock

        def failing_increase_stock(product_id: int, quantity: Decimal, unit_type: UnitType):
            raise ValidationError("forced rollback failure")

        self.sales_service._inventory_service.increase_stock = failing_increase_stock  # type: ignore[assignment]
        try:
            with self.assertRaises(ValidationError):
                self.sales_service.delete_invoice(invoice.id)
        finally:
            self.sales_service._inventory_service.increase_stock = original_increase  # type: ignore[assignment]

        reloaded = self.sales_repository.get_invoice(invoice.id)
        self.assertEqual(reloaded.id, invoice.id)
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), original_stock)

    def test_search_invoices_by_code_returns_matching_invoice_code(self) -> None:
        invoice_a = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 10, 9, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1")}],
            paid_amount=Decimal("100"),
            payment_method=PaymentMethod.CASH,
        )
        invoice_b = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 10, 10, 0, 0),
            items=[{"product_id": self.bich_product_id, "unit_type": UnitType.BICH, "quantity": Decimal("1")}],
            paid_amount=Decimal("20"),
            payment_method=PaymentMethod.CASH,
        )

        matches = list(self.sales_repository.search_invoices_by_code(invoice_a.invoice_code))

        self.assertEqual([invoice.id for invoice in matches], [invoice_a.id])
        self.assertNotIn(invoice_b.id, [invoice.id for invoice in matches])

    def test_return_controller_search_source_invoices_uses_invoice_code(self) -> None:
        invoice_a = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 4, 10, 11, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
            payment_method=PaymentMethod.CASH,
        )
        self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Nguoi khac",
            invoice_datetime=datetime(2026, 4, 10, 12, 0, 0),
            items=[{"product_id": self.bich_product_id, "unit_type": UnitType.BICH, "quantity": Decimal("1")}],
            paid_amount=Decimal("20"),
            payment_method=PaymentMethod.CASH,
        )

        rows = list(self.return_controller.search_source_invoices(invoice_a.invoice_code))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].invoice_id, invoice_a.id)
        self.assertEqual(rows[0].invoice_code, invoice_a.invoice_code)


if __name__ == "__main__":
    unittest.main()

