from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import UnitMode, UnitType
from modules.customer.models import Customer, CustomerBalanceLedger
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.models import Product, ProductPrice
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.orders.models import OrderRequest
from modules.orders.repository import OrderRepository
from modules.orders.service import OrderService
import modules.returns.models  # noqa: F401
from modules.sales.models import Invoice
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService


class OrderServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.order_repository = OrderRepository(self.Session)
        self.order_service = OrderService(self.order_repository)
        self.inventory_repository = InventoryRepository(self.Session)
        self.inventory_service = InventoryService(self.inventory_repository)
        self.customer_repository = CustomerRepository(self.Session)
        self.customer_service = CustomerService(self.customer_repository)
        self.sales_repository = SalesRepository(self.Session)
        self.sales_service = SalesService(
            self.sales_repository,
            inventory_service=self.inventory_service,
            customer_service=self.customer_service,
        )
        self.product_id = self._create_product()
        self.customer_id = self._create_customer()

    def tearDown(self) -> None:
        self.order_repository.session.close()
        self.inventory_repository.session.close()
        self.customer_repository.session.close()
        self.sales_repository.session.close()
        self.engine.dispose()

    def test_create_order_does_not_touch_inventory_invoice_or_ledger(self) -> None:
        order = self._create_order(quantity=Decimal("3"))

        self.assertEqual(order.status, "OPEN")
        self.assertEqual(self.inventory_service.get_available_quantity(self.product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self.sales_repository.session.scalars(select(Invoice)).all(), [])
        self.assertEqual(self.customer_repository.session.scalars(select(CustomerBalanceLedger)).all(), [])
        self.assertEqual([item.quantity for item in order.items], [Decimal("3")])

    def test_order_can_exceed_current_stock_without_changing_stock(self) -> None:
        order = self._create_order(quantity=Decimal("999"))

        self.assertEqual(order.items[0].quantity, Decimal("999"))
        self.assertEqual(self.inventory_service.get_available_quantity(self.product_id, UnitType.BAO), Decimal("0"))

    def test_order_keeps_decimal_quantity_without_inventory_effect(self) -> None:
        order = self._create_order(quantity=Decimal("4.8"))
        summary = self.order_service.list_active_quantity_summary()

        self.assertEqual(order.items[0].quantity, Decimal("4.8"))
        self.assertEqual(summary[0].quantity, Decimal("4.8"))
        self.assertEqual(summary[0].stock_available, Decimal("0"))
        self.assertEqual(self.inventory_service.get_available_quantity(self.product_id, UnitType.BAO), Decimal("0"))

    def test_prepared_orders_stay_active_and_sort_before_open_orders(self) -> None:
        open_order = self._create_order(code_suffix_time=datetime(2026, 4, 10, 9, 0, 0))
        prepared_order = self._create_order(code_suffix_time=datetime(2026, 4, 10, 10, 0, 0))

        self.order_service.mark_prepared(prepared_order.id, True)

        rows = list(self.order_service.list_active_orders())
        self.assertEqual([row.id for row in rows], [prepared_order.id, open_order.id])
        self.assertEqual(rows[0].status, "PREPARED")

    def test_convert_order_after_sales_invoice_hides_order_and_applies_sales_effects(self) -> None:
        order = self._create_order(quantity=Decimal("2"))

        active_before = [row.id for row in self.order_service.list_active_orders()]
        self.assertIn(order.id, active_before)

        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach A",
            invoice_datetime=datetime(2026, 4, 10, 11, 0, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("50"),
        )
        self.order_service.mark_converted(order.id, invoice.id)

        active_after = [row.id for row in self.order_service.list_active_orders()]
        self.assertNotIn(order.id, active_after)
        self.assertEqual(self.inventory_service.get_available_quantity(self.product_id, UnitType.BAO), Decimal("-2"))
        self.assertEqual(self.customer_service.get_customer(self.customer_id).current_balance, Decimal("150"))
        converted = self.order_service.get_order(order.id)
        self.assertEqual(converted.status, "CONVERTED")
        self.assertEqual(converted.source_invoice_id, invoice.id)

    def test_update_order_changes_items_without_business_effects(self) -> None:
        order = self._create_order(quantity=Decimal("2"))

        updated = self.order_service.update_order(
            order.id,
            customer_id=self.customer_id,
            customer_name_snapshot="Khach A",
            order_datetime=datetime(2026, 4, 11, 9, 0, 0),
            required_delivery_datetime=datetime(2026, 4, 12, 9, 0, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("5")}],
            note="Updated",
        )

        self.assertEqual(updated.items[0].quantity, Decimal("5"))
        self.assertEqual(updated.note, "Updated")
        self.assertEqual(self.inventory_service.get_available_quantity(self.product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self.customer_repository.session.scalars(select(CustomerBalanceLedger)).all(), [])

    def test_delete_order_removes_it_without_business_effects(self) -> None:
        order = self._create_order(quantity=Decimal("2"))

        self.order_service.delete_order(order.id)

        self.assertEqual(self.order_service.list_active_orders(), [])
        self.assertEqual(self.inventory_service.get_available_quantity(self.product_id, UnitType.BAO), Decimal("0"))
        self.assertEqual(self.customer_service.get_customer(self.customer_id).current_balance, Decimal("0"))

    def test_walk_in_order_uses_walk_in_snapshot(self) -> None:
        order = self.order_service.create_order(
            customer_id=None,
            customer_name_snapshot="",
            order_datetime=datetime(2026, 4, 10, 9, 0, 0),
            required_delivery_datetime=None,
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1")}],
        )

        self.assertIsNone(order.customer_id)
        self.assertEqual(order.customer_name_snapshot, "Khách lẻ")

    def _create_product(self) -> int:
        session = self.inventory_repository.session
        product = Product(product_code_base="P001", product_name="Gao", unit_mode=UnitMode.BAO_KG, is_active=True)
        session.add(product)
        session.flush()
        session.add(ProductPrice(product_id=product.id, unit_type=UnitType.BAO, price=Decimal("100"), is_enabled=True))
        session.commit()
        return product.id

    def _create_customer(self) -> int:
        session = self.customer_repository.session
        customer = Customer(customer_name="Khach A", current_balance=Decimal("0"), total_sales=Decimal("0"))
        session.add(customer)
        session.commit()
        return customer.id

    def _create_order(
        self,
        *,
        quantity: Decimal = Decimal("1"),
        code_suffix_time: datetime = datetime(2026, 4, 10, 9, 0, 0),
    ) -> OrderRequest:
        return self.order_service.create_order(
            customer_id=self.customer_id,
            customer_name_snapshot="Khach A",
            order_datetime=code_suffix_time,
            required_delivery_datetime=None,
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": quantity}],
            note="Can giao som",
        )


if __name__ == "__main__":
    unittest.main()
