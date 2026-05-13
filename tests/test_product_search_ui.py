from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QWidget

from core.enums import UnitType
from modules.inventory.dto import InventoryProductDTO
from modules.inventory.ui.product_list_view import ProductListView
from modules.returns.ui.product_search_widget import QuickReturnProductSearchWidget
from modules.sales.controller import SellableProductOption
from modules.sales.ui.product_search_widget import ProductSearchWidget
from shared.widgets.message_box import MessageBox


@dataclass(frozen=True, slots=True)
class _QuickReturnProductOptionStub:
    product_id: int
    product_code_base: str
    product_name: str
    enabled_prices: dict[UnitType, Decimal]


class _InventoryControllerStub:
    def __init__(
        self,
        products: list[InventoryProductDTO],
        *,
        delete_modes: dict[int, str] | None = None,
        delete_failures: set[int] | None = None,
    ) -> None:
        self._products = products
        self.delete_modes = delete_modes or {}
        self.delete_failures = delete_failures or set()
        self.get_delete_mode_calls: list[int] = []
        self.delete_product_calls: list[int] = []

    def list_products(self, *, include_inactive: bool = False) -> list[InventoryProductDTO]:
        if include_inactive:
            return list(self._products)
        return [product for product in self._products if product.is_active]

    def get_unit_display(self, product: InventoryProductDTO) -> str:
        return product.unit_mode

    def get_on_hand_display(self, product: InventoryProductDTO) -> str:
        return product.on_hand_display

    def get_delete_mode(self, product_id: int) -> str:
        self.get_delete_mode_calls.append(product_id)
        return self.delete_modes.get(product_id, "hard_delete")

    def delete_product(self, product_id: int) -> object:
        self.delete_product_calls.append(product_id)
        if product_id in self.delete_failures:
            raise RuntimeError("delete failed")
        action = "hard_deleted" if self.delete_modes.get(product_id, "hard_delete") == "hard_delete" else "deactivated"
        for index, product in enumerate(self._products):
            if product.id != product_id:
                continue
            if action == "hard_deleted":
                del self._products[index]
            else:
                self._products[index] = InventoryProductDTO(
                    product.id,
                    product.product_code_base,
                    product.product_name,
                    product.unit_mode,
                    product.on_hand_display,
                    product.enabled_price_summary,
                    False,
                    product.updated_at,
                )
            break
        return SimpleNamespace(action=action)


class ProductSearchUiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def _show_in_active_window(self, widget: QWidget) -> QWidget:
        window = QWidget()
        layout = QVBoxLayout(window)
        layout.addWidget(widget)
        window.show()
        window.raise_()
        window.activateWindow()
        QTest.qWaitForWindowExposed(window)
        self._app.processEvents()
        return window

    def test_sales_product_search_keeps_input_focus_and_renders_name_only(self) -> None:
        widget = ProductSearchWidget(
            [
                SellableProductOption(1, "P001", "Gao Nep", "BAO", {UnitType.BAO: Decimal("100")}),
                SellableProductOption(2, "P002", "Gao Te", "BAO", {UnitType.BAO: Decimal("120")}),
            ]
        )
        window = self._show_in_active_window(widget)
        widget.search_input.setFocus()
        self._app.processEvents()

        QTest.keyClick(widget.search_input, Qt.Key.Key_G)
        self._app.processEvents()
        popup = widget.search_input._popup_ref()
        self.assertIsNotNone(popup)
        self.assertTrue(popup.isVisible())
        self.assertEqual(popup.focusPolicy(), Qt.FocusPolicy.NoFocus)

        QTest.keyClick(widget.search_input, Qt.Key.Key_A)
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
        window.close()
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

    def test_inventory_product_delete_button_enters_selection_mode_and_cancel_exits(self) -> None:
        view = ProductListView(
            _InventoryControllerStub(
                [
                    InventoryProductDTO(1, "P001", "Gao Nep", "Bao", "10 bao", "BAO:100", True, datetime(2026, 4, 10, 8, 0, 0)),
                    InventoryProductDTO(2, "P002", "Gao Te", "Bao", "5 bao", "BAO:120", True, datetime(2026, 4, 10, 8, 5, 0)),
                ]
            )
        )

        view._delete_button.click()

        self.assertEqual(view._table.columnCount(), 6)
        self.assertTrue(view._create_button.isHidden())
        self.assertFalse(view._delete_selected_button.isHidden())
        self.assertFalse(view._cancel_delete_button.isHidden())
        self.assertEqual(view._selected_count_label.text(), "Đã chọn: 0")

        checkbox = view._table.item(self._product_row_for_name(view, "Gao Nep"), 0)
        self.assertIsNotNone(checkbox)
        assert checkbox is not None
        checkbox.setCheckState(Qt.CheckState.Checked)
        self.assertEqual(view._selected_count_label.text(), "Đã chọn: 1")
        self.assertTrue(view._delete_selected_button.isEnabled())

        view._cancel_delete_button.click()

        self.assertEqual(view._table.columnCount(), 5)
        self.assertFalse(view._create_button.isHidden())
        self.assertTrue(view._delete_selected_button.isHidden())
        self.assertEqual(view._selected_count_label.text(), "Đã chọn: 0")
        view.deleteLater()

    def test_inventory_product_batch_delete_previews_and_executes_mixed_modes(self) -> None:
        controller = _InventoryControllerStub(
            [
                InventoryProductDTO(1, "P001", "No History", "Bao", "10 bao", "BAO:100", True, datetime(2026, 4, 10, 8, 0, 0)),
                InventoryProductDTO(2, "P002", "Has History", "Bao", "5 bao", "BAO:120", True, datetime(2026, 4, 10, 8, 5, 0)),
            ],
            delete_modes={1: "hard_delete", 2: "deactivate"},
        )
        view = ProductListView(controller)
        view._delete_button.click()
        for name in ("No History", "Has History"):
            checkbox = view._table.item(self._product_row_for_name(view, name), 0)
            self.assertIsNotNone(checkbox)
            assert checkbox is not None
            checkbox.setCheckState(Qt.CheckState.Checked)

        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as question_mock,
            patch.object(MessageBox, "info") as info_mock,
            patch.object(MessageBox, "warning") as warning_mock,
        ):
            view._delete_selected_button.click()

        self.assertEqual(controller.get_delete_mode_calls, [1, 2])
        self.assertEqual(controller.delete_product_calls, [1, 2])
        confirm_message = question_mock.call_args.args[2]
        self.assertIn("Bạn đã chọn 2 hàng hóa", confirm_message)
        self.assertIn("1 hàng hóa chưa có lịch sử", confirm_message)
        self.assertIn("1 hàng hóa đã có lịch sử", confirm_message)
        self.assertEqual(view._table.columnCount(), 5)
        self.assertEqual([view._table.item(row, 1).text() for row in range(view._table.rowCount())], [])
        self.assertEqual([product.id for product in controller.list_products(include_inactive=True)], [2])
        self.assertFalse(controller.list_products(include_inactive=True)[0].is_active)
        warning_mock.assert_not_called()
        summary = info_mock.call_args.args[2]
        self.assertIn("xóa vĩnh viễn 1", summary.lower())
        self.assertIn("ngừng sử dụng", summary.lower())
        view.deleteLater()

    def test_inventory_product_batch_delete_continues_after_failure(self) -> None:
        controller = _InventoryControllerStub(
            [
                InventoryProductDTO(1, "P001", "Ok", "Bao", "10 bao", "BAO:100", True, datetime(2026, 4, 10, 8, 0, 0)),
                InventoryProductDTO(2, "P002", "Fail", "Bao", "5 bao", "BAO:120", True, datetime(2026, 4, 10, 8, 5, 0)),
            ],
            delete_modes={1: "hard_delete", 2: "deactivate"},
            delete_failures={2},
        )
        view = ProductListView(controller)
        view._delete_button.click()
        for name in ("Ok", "Fail"):
            checkbox = view._table.item(self._product_row_for_name(view, name), 0)
            self.assertIsNotNone(checkbox)
            assert checkbox is not None
            checkbox.setCheckState(Qt.CheckState.Checked)

        with (
            patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
            patch.object(MessageBox, "warning") as warning_mock,
            patch.object(MessageBox, "info"),
        ):
            view._delete_selected_button.click()

        self.assertEqual(controller.delete_product_calls, [1, 2])
        summary = warning_mock.call_args.args[2]
        self.assertIn("1 hàng hóa không xử lý được", summary)
        self.assertIn("Fail", summary)
        view.deleteLater()

    def test_inventory_product_filter_change_exits_delete_selection_mode(self) -> None:
        view = ProductListView(
            _InventoryControllerStub(
                [
                    InventoryProductDTO(1, "P001", "Gao Nep", "Bao", "10 bao", "BAO:100", True, datetime(2026, 4, 10, 8, 0, 0)),
                    InventoryProductDTO(2, "P002", "Gao Te", "Bao", "5 bao", "BAO:120", True, datetime(2026, 4, 10, 8, 5, 0)),
                ]
            )
        )
        view._delete_button.click()
        self.assertEqual(view._table.columnCount(), 6)

        view._search_input.setText("Nep")

        self.assertEqual(view._table.columnCount(), 5)
        self.assertTrue(view._delete_selected_button.isHidden())
        self.assertFalse(view._create_button.isHidden())
        self.assertEqual(view._table.rowCount(), 1)
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

    def _product_row_for_name(self, view: ProductListView, name: str) -> int:
        name_column = 2 if view._table.columnCount() == 6 else 1
        for row in range(view._table.rowCount()):
            item = view._table.item(row, name_column)
            if item is not None and item.text() == name:
                return row
        raise AssertionError(f"product row not found: {name}")


if __name__ == "__main__":
    unittest.main()
