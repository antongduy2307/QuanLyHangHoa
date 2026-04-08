from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import PaymentMethod, UnitMode, UnitType
from core.exceptions import ValidationError
from modules.customer.models import Customer
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.models import InventoryBalance, Product, ProductPrice
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService
import modules.returns.models  # noqa: F401
import modules.sales.models  # noqa: F401


class InventoryServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.repository = InventoryRepository(self.Session)
        self.service = InventoryService(self.repository)
        self.customer_service = CustomerService(CustomerRepository(self.Session))
        self.sales_service = SalesService(
            SalesRepository(self.Session),
            inventory_service=InventoryService(InventoryRepository(self.Session)),
            customer_service=self.customer_service,
        )

        self.bao_product_id = self._create_product("P-BAO", UnitMode.BAO_KG)
        self.bich_product_id = self._create_product("P-BICH", UnitMode.BICH)
        self.customer_id = self._create_customer("Customer A")

    def tearDown(self) -> None:
        self.repository.session.close()
        self.engine.dispose()

    def _create_product(self, code: str, unit_mode: UnitMode) -> int:
        product = Product(product_code_base=code, product_name=code, unit_mode=unit_mode)
        self.repository.session.add(product)
        self.repository.session.flush()
        return product.id

    def _create_customer(self, name: str) -> int:
        customer = Customer(customer_name=name, phone=None, current_balance=Decimal("0"), total_sales=Decimal("0"))
        self.repository.session.add(customer)
        self.repository.session.flush()
        return customer.id

    def test_create_product_bao_only(self) -> None:
        product = self.service.create_product(
            product_code_base="NEW-BAO",
            product_name="Bao only",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.BAO: Decimal("100")},
        )
        self.repository.session.commit()
        self.assertEqual(product.unit_mode, UnitMode.BAO_KG)
        prices = self.repository.session.scalars(select(ProductPrice).where(ProductPrice.product_id == product.id)).all()
        self.assertEqual(len(prices), 1)
        self.assertEqual(prices[0].unit_type, UnitType.BAO)
        balance = self.service.get_balance(product.id)
        self.assertEqual(balance.on_hand_bao_decimal, Decimal("0"))

    def test_create_product_kg_only(self) -> None:
        product = self.service.create_product(
            product_code_base="NEW-KG",
            product_name="Kg only",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.KG: Decimal("5")},
        )
        self.repository.session.commit()
        prices = self.repository.session.scalars(select(ProductPrice).where(ProductPrice.product_id == product.id)).all()
        self.assertEqual(len(prices), 1)
        self.assertEqual(prices[0].unit_type, UnitType.KG)

    def test_create_product_bao_and_kg(self) -> None:
        product = self.service.create_product(
            product_code_base="NEW-BOTH",
            product_name="Both units",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.BAO: Decimal("100"), UnitType.KG: Decimal("5")},
        )
        self.repository.session.commit()
        prices = self.repository.session.scalars(select(ProductPrice).where(ProductPrice.product_id == product.id)).all()
        self.assertEqual(len(prices), 2)
        self.assertEqual({price.unit_type for price in prices}, {UnitType.BAO, UnitType.KG})

    def test_create_product_bich(self) -> None:
        product = self.service.create_product(
            product_code_base="NEW-BICH",
            product_name="Bich item",
            unit_mode=UnitMode.BICH,
            enabled_prices={UnitType.BICH: Decimal("20")},
        )
        self.repository.session.commit()
        balance = self.service.get_balance(product.id)
        self.assertEqual(balance.on_hand_bich_integer, 0)

    def test_create_product_invalid_unit_or_price_fails(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.create_product(
                product_code_base="BAD1",
                product_name="Bad",
                unit_mode=UnitMode.BICH,
                enabled_prices={UnitType.BAO: Decimal("100")},
            )
        with self.assertRaises(ValidationError):
            self.service.create_product(
                product_code_base="BAD2",
                product_name="Bad",
                unit_mode=UnitMode.BAO_KG,
                enabled_prices={UnitType.KG: Decimal("0")},
            )

    def test_update_product_name(self) -> None:
        product = self.service.create_product(
            product_code_base="UP-NAME",
            product_name="Old name",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.BAO: Decimal("10")},
        )
        self.repository.session.commit()

        updated = self.service.update_product(
            product.id,
            product_name="New name",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.BAO: Decimal("10")},
        )
        self.repository.session.commit()
        self.assertEqual(updated.product_name, "New name")

    def test_update_bao_only_to_bao_and_kg(self) -> None:
        product = self.service.create_product(
            product_code_base="UP-BAO",
            product_name="Bao only",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.BAO: Decimal("10")},
        )
        self.repository.session.commit()

        self.service.update_product(
            product.id,
            product_name="Bao and Kg",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.BAO: Decimal("12"), UnitType.KG: Decimal("3")},
        )
        self.repository.session.commit()
        prices = {price.unit_type: price for price in self.repository.session.scalars(select(ProductPrice).where(ProductPrice.product_id == product.id)).all()}
        self.assertTrue(prices[UnitType.BAO].is_enabled)
        self.assertTrue(prices[UnitType.KG].is_enabled)
        self.assertEqual(prices[UnitType.KG].price, Decimal("3"))

    def test_update_bao_and_kg_to_kg_only(self) -> None:
        product = self.service.create_product(
            product_code_base="UP-KGONLY",
            product_name="Both units",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.BAO: Decimal("12"), UnitType.KG: Decimal("3")},
        )
        self.repository.session.commit()

        self.service.update_product(
            product.id,
            product_name="Kg only",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.KG: Decimal("4")},
        )
        self.repository.session.commit()
        prices = {price.unit_type: price for price in self.repository.session.scalars(select(ProductPrice).where(ProductPrice.product_id == product.id)).all()}
        self.assertFalse(prices[UnitType.BAO].is_enabled)
        self.assertTrue(prices[UnitType.KG].is_enabled)
        self.assertEqual(prices[UnitType.KG].price, Decimal("4"))

    def test_update_bich_price(self) -> None:
        product = self.service.create_product(
            product_code_base="UP-BICH",
            product_name="Bich item",
            unit_mode=UnitMode.BICH,
            enabled_prices={UnitType.BICH: Decimal("20")},
        )
        self.repository.session.commit()

        self.service.update_product(
            product.id,
            product_name="Bich item updated",
            unit_mode=UnitMode.BICH,
            enabled_prices={UnitType.BICH: Decimal("25")},
        )
        self.repository.session.commit()
        price = self.repository.session.scalars(select(ProductPrice).where(ProductPrice.product_id == product.id)).one()
        self.assertEqual(price.price, Decimal("25"))
        self.assertEqual(price.is_enabled, True)

    def test_delete_unused_product_succeeds(self) -> None:
        product = self.service.create_product(
            product_code_base="DEL-OK",
            product_name="Unused",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.BAO: Decimal("15")},
        )
        self.repository.session.commit()

        self.service.delete_product(product.id)
        self.repository.session.commit()
        self.assertEqual(self.repository.session.get(Product, product.id), None)

    def test_delete_product_with_history_fails(self) -> None:
        receipt_product = self.service.create_product(
            product_code_base="DEL-RECEIPT",
            product_name="Receipt history",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.BAO: Decimal("15")},
        )
        self.repository.session.commit()
        self.service.create_receipt([{"product_id": receipt_product.id, "quantity": Decimal("2")}])
        self.repository.session.commit()
        with self.assertRaises(ValidationError):
            self.service.delete_product(receipt_product.id)

        invoice_product = self.service.create_product(
            product_code_base="DEL-INVOICE",
            product_name="Invoice history",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.BAO: Decimal("15")},
        )
        self.repository.session.commit()
        self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="",
            invoice_datetime=datetime(2026, 4, 8, 9, 0, 0),
            items=[{"product_id": invoice_product.id, "unit_type": UnitType.BAO, "quantity": Decimal("1")}],
            paid_amount=Decimal("15"),
            payment_method=PaymentMethod.CASH,
        )
        self.repository.session.commit()
        with self.assertRaises(ValidationError):
            self.service.delete_product(invoice_product.id)

        adjustment_product = self.service.create_product(
            product_code_base="DEL-ADJ",
            product_name="Adjustment history",
            unit_mode=UnitMode.BAO_KG,
            enabled_prices={UnitType.BAO: Decimal("15")},
        )
        self.repository.session.commit()
        self.service.create_adjustment([{"product_id": adjustment_product.id, "new_quantity": Decimal("3")}])
        self.repository.session.commit()
        with self.assertRaises(ValidationError):
            self.service.delete_product(adjustment_product.id)

    def test_bao_to_kg_conversion_is_correct(self) -> None:
        self.assertEqual(self.service.bao_to_kg(Decimal("2")), Decimal("50"))
        self.assertEqual(self.service.kg_to_bao(Decimal("50")), Decimal("2"))

    def test_increase_and_decrease_bao_stock(self) -> None:
        self.service.increase_stock(self.bao_product_id, Decimal("4"), UnitType.BAO)
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("4"))

        self.service.decrease_stock(self.bao_product_id, Decimal("1.5"), UnitType.BAO)
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("2.5"))

    def test_increase_and_decrease_kg_stock(self) -> None:
        self.service.increase_stock(self.bao_product_id, Decimal("50"), UnitType.KG)
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("2"))
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.KG), Decimal("50"))

        self.service.decrease_stock(self.bao_product_id, Decimal("25"), UnitType.KG)
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("1"))
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.KG), Decimal("25"))

    def test_stock_can_go_negative(self) -> None:
        self.service.decrease_stock(self.bao_product_id, Decimal("1"), UnitType.BAO)
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("-1"))
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.KG), Decimal("-25"))

    def test_negative_balance_persists_after_commit_and_reload(self) -> None:
        self.service.decrease_stock(self.bao_product_id, Decimal("3"), UnitType.BAO)
        self.repository.session.commit()
        self.repository.session.expire_all()

        reloaded_balance = self.service.get_balance(self.bao_product_id)
        self.assertEqual(reloaded_balance.on_hand_bao_decimal, Decimal("-3"))
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.KG), Decimal("-75"))

    def test_bich_rejects_bao_and_kg_units(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.get_available_quantity(self.bich_product_id, UnitType.BAO)
        with self.assertRaises(ValidationError):
            self.service.increase_stock(self.bich_product_id, Decimal("1"), UnitType.KG)

    def test_bich_increase_and_decrease_use_direct_integer_stock(self) -> None:
        self.service.increase_stock(self.bich_product_id, 3, UnitType.BICH)
        self.assertEqual(self.service.get_available_quantity(self.bich_product_id, UnitType.BICH), Decimal("3"))

        self.service.decrease_stock(self.bich_product_id, 5, UnitType.BICH)
        self.assertEqual(self.service.get_available_quantity(self.bich_product_id, UnitType.BICH), Decimal("-2"))


if __name__ == "__main__":
    unittest.main()
