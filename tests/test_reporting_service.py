from __future__ import annotations

from datetime import date, datetime
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
from modules.reporting.repository import ReportingRepository
from modules.reporting.service import ReportingService
from modules.returns.repository import ReturnsRepository
from modules.returns.service import ReturnService
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService


class ReportingServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

        self.sales_repository = SalesRepository(self.Session)
        self.inventory_repository = InventoryRepository(self.Session)
        self.customer_repository = CustomerRepository(self.Session)
        self.returns_repository = ReturnsRepository(self.Session)
        self.reporting_repository = ReportingRepository(self.Session)

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
        self.reporting_service = ReportingService(self.reporting_repository)

        self.product_bao_id = self._create_product_with_price("P-BAO", UnitMode.BAO_KG, [(UnitType.BAO, "100"), (UnitType.KG, "5")])
        self.product_bich_id = self._create_product_with_price("P-BICH", UnitMode.BICH, [(UnitType.BICH, "20")])
        self.customer_id = self._create_customer("Khach report")

        self._seed_transactions()

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

    def _seed_transactions(self) -> None:
        invoice_walk_in = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 10, 9, 0, 0),
            items=[
                {"product_id": self.product_bao_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")},
                {"product_id": self.product_bao_id, "unit_type": UnitType.KG, "quantity": Decimal("25")},
            ],
            paid_amount=Decimal("325"),
            payment_method=PaymentMethod.CASH,
        )
        self.invoice_walk_in = invoice_walk_in

        invoice_customer = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="",
            invoice_datetime=datetime(2026, 4, 10, 15, 0, 0),
            items=[
                {"product_id": self.product_bich_id, "unit_type": UnitType.BICH, "quantity": Decimal("10")},
            ],
            paid_amount=Decimal("50"),
            payment_method=PaymentMethod.BANK_TRANSFER,
        )
        self.invoice_customer = invoice_customer

        invoice_day_two = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=datetime(2026, 4, 11, 11, 0, 0),
            items=[
                {"product_id": self.product_bao_id, "unit_type": UnitType.BAO, "quantity": Decimal("1")},
            ],
            paid_amount=Decimal("100"),
            payment_method=PaymentMethod.CASH,
        )
        self.invoice_day_two = invoice_day_two

        self.return_walk_in = self.return_service.create_return_invoice(
            source_invoice_id=invoice_walk_in.id,
            return_datetime=datetime(2026, 4, 10, 17, 0, 0),
            items=[
                {"source_invoice_item_id": invoice_walk_in.items[1].id, "quantity": Decimal("10")},
            ],
            handling_mode=ReturnHandlingMode.REFUND_NOW,
        )

        self.return_customer = self.return_service.create_return_invoice(
            source_invoice_id=invoice_customer.id,
            return_datetime=datetime(2026, 4, 11, 13, 0, 0),
            items=[
                {"source_invoice_item_id": invoice_customer.items[0].id, "quantity": Decimal("2")},
            ],
            handling_mode=ReturnHandlingMode.STORE_CREDIT,
        )

    def test_sales_summary_includes_walk_in_and_customer_invoices(self) -> None:
        summary = self.reporting_service.get_sales_summary(
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 4, 10, 23, 59, 59),
        )
        self.assertEqual(summary.gross_sales_amount, Decimal("525"))
        self.assertEqual(summary.invoice_count, 2)

    def test_returns_reduce_net_revenue(self) -> None:
        summary = self.reporting_service.get_sales_summary(
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 4, 11, 23, 59, 59),
        )
        self.assertEqual(summary.gross_sales_amount, Decimal("625"))
        self.assertEqual(summary.return_amount, Decimal("90"))
        self.assertEqual(summary.net_revenue, Decimal("535"))
        self.assertEqual(summary.return_count, 2)

    def test_top_products_grouped_by_product_and_unit_type(self) -> None:
        rows = self.reporting_service.get_top_products(
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 4, 11, 23, 59, 59),
            sort_by="revenue",
            limit=10,
        )
        bao_rows = [row for row in rows if row.product_id == self.product_bao_id]
        self.assertEqual(len(bao_rows), 2)
        self.assertEqual({row.unit_type for row in bao_rows}, {"BAO", "KG"})

    def test_top_products_sorted_by_revenue(self) -> None:
        rows = self.reporting_service.get_top_products(
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 4, 11, 23, 59, 59),
            sort_by="revenue",
            limit=3,
        )
        self.assertEqual(rows[0].product_id, self.product_bao_id)
        self.assertEqual(rows[0].unit_type, "BAO")
        self.assertEqual(rows[0].net_revenue, Decimal("300"))

    def test_top_products_sorted_by_quantity(self) -> None:
        rows = self.reporting_service.get_top_products(
            datetime(2026, 4, 10, 0, 0, 0),
            datetime(2026, 4, 11, 23, 59, 59),
            sort_by="quantity",
            limit=3,
        )
        self.assertEqual(rows[0].product_id, self.product_bao_id)
        self.assertEqual(rows[0].unit_type, "KG")
        self.assertEqual(rows[0].net_quantity, Decimal("15"))

    def test_revenue_timeseries_by_day(self) -> None:
        points = self.reporting_service.get_revenue_timeseries(
            date(2026, 4, 10),
            date(2026, 4, 11),
        )
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].bucket_date, date(2026, 4, 10))
        self.assertEqual(points[0].gross_sales_amount, Decimal("525"))
        self.assertEqual(points[0].return_amount, Decimal("50"))
        self.assertEqual(points[0].net_revenue, Decimal("475"))
        self.assertEqual(points[1].bucket_date, date(2026, 4, 11))
        self.assertEqual(points[1].gross_sales_amount, Decimal("100"))
        self.assertEqual(points[1].return_amount, Decimal("40"))
        self.assertEqual(points[1].net_revenue, Decimal("60"))

    def test_preset_range_helper(self) -> None:
        now = datetime(2026, 4, 11, 15, 0, 0)
        today_range = self.reporting_service.resolve_preset_range("today", now=now)
        yesterday_range = self.reporting_service.resolve_preset_range("yesterday", now=now)
        last_7_days = self.reporting_service.resolve_preset_range("last_7_days", now=now)

        self.assertEqual(today_range.start_datetime.date(), date(2026, 4, 11))
        self.assertEqual(yesterday_range.start_datetime.date(), date(2026, 4, 10))
        self.assertEqual(last_7_days.start_datetime.date(), date(2026, 4, 5))
        self.assertEqual(last_7_days.end_datetime.date(), date(2026, 4, 11))


if __name__ == "__main__":
    unittest.main()
