from __future__ import annotations

from decimal import Decimal
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import UnitMode, UnitType
import modules.customer.models  # noqa: F401
from modules.inventory.models import Product
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
import modules.returns.models  # noqa: F401
import modules.sales.models  # noqa: F401


class InventoryTransactionServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.repository = InventoryRepository(self.Session)
        self.service = InventoryService(self.repository)

        self.bao_product_id = self._create_product("P-BAO", UnitMode.BAO_KG)
        self.bich_product_id = self._create_product("P-BICH", UnitMode.BICH)
        self.second_bao_product_id = self._create_product("P-BAO-2", UnitMode.BAO_KG)

    def tearDown(self) -> None:
        self.repository.session.close()
        self.engine.dispose()

    def _create_product(self, code: str, unit_mode: UnitMode) -> int:
        product = Product(product_code_base=code, product_name=code, unit_mode=unit_mode)
        self.repository.session.add(product)
        self.repository.session.commit()
        return product.id

    def test_create_receipt_with_multiple_lines_increases_stock(self) -> None:
        receipt = self.service.create_receipt(
            [
                {"product_id": self.bao_product_id, "quantity": Decimal("2.5")},
                {"product_id": self.bich_product_id, "quantity": Decimal("4")},
            ]
        )

        self.assertTrue(receipt.receipt_code.startswith("NK"))
        self.assertEqual(len(receipt.items), 2)
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("2.5"))
        self.assertEqual(self.service.get_available_quantity(self.bich_product_id, UnitType.BICH), Decimal("4"))

    def test_receipt_supports_many_products_in_one_document(self) -> None:
        receipt = self.service.create_receipt(
            [
                {"product_id": self.bao_product_id, "quantity": Decimal("1")},
                {"product_id": self.second_bao_product_id, "quantity": Decimal("3")},
                {"product_id": self.bich_product_id, "quantity": Decimal("2")},
            ]
        )

        self.assertEqual(len(receipt.items), 3)
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("1"))
        self.assertEqual(self.service.get_available_quantity(self.second_bao_product_id, UnitType.BAO), Decimal("3"))
        self.assertEqual(self.service.get_available_quantity(self.bich_product_id, UnitType.BICH), Decimal("2"))

    def test_current_quantity_loads_actual_balance(self) -> None:
        self.service.create_receipt([{"product_id": self.bao_product_id, "quantity": Decimal("5")}])
        self.assertEqual(self.service.get_current_quantity(self.bao_product_id), Decimal("5"))

    def test_adjustment_decreases_stock_from_five_to_three(self) -> None:
        self.service.create_receipt([{"product_id": self.bao_product_id, "quantity": Decimal("5")}])
        adjustment = self.service.create_adjustment([{"product_id": self.bao_product_id, "new_quantity": Decimal("3")}])

        self.assertEqual(len(adjustment.items), 1)
        item = adjustment.items[0]
        self.assertEqual(item.old_quantity, Decimal("5"))
        self.assertEqual(item.new_quantity, Decimal("3"))
        self.assertEqual(item.delta_quantity, Decimal("-2"))
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("3"))

    def test_adjustment_increases_stock_from_three_to_eight(self) -> None:
        self.service.create_receipt([{"product_id": self.bao_product_id, "quantity": Decimal("3")}])
        adjustment = self.service.create_adjustment([{"product_id": self.bao_product_id, "new_quantity": Decimal("8")}])

        self.assertEqual(len(adjustment.items), 1)
        item = adjustment.items[0]
        self.assertEqual(item.old_quantity, Decimal("3"))
        self.assertEqual(item.new_quantity, Decimal("8"))
        self.assertEqual(item.delta_quantity, Decimal("5"))
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("8"))

    def test_adjustment_for_bich_uses_canonical_integer_stock(self) -> None:
        self.service.create_receipt([{"product_id": self.bich_product_id, "quantity": Decimal("7")}])
        adjustment = self.service.create_adjustment([{"product_id": self.bich_product_id, "new_quantity": Decimal("3")}])

        item = adjustment.items[0]
        self.assertEqual(item.old_quantity, Decimal("7"))
        self.assertEqual(item.new_quantity, Decimal("3"))
        self.assertEqual(item.delta_quantity, Decimal("-4"))
        self.assertEqual(self.service.get_available_quantity(self.bich_product_id, UnitType.BICH), Decimal("3"))

    def test_adjustment_allows_negative_old_quantity_and_records_true_snapshot(self) -> None:
        self.service.decrease_stock(self.bao_product_id, Decimal("14"), UnitType.BAO)
        adjustment = self.service.create_adjustment([{"product_id": self.bao_product_id, "new_quantity": Decimal("12")}])

        item = adjustment.items[0]
        self.assertEqual(item.old_quantity, Decimal("-14"))
        self.assertEqual(item.new_quantity, Decimal("12"))
        self.assertEqual(item.delta_quantity, Decimal("26"))
        self.assertEqual(self.service.get_available_quantity(self.bao_product_id, UnitType.BAO), Decimal("12"))


if __name__ == "__main__":
    unittest.main()
