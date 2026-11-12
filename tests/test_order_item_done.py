from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.db import Base, _ensure_order_item_done_columns
from core.enums import UnitMode, UnitType
from core.exceptions import ValidationError
from modules.customer.models import Customer
from modules.inventory.models import Product, ProductPrice
from modules.orders.controller import OrderController
from modules.orders.repository import OrderRepository
from modules.orders.service import OrderService
from modules.orders.ui.order_detail_popup import OrderDetailPopup
from modules.orders.ui.page import OrdersPage
import modules.returns.models  # noqa: F401
import modules.sales.models  # noqa: F401


class OrderItemDoneTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.repository = OrderRepository(self.Session)
        self.service = OrderService(self.repository)
        self.controller = OrderController(self.Session)
        self.rice_id = self._create_product("P001", "Gao")
        self.flour_id = self._create_product("P002", "Bot")
        self.customer_id = self._create_customer()

    def tearDown(self) -> None:
        self.repository.session.close()
        self.engine.dispose()

    def test_done_line_stays_in_order_and_leaves_quantity_summary(self) -> None:
        order = self._create_order()
        rice_item = next(item for item in order.items if item.product_id == self.rice_id)

        self.controller.mark_item_done(rice_item.id, True)

        reloaded = self.controller.get_order(order.id)
        self.assertEqual(len(reloaded.items), 2)
        done_flags = {item.product_id: item.is_done for item in reloaded.items}
        self.assertEqual(done_flags, {self.rice_id: True, self.flour_id: False})
        self.assertIsNotNone(next(item for item in reloaded.items if item.product_id == self.rice_id).done_at)
        self.assertEqual(reloaded.status, "OPEN")

        summary = self.controller.list_active_quantity_summary()
        self.assertEqual([(row.product_id, row.quantity) for row in summary], [(self.flour_id, Decimal("3"))])

        self.controller.mark_item_done(rice_item.id, False)
        summary = {row.product_id: row.quantity for row in self.controller.list_active_quantity_summary()}
        self.assertEqual(summary, {self.rice_id: Decimal("5"), self.flour_id: Decimal("3")})

    def test_done_line_reduces_total_across_orders(self) -> None:
        first = self._create_order()
        self._create_order(order_datetime=datetime(2026, 4, 10, 10, 0, 0))
        rice_item = next(item for item in first.items if item.product_id == self.rice_id)

        self.controller.mark_item_done(rice_item.id, True)

        summary = {row.product_id: row.quantity for row in self.controller.list_active_quantity_summary()}
        self.assertEqual(summary, {self.rice_id: Decimal("5"), self.flour_id: Decimal("6")})

    def test_update_order_keeps_done_flag_only_for_unchanged_lines(self) -> None:
        order = self._create_order()
        for item in order.items:
            self.controller.mark_item_done(item.id, True)
        # Done flags were written by the controller's own session; drop stale state like the app does.
        self.repository.session.expire_all()

        self.service.update_order(
            order.id,
            customer_id=self.customer_id,
            customer_name_snapshot="Khach A",
            order_datetime=datetime(2026, 4, 10, 9, 0, 0),
            required_delivery_datetime=None,
            items=[
                {"product_id": self.rice_id, "unit_type": UnitType.BAO, "quantity": Decimal("5")},
                {"product_id": self.flour_id, "unit_type": UnitType.BAO, "quantity": Decimal("4")},
            ],
        )

        reloaded = self.controller.get_order(order.id)
        done_flags = {item.product_id: item.is_done for item in reloaded.items}
        self.assertEqual(done_flags, {self.rice_id: True, self.flour_id: False})

    def test_converted_order_lines_cannot_be_toggled(self) -> None:
        order = self._create_order()
        self.service.mark_converted(order.id, 999)
        self.repository.session.commit()

        with self.assertRaises(ValidationError):
            self.controller.mark_item_done(order.items[0].id, True)

    def test_popup_checkbox_marks_line_done_and_updates_progress(self) -> None:
        order = self._create_order()
        popup = OrderDetailPopup(self.controller.get_order(order.id), self.controller)
        self.assertEqual(popup._progress_label.text(), "Đã làm xong 0/2 dòng hàng")

        popup._items_table.item(0, 0).setCheckState(Qt.CheckState.Checked)

        self.assertEqual(popup._progress_label.text(), "Đã làm xong 1/2 dòng hàng")
        self.assertEqual(popup._items_table.item(0, 1).background().color().name(), "#d1fae5")
        item_id = popup._items_table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        reloaded = self.controller.get_order(order.id)
        self.assertTrue(next(item for item in reloaded.items if item.id == item_id).is_done)
        popup.deleteLater()

    def test_popup_checkbox_not_checkable_for_converted_order(self) -> None:
        order = self._create_order()
        self.service.mark_converted(order.id, 999)
        self.repository.session.commit()

        popup = OrderDetailPopup(self.controller.get_order(order.id), self.controller)
        flags = popup._items_table.item(0, 0).flags()
        self.assertFalse(bool(flags & Qt.ItemFlag.ItemIsUserCheckable))
        popup.deleteLater()

    def test_orders_list_shows_partial_progress(self) -> None:
        order = self._create_order()
        self.controller.mark_item_done(order.items[0].id, True)

        page = OrdersPage(self.service)
        self.assertEqual(page._table.item(0, 4).text(), "Đang mở · xong 1/2")
        page.deleteLater()

    def test_migration_adds_done_columns_idempotently(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE order_request_items (id INTEGER PRIMARY KEY, quantity NUMERIC)"))
            connection.execute(text("INSERT INTO order_request_items (id, quantity) VALUES (1, 2)"))

        _ensure_order_item_done_columns(engine)
        _ensure_order_item_done_columns(engine)

        with engine.connect() as connection:
            columns = {row["name"] for row in connection.execute(text("PRAGMA table_info(order_request_items)")).mappings()}
            is_done = connection.execute(text("SELECT is_done FROM order_request_items WHERE id = 1")).scalar_one()
        self.assertIn("is_done", columns)
        self.assertIn("done_at", columns)
        self.assertEqual(is_done, 0)
        engine.dispose()

    def _create_order(self, *, order_datetime: datetime = datetime(2026, 4, 10, 9, 0, 0)):
        order = self.service.create_order(
            customer_id=self.customer_id,
            customer_name_snapshot="Khach A",
            order_datetime=order_datetime,
            required_delivery_datetime=None,
            items=[
                {"product_id": self.rice_id, "unit_type": UnitType.BAO, "quantity": Decimal("5")},
                {"product_id": self.flour_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")},
            ],
        )
        self.repository.session.commit()
        return order

    def _create_product(self, code: str, name: str) -> int:
        session = self.repository.session
        product = Product(product_code_base=code, product_name=name, unit_mode=UnitMode.BAO_KG, is_active=True)
        session.add(product)
        session.flush()
        session.add(ProductPrice(product_id=product.id, unit_type=UnitType.BAO, price=Decimal("100"), is_enabled=True))
        session.commit()
        return product.id

    def _create_customer(self) -> int:
        session = self.repository.session
        customer = Customer(customer_name="Khach A", current_balance=Decimal("0"), total_sales=Decimal("0"))
        session.add(customer)
        session.commit()
        return customer.id


if __name__ == "__main__":
    unittest.main()
