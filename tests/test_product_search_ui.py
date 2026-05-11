from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import unittest

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from core.enums import UnitType
from modules.inventory.dto import InventoryProductDTO
from modules.inventory.ui.product_list_view import ProductListView
from modules.returns.ui.product_search_widget import QuickReturnProductSearchWidget
from modules.sales.controller import SellableProductOption
from modules.sales.ui.product_search_widget import ProductSearchWidget


@dataclass(frozen=True, slots=True)
class _QuickReturnProductOptionStub:
    product_id: int
    product_code_base: str
    product_name: str
    enabled_prices: dict[UnitType, Decimal]


class _InventoryControllerStub:
    def __init__(self, products: list[InventoryProductDTO]) -> None:
        self._products = products

    def list_products(self, *, include_inactive: bool = False) -> list[InventoryProductDTO]:
        if include_inactive:
            return list(self._products)
        return [product for product in self._products if product.is_active]

    def get_unit_display(self, product: InventoryProductDTO) -> str:
        return product.unit_mode

    def get_on_hand_display(self, product: InventoryProductDTO) -> str:
        return product.on_hand_display


class ProductSearchUiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_sales_product_search_keeps_input_focus_and_renders_name_only(self) -> None:
        widget = ProductSearchWidget(
            [
                SellableProductOption(1, "P001", "Gao Nep", "BAO", {UnitType.BAO: Decimal("100")}),
                SellableProductOption(2, "P002", "Gao Te", "BAO", {UnitType.BAO: Decimal("120")}),
            ]
        )
        widget.show()
        widget.search_input.setFocus()
        self._app.processEvents()

        QTest.keyClick(widget.search_input, Qt.Key.Key_G)
        self._app.processEvents()
        popup = widget.search_input._popup_ref()
        self.assertIsNotNone(popup)
        self.assertTrue(popup.isVisible())
        self.assertTrue(widget.search_input.hasFocus())

        focus_widget = QApplication.focusWidget() or widget.search_input
        QTest.keyClick(focus_widget, Qt.Key.Key_A)
        self._app.processEvents()

        self.assertEqual(widget.search_input.text(), "ga")
        self.assertEqual([popup.item(index).text() for index in range(popup.count())], ["Gao Nep", "Gao Te"])

        QTest.keyClick(widget.search_input, Qt.Key.Key_Return)
        self._app.processEvents()

        self.assertEqual(widget.search_input.text(), "Gao Nep")
        self.assertIsNotNone(widget._selected_product)

        widget.search_input.setText("P001")
        widget._handle_search_text_edited("P001")
        self._app.processEvents()
        self.assertFalse(popup.isVisible())
        widget.deleteLater()

    def test_inventory_product_search_suggestions_use_name_only_and_do_not_match_code(self) -> None:
        view = ProductListView(
            _InventoryControllerStub(
                [
                    InventoryProductDTO(1, "P001", "Gao Nep", "Bao", "10 bao", "BAO:100", True, datetime(2026, 4, 10, 8, 0, 0)),
                    InventoryProductDTO(2, "P002", "Gao Te", "Bao", "5 bao", "BAO:120", True, datetime(2026, 4, 10, 8, 5, 0)),
                ]
            )
        )
        view.show()
        view._search_input.setText("Gao")
        view._apply_filter()
        self._app.processEvents()

        popup = view._search_input._popup_ref()
        self.assertIsNotNone(popup)
        self.assertEqual([popup.item(index).text() for index in range(popup.count())], ["Gao Nep", "Gao Te"])

        view._search_input.setText("P0")
        view._apply_filter()
        self._app.processEvents()
        self.assertFalse(popup.isVisible())
        view.deleteLater()

    def test_sales_compact_product_search_adds_first_match_on_enter(self) -> None:
        widget = ProductSearchWidget(
            [
                SellableProductOption(1, "P001", "Gao Nep", "BAO", {UnitType.BAO: Decimal("100")}, {UnitType.BAO: Decimal("12")}),
                SellableProductOption(2, "P002", "Gao Te", "BAO", {UnitType.BAO: Decimal("120")}, {UnitType.BAO: Decimal("7")}),
            ],
            compact=True,
        )
        payloads: list[dict[str, object]] = []
        widget.item_added.connect(lambda payload: payloads.append(dict(payload)))
        widget.show()
        widget.search_input.setFocus()
        self._app.processEvents()

        QTest.keyClicks(widget.search_input, "gao")
        QTest.keyClick(widget.search_input, Qt.Key.Key_Return)
        self._app.processEvents()

        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["product_name"], "Gao Nep")
        self.assertEqual(payloads[0]["quantity"], Decimal("1"))
        self.assertEqual(payloads[0]["unit_type"], UnitType.BAO)
        self.assertEqual(widget.search_input.text(), "")
        widget.deleteLater()

    def test_quick_return_product_search_suggestions_use_name_only_and_do_not_match_code(self) -> None:
        widget = QuickReturnProductSearchWidget(
            [
                _QuickReturnProductOptionStub(1, "P001", "Gao Nep", {UnitType.BAO: Decimal("100")}),
                _QuickReturnProductOptionStub(2, "P002", "Gao Te", {UnitType.BAO: Decimal("120")}),
            ]
        )
        widget.show()
        widget.search_input.setText("gao")
        self._app.processEvents()

        popup = widget.search_input._popup_ref()
        self.assertIsNotNone(popup)
        self.assertEqual([popup.item(index).text() for index in range(popup.count())], ["Gao Nep", "Gao Te"])

        widget.search_input.setText("P001")
        self._app.processEvents()
        self.assertFalse(popup.isVisible())
        widget.deleteLater()


if __name__ == "__main__":
    unittest.main()
