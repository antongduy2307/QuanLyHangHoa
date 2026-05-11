from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QPushButton, QSizePolicy, QToolButton
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import UnitMode, UnitType
from modules.customer.models import Customer
from modules.inventory.models import Product, ProductPrice
from modules.orders.repository import OrderRepository
from modules.orders.service import OrderService
from modules.returns.repository import ReturnsRepository
from modules.returns.service import ReturnService
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService
from modules.sales.ui.page import SalesPage as SalesWorkspacePage
from modules.sales.ui.sales_page import SalesPage as SalesPageView
from shared.widgets.numeric_inputs import SelectAllQuantityInput
import modules.returns.models  # noqa: F401
import modules.orders.models  # noqa: F401


class SalesPosLayoutTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

        self.sales_repository = SalesRepository(self.Session)
        self.returns_repository = ReturnsRepository(self.Session)
        session = self.sales_repository.session

        customer = Customer(
            customer_name="Nguyen Van A",
            phone="0901000001",
            address="123 Le Loi",
            current_balance=Decimal("250000"),
            total_sales=Decimal("1000000"),
        )
        session.add(customer)

        product = Product(product_code_base="P001", product_name="Gao Nep", unit_mode=UnitMode.BAO_KG, is_active=True)
        session.add(product)
        session.flush()
        session.add(ProductPrice(product_id=product.id, unit_type=UnitType.BAO, price=Decimal("100"), is_enabled=True))
        session.commit()

        self.sales_service = SalesService(self.sales_repository)
        self.return_service = ReturnService(self.returns_repository, sales_repository=self.sales_repository)
        self.order_service = OrderService(OrderRepository(self.Session))
        self.workspace = SalesWorkspacePage(self.sales_service)
        self.workspace.resize(1400, 900)
        self.workspace.show()
        self._app.processEvents()

    def tearDown(self) -> None:
        self.workspace.deleteLater()
        self.sales_repository.session.close()
        self.returns_repository.session.close()
        self.engine.dispose()

    def test_workspace_uses_shared_search_tabs_and_plus_button(self) -> None:
        texts = [button.text() for button in self.workspace.findChildren(QPushButton)]
        self.assertNotIn("Đơn bán mới", texts)
        self.assertNotIn("Trả hàng mới", texts)
        self.assertEqual(self.workspace._new_tab_button.text(), "+")
        self.assertIsInstance(self.workspace._new_tab_button, QToolButton)
        self.assertIsNotNone(self.workspace._shared_search_input)
        self.assertEqual(self.workspace._workspace_tab_bar.count(), self.workspace._workspace_tabs.count())
        self.assertFalse(self.workspace._workspace_tab_bar.expanding())

    def test_search_bar_and_tab_bar_do_not_overlap(self) -> None:
        self._app.processEvents()
        search_rect = self.workspace._shared_search_input.geometry()
        tab_rect = self.workspace._workspace_tab_bar.geometry()
        plus_rect = self.workspace._new_tab_button.geometry()

        self.assertFalse(search_rect.intersects(tab_rect))
        self.assertFalse(tab_rect.intersects(plus_rect))
        self.assertLess(search_rect.right(), tab_rect.left())
        self.assertLess(tab_rect.right(), plus_rect.left())

    def test_tab_labels_are_renumbered_independently_by_remaining_tabs(self) -> None:
        self.workspace._add_sales_tab(make_current=False)
        self.workspace._add_sales_tab(make_current=False)
        self.workspace._add_return_tab(make_current=False, mode="quick")
        self.workspace._add_order_tab(make_current=False)

        self.assertEqual(
            [self.workspace._workspace_tab_bar.tabText(index) for index in range(self.workspace._workspace_tab_bar.count())],
            ["Bán hàng 1", "Trả hàng 1", "Bán hàng 2", "Bán hàng 3", "Trả hàng 2", "Đặt hàng 1"],
        )

        self.workspace._close_workspace_tab(0)
        self.assertEqual(
            [self.workspace._workspace_tab_bar.tabText(index) for index in range(self.workspace._workspace_tab_bar.count())],
            ["Trả hàng 1", "Bán hàng 1", "Bán hàng 2", "Trả hàng 2", "Đặt hàng 1"],
        )

        self.workspace._close_workspace_tab(0)
        self.assertEqual(
            [self.workspace._workspace_tab_bar.tabText(index) for index in range(self.workspace._workspace_tab_bar.count())],
            ["Bán hàng 1", "Bán hàng 2", "Trả hàng 1", "Đặt hàng 1"],
        )

    def test_return_tab_creation_supports_both_modes(self) -> None:
        self.workspace._add_return_tab(make_current=False, mode="invoice")
        self.workspace._add_return_tab(make_current=False, mode="quick")

        modes = [
            self.workspace._workspace_tabs.widget(index).property("return_mode")
            for index in range(self.workspace._workspace_tabs.count())
            if self.workspace._workspace_tabs.widget(index).property("workspace_mode") == "return"
        ]
        self.assertEqual(modes, ["invoice", "invoice", "quick"])

    def test_shared_search_placeholder_switches_with_active_tab_mode(self) -> None:
        self.assertEqual(self.workspace._shared_search_input.placeholderText(), "Tìm theo tên hàng")

        self.workspace._workspace_tab_bar.setCurrentIndex(1)
        self._app.processEvents()
        self.assertEqual(self.workspace._shared_search_input.placeholderText(), "Nhập mã hóa đơn nguồn")

        self.workspace._add_return_tab(make_current=True, mode="quick")
        self._app.processEvents()
        self.assertEqual(self.workspace._shared_search_input.placeholderText(), "Tìm theo tên hàng")

        self.workspace._add_order_tab(make_current=True)
        self._app.processEvents()
        self.assertEqual(self.workspace._shared_search_input.placeholderText(), "Tìm theo tên hàng")

    def test_order_sales_draft_does_not_convert_until_invoice_is_paid(self) -> None:
        order = self.order_service.create_order(
            customer_id=1,
            customer_name_snapshot="Nguyen Van A",
            order_datetime=datetime(2026, 4, 10, 8, 0, 0),
            required_delivery_datetime=None,
            items=[{"product_id": 1, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
        )

        self.workspace.open_order_sales_draft(order.id)
        self._app.processEvents()

        draft = self.workspace._workspace_tabs.currentWidget()
        self.assertIsInstance(draft, SalesPageView)
        self.assertIn(order.id, [row.id for row in self.order_service.list_active_orders()])
        draft._paid_amount_input.setValue(200)
        with patch("modules.sales.ui.sales_page.MessageBox.info"):
            draft._create_invoice()

        self.order_service._repository.session.expire_all()
        self.assertNotIn(order.id, [row.id for row in self.order_service.list_active_orders()])
        converted = self.order_service.get_order(order.id)
        self.assertEqual(converted.status, "CONVERTED")
        self.assertIsNotNone(converted.source_invoice_id)

    def test_payment_button_stays_visible_after_customer_select_and_paid_amount_entry(self) -> None:
        sales_page = self.workspace._workspace_tabs.widget(0)
        self.assertIsInstance(sales_page, SalesPageView)

        sales_page.add_product_payload(
            {
                "product_id": 1,
                "product_code_base": "P001",
                "product_name": "Gao Nep",
                "unit_type": UnitType.BAO,
                "quantity": Decimal("1"),
                "unit_price": Decimal("100"),
                "line_total": Decimal("100"),
                "stock_available": Decimal("12"),
                "enabled_prices": {UnitType.BAO: Decimal("100")},
                "stock_by_unit": {UnitType.BAO: Decimal("12")},
            }
        )
        sales_page._customer_picker.search_input.setText("Nguyen")
        sales_page._customer_picker._select_best_match()
        sales_page._paid_amount_input.setValue(150)
        self._app.processEvents()

        self.assertTrue(sales_page._create_button.isVisible())

    def test_sales_item_editors_use_compact_height(self) -> None:
        sales_page = self.workspace._workspace_tabs.widget(0)
        self.assertIsInstance(sales_page, SalesPageView)

        sales_page.add_product_payload(
            {
                "product_id": 1,
                "product_code_base": "P001",
                "product_name": "Gao Nep",
                "unit_type": UnitType.BAO,
                "quantity": Decimal("1"),
                "unit_price": Decimal("100"),
                "line_total": Decimal("100"),
                "stock_available": Decimal("12"),
                "enabled_prices": {UnitType.BAO: Decimal("100")},
                "stock_by_unit": {UnitType.BAO: Decimal("12")},
            }
        )
        self._app.processEvents()

        quantity_widget = sales_page._items_table.cellWidget(0, 3)
        price_widget = sales_page._items_table.cellWidget(0, 4)
        self.assertIsNotNone(quantity_widget)
        self.assertIsNotNone(price_widget)
        self.assertIsInstance(quantity_widget, SelectAllQuantityInput)
        self.assertLessEqual(quantity_widget.maximumHeight(), 36)
        self.assertLessEqual(price_widget.maximumHeight(), 36)
        self.assertEqual(quantity_widget.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Fixed)

    def test_sales_item_quantity_editor_accepts_decimal(self) -> None:
        sales_page = self.workspace._workspace_tabs.widget(0)
        self.assertIsInstance(sales_page, SalesPageView)

        sales_page.add_product_payload(
            {
                "product_id": 1,
                "product_code_base": "P001",
                "product_name": "Gao Nep",
                "unit_type": UnitType.BAO,
                "quantity": Decimal("1"),
                "unit_price": Decimal("100"),
                "line_total": Decimal("100"),
                "stock_available": Decimal("12"),
                "enabled_prices": {UnitType.BAO: Decimal("100")},
                "stock_by_unit": {UnitType.BAO: Decimal("12")},
            }
        )
        quantity_widget = sales_page._items_table.cellWidget(0, 3)
        self.assertIsInstance(quantity_widget, SelectAllQuantityInput)

        quantity_widget.setValue(Decimal("4.8"))
        quantity_widget.editingFinished.emit()

        payload = sales_page._items_table.items_payload()[0]
        self.assertEqual(payload["quantity"], Decimal("4.8"))
        self.assertEqual(payload["line_total"], Decimal("480.0"))

    def test_workspace_can_open_invoice_edit_tab_with_locked_customer_and_custom_label(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=1,
            customer_snapshot_name="Nguyen Van A",
            invoice_datetime=datetime(2026, 4, 10, 9, 0, 0),
            items=[{"product_id": 1, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("250"),
        )

        self.workspace.open_invoice_edit_tab(invoice.id)
        self._app.processEvents()

        current = self.workspace._workspace_tabs.currentWidget()
        self.assertIsInstance(current, SalesPageView)
        self.assertTrue(self.workspace._workspace_tab_bar.tabText(self.workspace._workspace_tab_bar.currentIndex()).startswith("Sửa bán hàng"))
        self.assertEqual(current._create_button.text(), "Cập nhật")
        self.assertFalse(current._customer_picker.search_input.isEnabled())
        self.assertEqual(current._paid_amount_input.value(), 250)

    def test_invoice_edit_can_lock_inactive_historical_customer(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=1,
            customer_snapshot_name="Nguyen Van A",
            invoice_datetime=datetime(2026, 4, 10, 9, 5, 0),
            items=[{"product_id": 1, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
        )
        customer = self.sales_repository.session.get(Customer, 1)
        self.assertIsNotNone(customer)
        customer.is_active = False
        self.sales_repository.session.commit()

        self.workspace.open_invoice_edit_tab(invoice.id)
        self._app.processEvents()

        current = self.workspace._workspace_tabs.currentWidget()
        self.assertIsInstance(current, SalesPageView)
        self.assertFalse(current._customer_picker.search_input.isEnabled())
        self.assertEqual(current._customer_picker.selected_customer_id(), 1)

    def test_workspace_can_open_return_edit_tab_with_custom_label(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=1,
            customer_snapshot_name="Nguyen Van A",
            invoice_datetime=datetime(2026, 4, 10, 9, 0, 0),
            items=[{"product_id": 1, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("200"),
        )
        return_invoice = self.return_service.create_return_invoice(
            source_invoice_id=invoice.id,
            return_datetime=datetime(2026, 4, 10, 10, 0, 0),
            items=[{"source_invoice_item_id": invoice.items[0].id, "quantity": Decimal("1")}],
            handling_mode="REFUND_NOW",
        )

        self.workspace.open_return_edit_tab(return_invoice.id)
        self._app.processEvents()

        current = self.workspace._workspace_tabs.currentWidget()
        self.assertTrue(self.workspace._workspace_tab_bar.tabText(self.workspace._workspace_tab_bar.currentIndex()).startswith("Sửa trả hàng"))
        self.assertEqual(current._create_button.text(), "Cập nhật")
        self.assertFalse(current._customer_picker.search_input.isEnabled())


if __name__ == "__main__":
    unittest.main()
