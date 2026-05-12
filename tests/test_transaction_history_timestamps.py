from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import PaymentMethod, ReturnHandlingMode, UnitMode, UnitType
from modules.customer.models import Customer
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.models import Product, ProductPrice
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.returns.repository import ReturnsRepository
from modules.returns.service import ReturnService
from modules.sales.controller import SalesController
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService
import modules.returns.models  # noqa: F401


class TransactionHistoryTimestampTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

        self.customer_repository = CustomerRepository(self.Session)
        self.sales_repository = SalesRepository(self.Session)
        self.inventory_repository = InventoryRepository(self.Session)
        self.returns_repository = ReturnsRepository(self.Session)

        self.customer_service = CustomerService(self.customer_repository)
        self.inventory_service = InventoryService(self.inventory_repository)
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
        self.sales_controller = SalesController(self.Session)

        self.product_id = self._create_product_with_price("P-BAO", UnitMode.BAO_KG, [(UnitType.BAO, "100")])
        self.customer_id = self._create_customer("Khach lich su")

    def tearDown(self) -> None:
        self.customer_repository.session.close()
        self.sales_repository.session.close()
        self.inventory_repository.session.close()
        self.returns_repository.session.close()
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
        customer = Customer(customer_name=name, phone="0909", address="123", current_balance=Decimal("0"), total_sales=Decimal("0"))
        self.sales_repository.session.add(customer)
        self.sales_repository.session.commit()
        return customer.id

    def test_transaction_history_uses_business_datetime_for_all_transaction_types(self) -> None:
        invoice_datetime = datetime(2026, 4, 10, 9, 0, 0)
        debt_payment_datetime = datetime(2026, 4, 10, 9, 30, 0)
        return_datetime = datetime(2026, 4, 10, 10, 0, 0)

        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=invoice_datetime,
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")}],
            paid_amount=Decimal("100"),
            payment_method=PaymentMethod.CASH,
        )
        debt_payment = self.customer_service.pay_debt(
            self.customer_id,
            Decimal("25"),
            note="Khach tra no",
            payment_datetime=debt_payment_datetime,
        )
        return_invoice = self.return_service.create_return_invoice(
            source_invoice_id=invoice.id,
            return_datetime=return_datetime,
            items=[{"source_invoice_item_id": invoice.items[0].id, "quantity": Decimal("1")}],
            handling_mode=ReturnHandlingMode.REFUND_NOW,
        )

        rows = self.sales_controller.list_transaction_history(sort_option="newest")

        transaction_rows = [row for row in rows if row.transaction_code in {invoice.invoice_code, return_invoice.return_code, str(debt_payment.ref_id)}]

        self.assertEqual(
            [(row.transaction_type, row.transaction_datetime) for row in transaction_rows],
            [
                ("RETURN", return_datetime),
                ("DEBT_PAYMENT", debt_payment_datetime),
                ("INVOICE", invoice_datetime),
            ],
        )

    def test_transaction_history_reorders_after_source_timestamps_are_edited(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=datetime(2026, 4, 10, 9, 0, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("50"),
            payment_method=PaymentMethod.CASH,
        )
        debt_payment = self.customer_service.pay_debt(
            self.customer_id,
            Decimal("10"),
            payment_datetime=datetime(2026, 4, 10, 9, 30, 0),
        )
        return_invoice = self.return_service.create_return_invoice(
            source_invoice_id=invoice.id,
            return_datetime=datetime(2026, 4, 10, 10, 0, 0),
            items=[{"source_invoice_item_id": invoice.items[0].id, "quantity": Decimal("1")}],
            handling_mode=ReturnHandlingMode.REFUND_NOW,
        )

        self.sales_service.update_invoice_datetime(invoice.id, datetime(2026, 4, 10, 12, 0, 0))
        self.return_service.update_return_datetime(return_invoice.id, datetime(2026, 4, 10, 8, 0, 0))
        self.customer_service.update_debt_payment_datetime(debt_payment.id, datetime(2026, 4, 10, 11, 0, 0))

        rows = self.sales_controller.list_transaction_history(sort_option="newest")
        transaction_rows = [row for row in rows if row.transaction_code in {invoice.invoice_code, return_invoice.return_code, str(debt_payment.ref_id)}]

        self.assertEqual(
            [(row.transaction_type, row.transaction_datetime) for row in transaction_rows],
            [
                ("INVOICE", datetime(2026, 4, 10, 12, 0, 0)),
                ("DEBT_PAYMENT", datetime(2026, 4, 10, 11, 0, 0)),
                ("RETURN", datetime(2026, 4, 10, 8, 0, 0)),
            ],
        )

    def test_transaction_history_search_matches_customer_name_only(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=datetime(2026, 4, 10, 9, 0, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1")}],
            paid_amount=Decimal("100"),
            payment_method=PaymentMethod.CASH,
        )

        rows_by_name = self.sales_controller.list_transaction_history(query="Khach lich")
        rows_by_code = self.sales_controller.list_transaction_history(query=invoice.invoice_code)
        rows_by_phone = self.sales_controller.list_transaction_history(query="0909")

        self.assertTrue(any(row.transaction_id == invoice.id for row in rows_by_name))
        self.assertFalse(any(row.transaction_id == invoice.id for row in rows_by_code))
        self.assertFalse(any(row.transaction_id == invoice.id for row in rows_by_phone))

    def test_transaction_history_uses_batch_order_direction_for_overpayment_when_same_datetime(self) -> None:
        self.customer_service.adjust_balance(
            self.customer_id,
            Decimal("22000000"),
            "MANUAL",
            12,
            transaction_datetime=datetime(2026, 4, 10, 13, 0, 0),
        )
        shared_datetime = datetime(2026, 4, 10, 14, 0, 0)
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=shared_datetime,
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("340000")}],
            paid_amount=Decimal("56000000"),
            payment_method=PaymentMethod.CASH,
        )

        rows = self.sales_controller.list_transaction_history(sort_option="newest")
        paired_rows = [row for row in rows if row.transaction_datetime == shared_datetime][:2]

        self.assertEqual(
            [(row.transaction_type, row.amount) for row in paired_rows],
            [
                ("DEBT_PAYMENT", Decimal("56000000")),
                ("INVOICE", invoice.total_amount),
            ],
        )
        self.assertEqual(paired_rows[0].source_ref_type, "INVOICE")
        self.assertEqual(paired_rows[0].source_ref_id, invoice.id)

        oldest_rows = self.sales_controller.list_transaction_history(sort_option="oldest")
        oldest_pair = [row for row in oldest_rows if row.transaction_datetime == shared_datetime][:2]
        self.assertEqual(
            [(row.transaction_type, row.amount) for row in oldest_pair],
            [
                ("INVOICE", invoice.total_amount),
                ("DEBT_PAYMENT", Decimal("56000000")),
            ],
        )


if __name__ == "__main__":
    unittest.main()
