from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from PyQt6.QtWidgets import QApplication, QLineEdit

from modules.customer.dto import CustomerDTO
from modules.customer.ui.customer_list_view import CustomerListView


class _CustomerControllerStub:
    def __init__(self, customers: list[CustomerDTO]) -> None:
        self._customers = customers

    def list_customers(
        self,
        sort_option: str = "name_asc",
        only_positive_debt: bool = False,
        include_inactive: bool = False,
    ) -> list[CustomerDTO]:
        rows = [row for row in self._customers if include_inactive or row.is_active]
        if only_positive_debt:
            rows = [row for row in rows if row.current_balance > 0]
        rows.sort(key=lambda row: row.customer_name.lower(), reverse=(sort_option == "name_desc"))
        return rows

    def search_customers(
        self,
        query: str,
        sort_option: str = "name_asc",
        only_positive_debt: bool = False,
        include_inactive: bool = False,
    ) -> list[CustomerDTO]:
        needle = query.strip().lower()
        return [
            row
            for row in self.list_customers(sort_option, only_positive_debt, include_inactive)
            if needle in row.customer_name.lower()
        ]

    def is_phone_duplicate(self, phone: str, *, excluding_customer_id: int | None = None) -> bool:
        return False

    def get_customer_with_recent_history(self, customer_id: int) -> object:
        customer = next(row for row in self._customers if row.id == customer_id)
        return type("Detail", (), {"customer": customer, "recent_history": ()})()

    def list_customer_trade_history(self, customer_id: int) -> tuple[object, ...]:
        del customer_id
        return ()

    def list_customer_debt_history(self, customer_id: int) -> tuple[object, ...]:
        del customer_id
        return ()

    def create_customer(self, **_payload: object) -> None:
        return None


class CustomerListSearchTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.customers = [
            CustomerDTO(
                id=1,
                customer_name="Nguyen Van An",
                phone="0901000001",
                address=None,
                current_balance=Decimal("150000"),
                total_sales=Decimal("500000"),
                is_walk_in=False,
                created_at=datetime(2026, 4, 10, 8, 0, 0),
                note=None,
            ),
            CustomerDTO(
                id=2,
                customer_name="Tran Binh",
                phone="0902000002",
                address=None,
                current_balance=Decimal("0"),
                total_sales=Decimal("200000"),
                is_walk_in=False,
                created_at=datetime(2026, 4, 10, 8, 5, 0),
                note=None,
            ),
        ]
        self.view = CustomerListView(_CustomerControllerStub(self.customers))

    def tearDown(self) -> None:
        self.view.deleteLater()

    def test_customer_list_uses_direct_table_filtering_and_summary_row(self) -> None:
        self.assertIsInstance(self.view._search_input, QLineEdit)
        self.view._search_input.setText("Nguyen")
        self.view._apply_filter()
        self._app.processEvents()

        self.assertEqual(self.view._table.rowCount(), 2)
        self.assertEqual(self.view._table.item(0, 0).text(), "")
        self.assertEqual(self.view._table.item(0, 1).text(), "")
        self.assertEqual(self.view._table.item(0, 2).text(), "150,000 VND")
        self.assertEqual(self.view._table.item(0, 3).text(), "500,000 VND")
        self.assertEqual(self.view._table.item(1, 0).text(), "Nguyen Van An")

        self.view._search_input.setText("")
        self.view._apply_filter()
        self._app.processEvents()
        self.assertEqual(self.view._table.rowCount(), 3)

    def test_customer_list_layout_uses_side_panel_and_main_panel(self) -> None:
        self.assertEqual(self.view.layout().count(), 2)
        self.assertEqual(self.view.layout().itemAt(0).widget(), self.view._side_panel)
        self.assertEqual(self.view.layout().itemAt(1).widget(), self.view._main_panel)
        self.assertEqual(self.view._main_panel.layout().itemAt(0).widget(), self.view._search_input)
        self.assertEqual(self.view._main_panel.layout().itemAt(1).widget(), self.view._table)
        headers = [self.view._table.horizontalHeaderItem(index).text() for index in range(self.view._table.columnCount())]
        self.assertEqual(headers, ["Tên khách", "Điện thoại", "Công nợ", "Tổng mua"])

    def test_inactive_customer_filter_is_hidden_by_default_and_can_be_shown(self) -> None:
        inactive = CustomerDTO(
            id=3,
            customer_name="Khach Ngung",
            phone=None,
            address=None,
            current_balance=Decimal("0"),
            total_sales=Decimal("0"),
            is_walk_in=False,
            created_at=datetime(2026, 4, 10, 8, 10, 0),
            note=None,
            is_active=False,
        )
        self.customers.append(inactive)

        self.view.reload()
        self.assertNotIn("Khach Ngung", [self.view._table.item(row, 0).text() for row in range(self.view._table.rowCount())])

        self.view._include_inactive_checkbox.setChecked(True)
        self._app.processEvents()

        names = [self.view._table.item(row, 0).text() for row in range(self.view._table.rowCount())]
        self.assertIn("Khach Ngung (ngừng sử dụng)", names)

    def test_single_click_opens_inline_detail_and_summary_row_is_non_interactive(self) -> None:
        self.view._handle_table_click(0, 0)
        self._app.processEvents()
        self.assertIsNone(self.view._expanded_customer_id)

        self.view._handle_table_click(1, 0)
        self._app.processEvents()
        self.assertEqual(self.view._expanded_customer_id, 1)
        self.assertEqual(self.view._table.rowCount(), 4)
        detail_widget = self.view._table.cellWidget(2, 0)
        self.assertIsNotNone(detail_widget)
        self.assertEqual(self.view._table.rowHeight(2), 560)

        self.view._handle_table_click(1, 0)
        self._app.processEvents()
        self.assertIsNone(self.view._expanded_customer_id)
        self.assertEqual(self.view._table.rowCount(), 3)

    def test_inline_detail_pagination_is_bottom_left_and_buttons_are_compact(self) -> None:
        self.view._handle_table_click(1, 0)
        self._app.processEvents()
        detail_widget = self.view._table.cellWidget(2, 0)
        self.assertIsNotNone(detail_widget)
        pager_buttons = detail_widget.findChildren(type(self.view._create_button), "pagerButton")
        self.assertTrue(all(button.height() <= 28 for button in pager_buttons))
        inline_buttons = detail_widget.findChildren(type(self.view._create_button), "inlineActionButton")
        self.assertGreaterEqual(len(inline_buttons), 2)


if __name__ == "__main__":
    unittest.main()
