from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import PaymentMethod, ReturnHandlingMode, UnitMode, UnitType
from core.exceptions import ValidationError
from modules.customer.models import Customer, CustomerBalanceLedger
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.models import Product, ProductPrice
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.returns.models import ReturnInvoice
from modules.returns.repository import ReturnsRepository
from modules.returns.service import ReturnService
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService


class ReturnServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

        self.sales_repository = SalesRepository(self.Session)
        self.inventory_repository = InventoryRepository(self.Session)
        self.customer_repository = CustomerRepository(self.Session)
        self.returns_repository = ReturnsRepository(self.Session)

        self.inventory_service = InventoryService(self.inventory_repository)
        self.customer_service = CustomerService(self.customer_repository)
        self.sales_service = SalesService(
            self.sales_repository,
            inventory_service=self.inventory_service,
            customer_service=self.customer_service,
        )
        self.return_service = ReturnService(
            self.returns_repository,
            sales_repository=self.sales_repository,
            inventory_service=self.inventory_service,
            customer_service=self.customer_service,
        )

        self.bao_product_id = self._create_product_with_price("P-BAO", UnitMode.BAO_KG, [(UnitType.BAO, "100"), (UnitType.KG, "5")])
        self.bich_product_id = self._create_product_with_price("P-BICH", UnitMode.BICH, [(UnitType.BICH, "20")])
        self.customer_id = self._create_customer("Khach return")

    def tearDown(self) -> None:
        self.sales_repository.session.close()
        self.engine.dispose()

    def _create_product_with_price(self, code: str, unit_mode: UnitMode, prices: list[tuple[UnitType, str]]) -> int:
        session = self.sales_repository.session
        product = Product(product_code_base=code, product_name=code, unit_mode=unit_mode, is_active=True)
        session.add(product)
        session.flush()
        for unit_type, price in prices:
            session.add(ProductPrice(product_id=product.id, unit_type=unit_type, price=Decimal(price), is_enabled=True))
        session.commit()
        return product.id

    def _create_customer(self, name: str) -> int:
        customer = Customer(customer_name=name, phone=None, current_balance=Decimal("0"), total_sales=Decimal("0"))
        self.sales_repository.session.add(customer)
        self.sales_repository.session.commit()
        return customer.id

    def _ledger_for_return(self, return_id: int) -> list[CustomerBalanceLedger]:
        statement = (
            select(CustomerBalanceLedger)
            .where(CustomerBalanceLedger.ref_type == "RETURN")
            .where(CustomerBalanceLedger.ref_id == return_id)
            .order_by(CustomerBalanceLedger.id.asc())
        )
        return list(self.sales_repository.session.scalars(statement).all())

    def test_walk_in_return_refund_now_restores_stock_and_creates_no_ledger(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 9, 9, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
            payment_method=PaymentMethod.CASH,
        )
        source_item = invoice.items[0]

        return_invoice = self.return_service.create_return_invoice(
            source_invoice_id=invoice.id,
            return_datetime=datetime(2026, 4, 9, 10, 0, 0),
            items=[{"source_invoice_item_id": source_item.id, "quantity": Decimal("1")}],
            handling_mode=ReturnHandlingMode.REFUND_NOW,
        )

        self.assertTrue(return_invoice.return_code.startswith("TR"))
        self.assertEqual(return_invoice.total_amount, Decimal("100"))
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("-1"))
        self.assertEqual(self._ledger_for_return(return_invoice.id), [])

    def test_quick_return_walk_in_does_not_require_source_invoice_or_purchase_ceiling(self) -> None:
        return_invoice = self.return_service.create_quick_return_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            return_datetime=datetime(2026, 4, 9, 10, 30, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("5")}],
            handling_mode=ReturnHandlingMode.REFUND_NOW,
        )

        self.assertIsNone(return_invoice.source_invoice_id)
        self.assertTrue(return_invoice.is_quick_return)
        self.assertEqual(return_invoice.customer_snapshot_name, "Khach le")
        self.assertEqual(return_invoice.total_amount, Decimal("500"))
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("5"))
        self.assertEqual(self._ledger_for_return(return_invoice.id), [])

    def test_quick_return_customer_store_credit_updates_sales_balance_and_history(self) -> None:
        self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach return",
            invoice_datetime=datetime(2026, 4, 9, 10, 45, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("4")}],
            paid_amount=Decimal("0"),
        )

        return_invoice = self.return_service.create_quick_return_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach return",
            return_datetime=datetime(2026, 4, 9, 11, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            handling_mode=ReturnHandlingMode.STORE_CREDIT,
        )

        customer = self.customer_service.get_customer(self.customer_id)
        ledgers = self._ledger_for_return(return_invoice.id)
        self.assertTrue(return_invoice.is_quick_return)
        self.assertIsNone(return_invoice.source_invoice_id)
        self.assertEqual(return_invoice.customer_snapshot_name, "Khach return")
        self.assertEqual(return_invoice.total_amount, Decimal("200"))
        self.assertEqual(customer.total_sales, Decimal("200"))
        self.assertEqual(customer.current_balance, Decimal("200"))
        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].event_type, "RETURN_STORE_CREDIT")
        self.assertEqual(ledgers[0].amount_delta, Decimal("-200"))

    def test_customer_return_store_credit_reduces_sales_and_balance_and_can_go_negative(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach return",
            invoice_datetime=datetime(2026, 4, 9, 11, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")}],
            paid_amount=Decimal("50"),
        )
        source_item = invoice.items[0]

        return_invoice = self.return_service.create_return_invoice(
            source_invoice_id=invoice.id,
            return_datetime=datetime(2026, 4, 9, 12, 0, 0),
            items=[{"source_invoice_item_id": source_item.id, "quantity": Decimal("3")}],
            handling_mode=ReturnHandlingMode.STORE_CREDIT,
        )

        customer = self.customer_service.get_customer(self.customer_id)
        ledgers = self._ledger_for_return(return_invoice.id)
        self.assertEqual(return_invoice.total_amount, Decimal("300"))
        self.assertEqual(customer.total_sales, Decimal("0"))
        self.assertEqual(customer.current_balance, Decimal("-50"))
        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].event_type, "RETURN_STORE_CREDIT")
        self.assertEqual(ledgers[0].amount_delta, Decimal("-300"))

    def test_customer_return_refund_now_never_pushes_balance_below_zero_due_only_to_refund(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach return",
            invoice_datetime=datetime(2026, 4, 9, 13, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("4")}],
            paid_amount=Decimal("100"),
        )
        source_item = invoice.items[0]

        return_invoice = self.return_service.create_return_invoice(
            source_invoice_id=invoice.id,
            return_datetime=datetime(2026, 4, 9, 14, 0, 0),
            items=[{"source_invoice_item_id": source_item.id, "quantity": Decimal("4")}],
            handling_mode=ReturnHandlingMode.REFUND_NOW,
        )

        customer = self.customer_service.get_customer(self.customer_id)
        ledgers = self._ledger_for_return(return_invoice.id)
        self.assertEqual(return_invoice.total_amount, Decimal("400"))
        self.assertEqual(customer.total_sales, Decimal("0"))
        self.assertEqual(customer.current_balance, Decimal("0"))
        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].event_type, "RETURN_REFUND_NOW")
        self.assertEqual(ledgers[0].amount_delta, Decimal("-300"))

    def test_return_quantity_cannot_exceed_remaining_quantity(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 9, 15, 0, 0),
            items=[{"product_id": self.bich_product_id, "unit_type": UnitType.BICH, "quantity": Decimal("5")}],
            paid_amount=Decimal("100"),
        )
        source_item = invoice.items[0]
        self.return_service.create_return_invoice(
            source_invoice_id=invoice.id,
            return_datetime=datetime(2026, 4, 9, 16, 0, 0),
            items=[{"source_invoice_item_id": source_item.id, "quantity": Decimal("3")}],
            handling_mode=ReturnHandlingMode.REFUND_NOW,
        )

        with self.assertRaises(ValidationError):
            self.return_service.create_return_invoice(
                source_invoice_id=invoice.id,
                return_datetime=datetime(2026, 4, 9, 17, 0, 0),
                items=[{"source_invoice_item_id": source_item.id, "quantity": Decimal("3")}],
                handling_mode=ReturnHandlingMode.REFUND_NOW,
            )

    def test_source_invoice_item_must_belong_to_source_invoice(self) -> None:
        invoice_a = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach A",
            invoice_datetime=datetime(2026, 4, 9, 18, 0, 0),
            items=[{"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1")}],
            paid_amount=Decimal("100"),
        )
        invoice_b = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach B",
            invoice_datetime=datetime(2026, 4, 9, 18, 5, 0),
            items=[{"product_id": self.bich_product_id, "unit_type": UnitType.BICH, "quantity": Decimal("1")}],
            paid_amount=Decimal("20"),
        )

        with self.assertRaises(ValidationError):
            self.return_service.create_return_invoice(
                source_invoice_id=invoice_a.id,
                return_datetime=datetime(2026, 4, 9, 19, 0, 0),
                items=[{"source_invoice_item_id": invoice_b.items[0].id, "quantity": Decimal("1")}],
                handling_mode=ReturnHandlingMode.REFUND_NOW,
            )

    def test_return_creation_is_atomic_when_one_item_fails(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach return",
            invoice_datetime=datetime(2026, 4, 9, 20, 0, 0),
            items=[
                {"product_id": self.bao_product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")},
                {"product_id": self.bich_product_id, "unit_type": UnitType.BICH, "quantity": Decimal("1")},
            ],
            paid_amount=Decimal("50"),
        )
        initial_balance_bao = self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO)
        initial_balance_bich = self.inventory_service.get_available_quantity(self.bich_product_id, UnitType.BICH)
        customer_before = self.customer_service.get_customer(self.customer_id)

        with self.assertRaises(ValidationError):
            self.return_service.create_return_invoice(
                source_invoice_id=invoice.id,
                return_datetime=datetime(2026, 4, 9, 21, 0, 0),
                items=[
                    {"source_invoice_item_id": invoice.items[0].id, "quantity": Decimal("1")},
                    {"source_invoice_item_id": invoice.items[1].id, "quantity": Decimal("2")},
                ],
                handling_mode=ReturnHandlingMode.STORE_CREDIT,
            )

        return_invoices = self.returns_repository.list_return_invoices()
        customer_after = self.customer_service.get_customer(self.customer_id)
        self.assertEqual(len(return_invoices), 0)
        self.assertEqual(self.inventory_service.get_available_quantity(self.bao_product_id, UnitType.BAO), initial_balance_bao)
        self.assertEqual(self.inventory_service.get_available_quantity(self.bich_product_id, UnitType.BICH), initial_balance_bich)
        self.assertEqual(customer_after.current_balance, customer_before.current_balance)
        self.assertEqual(customer_after.total_sales, customer_before.total_sales)


if __name__ == "__main__":
    unittest.main()

