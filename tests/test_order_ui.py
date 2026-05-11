from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from PyQt6.QtWidgets import QApplication, QPushButton
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import UnitMode, UnitType
from modules.customer.models import Customer
from modules.inventory.models import InventoryBalance, Product, ProductPrice
from modules.orders.models import OrderRequest
from modules.orders.repository import OrderRepository
from modules.orders.service import OrderService
from modules.orders.ui.page import OrdersPage
import modules.returns.models  # noqa: F401


class OrderUiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.repository = OrderRepository(self.Session)
        self.service = OrderService(self.repository)
        self.product_id = self._create_product()
        self.customer_id = self._create_customer()
        self.page = OrdersPage(self.service)
        self.page.show()
        self._app.processEvents()

    def tearDown(self) -> None:
        self.page.deleteLater()
        self.repository.session.close()
        self.engine.dispose()

    def test_prepared_order_rows_are_green_and_sorted_first(self) -> None:
        open_order = self._create_order(datetime(2026, 4, 10, 8, 0, 0))
        prepared_order = self._create_order(datetime(2026, 4, 10, 9, 0, 0))
        self.service.mark_prepared(prepared_order.id, True)

        self.page.reload()
        self._app.processEvents()

        first_order_id = self.page._table.item(0, 0).data(0x0100)
        second_order_id = self.page._table.item(1, 0).data(0x0100)
        self.assertEqual(first_order_id, prepared_order.id)
        self.assertEqual(second_order_id, open_order.id)
        self.assertEqual(self.page._table.item(0, 4).text(), "Đã hoàn thành")
        self.assertTrue(self.page._table.item(0, 0).background().color().isValid())

    def test_order_page_has_sub_tabs_and_no_manual_view_refresh_buttons(self) -> None:
        button_texts = [button.text() for button in self.page.findChildren(QPushButton)]
        self.assertNotIn("Xem", button_texts)
        self.assertNotIn("Làm mới", button_texts)
        self.assertEqual(self.page._tabs.tabText(0), "Khách hàng")
        self.assertEqual(self.page._tabs.tabText(1), "Tổng số lượng hàng cần làm")

    def test_quantity_summary_groups_same_product_and_unit(self) -> None:
        self._set_stock(self.product_id, Decimal("12.5"))
        self._create_order(datetime(2026, 4, 10, 8, 0, 0), quantity=Decimal("10"))
        self._create_order(datetime(2026, 4, 10, 9, 0, 0), quantity=Decimal("5"))

        self.page.reload()

        self.assertEqual(self.page._summary_table.rowCount(), 1)
        self.assertEqual(self.page._summary_table.item(0, 1).text(), "Gao")
        self.assertEqual(self.page._summary_table.item(0, 2).text(), "BAO")
        self.assertEqual(self.page._summary_table.item(0, 3).text(), "15")
        self.assertEqual(self.page._summary_table.item(0, 4).text(), "12.5")

    def test_quantity_summary_keeps_decimal_order_quantity_and_zero_stock(self) -> None:
        self._create_order(datetime(2026, 4, 10, 8, 0, 0), quantity=Decimal("4.8"))

        self.page.reload()

        self.assertEqual(self.page._summary_table.rowCount(), 1)
        self.assertEqual(self.page._summary_table.item(0, 3).text(), "4.8")
        self.assertEqual(self.page._summary_table.item(0, 4).text(), "0")

    def test_quantity_summary_splits_same_product_different_units(self) -> None:
        self._create_order(datetime(2026, 4, 10, 8, 0, 0), unit_type=UnitType.BAO, quantity=Decimal("10"))
        self._create_order(datetime(2026, 4, 10, 9, 0, 0), unit_type=UnitType.KG, quantity=Decimal("5"))

        self.page.reload()

        rows = {
            self.page._summary_table.item(row, 2).text(): self.page._summary_table.item(row, 3).text()
            for row in range(self.page._summary_table.rowCount())
        }
        self.assertEqual(rows, {"BAO": "10", "KG": "5"})

    def test_quantity_summary_excludes_converted_and_includes_prepared(self) -> None:
        converted = self._create_order(datetime(2026, 4, 10, 8, 0, 0), quantity=Decimal("10"))
        prepared = self._create_order(datetime(2026, 4, 10, 9, 0, 0), quantity=Decimal("4"))
        self.service.mark_converted(converted.id, 999)
        self.service.mark_prepared(prepared.id, True)

        self.page.reload()

        self.assertEqual(self.page._summary_table.rowCount(), 1)
        self.assertEqual(self.page._summary_table.item(0, 3).text(), "4")

    def test_quantity_summary_search_filters_by_product_name_and_clear_restores(self) -> None:
        second_product_id = self._create_product(code="P002", name="Bot")
        self._create_order(datetime(2026, 4, 10, 8, 0, 0), product_id=self.product_id, quantity=Decimal("10"))
        self._create_order(datetime(2026, 4, 10, 9, 0, 0), product_id=second_product_id, quantity=Decimal("5"))

        self.page.reload()
        self.page._summary_search_input.setText("bo")

        self.assertEqual(self.page._summary_table.rowCount(), 1)
        self.assertEqual(self.page._summary_table.item(0, 1).text(), "Bot")

        self.page._summary_search_input.clear()
        self.assertEqual(self.page._summary_table.rowCount(), 2)

    def test_quantity_summary_sort_modes(self) -> None:
        second_product_id = self._create_product(code="P002", name="Bot")
        self._create_order(datetime(2026, 4, 10, 8, 0, 0), product_id=self.product_id, quantity=Decimal("3"))
        self._create_order(datetime(2026, 4, 10, 9, 0, 0), product_id=second_product_id, quantity=Decimal("9"))

        self.page.reload()
        self.assertEqual(self.page._summary_table.item(0, 1).text(), "Bot")

        self.page._summary_sort_combo.setCurrentIndex(1)
        self.assertEqual(
            [self.page._summary_table.item(row, 1).text() for row in range(self.page._summary_table.rowCount())],
            ["Bot", "Gao"],
        )

    def _create_product(self, *, code: str = "P001", name: str = "Gao") -> int:
        session = self.repository.session
        product = Product(product_code_base=code, product_name=name, unit_mode=UnitMode.BAO_KG, is_active=True)
        session.add(product)
        session.flush()
        session.add(ProductPrice(product_id=product.id, unit_type=UnitType.BAO, price=Decimal("100"), is_enabled=True))
        session.add(ProductPrice(product_id=product.id, unit_type=UnitType.KG, price=Decimal("5"), is_enabled=True))
        session.add(InventoryBalance(product_id=product.id, on_hand_bao_decimal=Decimal("0")))
        session.commit()
        return product.id

    def _set_stock(self, product_id: int, quantity: Decimal) -> None:
        session = self.repository.session
        balance = session.scalar(select(InventoryBalance).where(InventoryBalance.product_id == product_id))
        if balance is None:
            balance = InventoryBalance(product_id=product_id, on_hand_bao_decimal=quantity)
            session.add(balance)
        else:
            balance.on_hand_bao_decimal = quantity
        session.commit()

    def _create_customer(self) -> int:
        session = self.repository.session
        customer = Customer(customer_name="Khach A", current_balance=Decimal("0"), total_sales=Decimal("0"))
        session.add(customer)
        session.commit()
        return customer.id

    def _create_order(
        self,
        order_datetime: datetime,
        *,
        product_id: int | None = None,
        unit_type: UnitType = UnitType.BAO,
        quantity: Decimal = Decimal("1"),
    ) -> OrderRequest:
        return self.service.create_order(
            customer_id=self.customer_id,
            customer_name_snapshot="Khach A",
            order_datetime=order_datetime,
            required_delivery_datetime=None,
            items=[{"product_id": product_id or self.product_id, "unit_type": unit_type, "quantity": quantity}],
        )


if __name__ == "__main__":
    unittest.main()
