from __future__ import annotations

from decimal import Decimal
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import UnitMode, UnitType
from core.exceptions import ValidationError
import modules.customer.models  # noqa: F401
from modules.inventory.models import InventoryBalance, Product
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
import modules.returns.models  # noqa: F401
import modules.sales.models  # noqa: F401


class InventoryServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.repository = InventoryRepository(self.Session)
        self.service = InventoryService(self.repository)

        self.bao_product_id = self._create_product("P-BAO", UnitMode.BAO_KG)
        self.bich_product_id = self._create_product("P-BICH", UnitMode.BICH)

    def tearDown(self) -> None:
        self.repository.session.close()
        self.engine.dispose()

    def _create_product(self, code: str, unit_mode: UnitMode) -> int:
        product = Product(product_code_base=code, product_name=code, unit_mode=unit_mode)
        self.repository.session.add(product)
        self.repository.session.flush()
        return product.id

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
