from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from PyQt6.QtWidgets import QApplication, QSizePolicy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import PaymentMethod, UnitMode, UnitType
from modules.customer.models import Customer
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.models import Product, ProductPrice
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.sales.controller import SalesController
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService
from modules.sales.ui.invoice_edit_dialog import InvoiceEditDialog
import modules.returns.models  # noqa: F401


class InvoiceEditDialogLayoutTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

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
        self.controller = SalesController(self.Session)

        self.product_id = self._create_product_with_price("P-BAO", UnitMode.BAO_KG, [(UnitType.BAO, "100")])
        self.customer_id = self._create_customer("Khach sua hoa don")
        self.invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach sua hoa don",
            invoice_datetime=datetime(2026, 4, 12, 9, 0, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
            payment_method=PaymentMethod.CASH,
        )

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

    def test_dialog_layout_stays_stable_at_minimum_size(self) -> None:
        dialog = InvoiceEditDialog(self.controller, self.invoice)
        try:
            dialog.resize(dialog.minimumSize())
            dialog.show()
            self._app.processEvents()

            product_search = dialog._product_search
            self.assertFalse(product_search.unit_combo.geometry().intersects(product_search.quantity_input.geometry()))
            self.assertFalse(product_search.quantity_input.geometry().intersects(product_search._add_button.geometry()))
            self.assertGreater(product_search.price_label.geometry().width(), 0)
            self.assertEqual(dialog._items_table.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Expanding)
            self.assertTrue(dialog._scroll.widgetResizable())

            remove_button = dialog._items_table.cellWidget(0, 6)
            self.assertIsNotNone(remove_button)
            self.assertLessEqual(remove_button.geometry().height(), dialog._items_table.rowHeight(0))
            self.assertGreater(remove_button.geometry().width(), 0)
        finally:
            dialog.close()
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
