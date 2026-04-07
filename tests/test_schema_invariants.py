from __future__ import annotations

from decimal import Decimal
import unittest

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import InvoiceStatus, ReturnHandlingMode, UnitMode, UnitType
from core.exceptions import ValidationError
from modules.inventory.models import InventoryBalance, Product
from modules.returns.models import ReturnInvoice, ReturnInvoiceItem
from modules.sales.models import Invoice, InvoiceItem


class SchemaInvariantTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

    def tearDown(self) -> None:
        self.engine.dispose()

    def _make_product(self, code: str, unit_mode: UnitMode) -> Product:
        return Product(product_code_base=code, product_name=f"Product {code}", unit_mode=unit_mode)

    def test_product_mode_bich_rejects_bao_or_kg_price_via_model_helper(self) -> None:
        product = self._make_product("P-BICH", UnitMode.BICH)
        with self.assertRaises(ValidationError):
            product.validate_price_unit_type(UnitType.BAO)
        with self.assertRaises(ValidationError):
            product.validate_price_unit_type(UnitType.KG)

    def test_product_mode_bao_kg_rejects_bich_price_via_model_helper(self) -> None:
        product = self._make_product("P-BAO", UnitMode.BAO_KG)
        with self.assertRaises(ValidationError):
            product.validate_price_unit_type(UnitType.BICH)

    def test_invoice_item_requires_snapshot_fields(self) -> None:
        with self.Session() as session:
            product = self._make_product("P-001", UnitMode.BAO_KG)
            invoice = Invoice(
                invoice_code="INV-001",
                customer_id=None,
                customer_snapshot_name="Khach le",
                total_amount=Decimal("100000"),
                paid_amount=Decimal("100000"),
                status=InvoiceStatus.COMPLETED,
            )
            session.add_all([product, invoice])
            session.flush()

            broken_item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=product.id,
                unit_type=UnitType.BAO,
                quantity=Decimal("1"),
                unit_price=Decimal("100000"),
                line_total=Decimal("100000"),
                product_code_snapshot="",
                product_name_snapshot="San pham A",
            )
            session.add(broken_item)
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_return_invoice_item_requires_source_invoice_item_link(self) -> None:
        with self.Session() as session:
            product = self._make_product("P-RET", UnitMode.BICH)
            invoice = Invoice(
                invoice_code="INV-RET-001",
                customer_id=None,
                customer_snapshot_name="Khach le",
                total_amount=Decimal("50000"),
                paid_amount=Decimal("50000"),
            )
            session.add_all([product, invoice])
            session.flush()

            source_item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=product.id,
                unit_type=UnitType.BICH,
                quantity=Decimal("2"),
                unit_price=Decimal("25000"),
                line_total=Decimal("50000"),
                product_code_snapshot="P-RET",
                product_name_snapshot="San pham return",
            )
            session.add(source_item)
            session.flush()

            return_invoice = ReturnInvoice(
                return_code="RET-001",
                source_invoice_id=invoice.id,
                total_amount=Decimal("25000"),
                handling_mode=ReturnHandlingMode.STORE_CREDIT,
            )
            session.add(return_invoice)
            session.flush()

            broken_return_item = ReturnInvoiceItem(
                return_invoice_id=return_invoice.id,
                source_invoice_item_id=None,  # type: ignore[arg-type]
                product_id=product.id,
                unit_type=UnitType.BICH,
                quantity=Decimal("1"),
                unit_price=Decimal("25000"),
                line_total=Decimal("25000"),
                product_code_snapshot="P-RET",
                product_name_snapshot="San pham return",
            )
            session.add(broken_return_item)
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_invoice_supports_null_customer_id(self) -> None:
        with self.Session() as session:
            invoice = Invoice(
                invoice_code="INV-WALKIN",
                customer_id=None,
                customer_snapshot_name="Khach le",
                total_amount=Decimal("0"),
                paid_amount=Decimal("0"),
            )
            session.add(invoice)
            session.commit()
            self.assertIsNone(invoice.customer_id)

    def test_inventory_balance_helpers_match_product_mode(self) -> None:
        bao_product = self._make_product("P-BAO2", UnitMode.BAO_KG)
        bich_product = self._make_product("P-BICH2", UnitMode.BICH)

        InventoryBalance(
            product_id=1,
            on_hand_bao_decimal=Decimal("10.5"),
            on_hand_bich_integer=None,
        ).validate_for_product(bao_product)
        InventoryBalance(
            product_id=2,
            on_hand_bao_decimal=None,
            on_hand_bich_integer=12,
        ).validate_for_product(bich_product)

        with self.assertRaises(ValidationError):
            InventoryBalance(
                product_id=1,
                on_hand_bao_decimal=None,
                on_hand_bich_integer=5,
            ).validate_for_product(bao_product)

        with self.assertRaises(ValidationError):
            InventoryBalance(
                product_id=2,
                on_hand_bao_decimal=Decimal("1"),
                on_hand_bich_integer=None,
            ).validate_for_product(bich_product)


if __name__ == "__main__":
    unittest.main()
