from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QSizePolicy

from core.enums import UnitType
from modules.customer.dto import CustomerDTO
from modules.returns.ui.return_page import ReturnPage
from shared.widgets.message_box import MessageBox


@dataclass(frozen=True, slots=True)
class _ReturnInvoiceStub:
    return_code: str = "TR-QUICK-001"


@dataclass(frozen=True, slots=True)
class _QuickProductStub:
    product_id: int
    product_code_base: str
    product_name: str
    enabled_prices: dict[UnitType, Decimal]


class _ReturnControllerStub:
    def __init__(self) -> None:
        self.quick_return_calls: list[dict[str, object]] = []
        self._customers = [
            CustomerDTO(
                id=1,
                customer_name="Nguyen Van An",
                phone="0901000001",
                address=None,
                current_balance=Decimal("150000"),
                total_sales=Decimal("500000"),
                is_walk_in=False,
                created_at=datetime(2026, 4, 10, 8, 0, 0),
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
            ),
        ]

    def list_quick_return_customers(self) -> list[CustomerDTO]:
        return list(self._customers)

    def list_quick_return_products(self) -> list[object]:
        return [_QuickProductStub(101, "P-RET", "Hang tra", {UnitType.BAO: Decimal("100000")})]

    def search_source_invoices(self, query: str) -> list[object]:
        if "HD" not in query.upper():
            return []
        return [
            type(
                "Row",
                (),
                {
                    "invoice_id": 55,
                    "invoice_code": "HD001",
                    "customer_label": "Nguyen Van An",
                    "invoice_datetime": datetime(2026, 4, 10, 9, 0, 0),
                },
            )()
        ]

    def load_source_invoice_details(self, _invoice_id: int) -> object:
        return type(
            "Detail",
            (),
            {
                "invoice_id": 55,
                "invoice_code": "HD001",
                "invoice_datetime": datetime(2026, 4, 10, 9, 0, 0),
                "customer_name": "Nguyen Van An",
                "customer_id": 1,
                "current_balance": Decimal("150000"),
                "items": (
                    type(
                        "ItemRow",
                        (),
                        {
                            "source_invoice_item_id": 9001,
                            "product_code_snapshot": "P-RET",
                            "product_name_snapshot": "Hang tra",
                            "unit_type": "BAO",
                            "purchased_quantity": Decimal("3"),
                            "already_returned_quantity": Decimal("1"),
                            "remaining_returnable_quantity": Decimal("2"),
                            "unit_price": Decimal("100000"),
                        },
                    )(),
                ),
            },
        )()

    def create_quick_return_invoice(self, **payload: object) -> _ReturnInvoiceStub:
        self.quick_return_calls.append(payload)
        return _ReturnInvoiceStub()


class ReturnPageQuickCustomerSearchTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.controller = _ReturnControllerStub()
        self.quick_page = ReturnPage(self.controller, mode="quick")
        self.invoice_page = ReturnPage(self.controller, mode="invoice")

    def tearDown(self) -> None:
        self.quick_page.deleteLater()
        self.invoice_page.deleteLater()

    def test_quick_mode_has_no_extra_search_input_in_content(self) -> None:
        self.assertFalse(hasattr(self.quick_page, "_quick_product_search"))

    def test_invoice_mode_has_no_extra_search_input_in_content(self) -> None:
        self.assertFalse(hasattr(self.invoice_page, "_source_search"))

    def test_quick_mode_search_api_uses_product_name(self) -> None:
        suggestions = self.quick_page.shared_search_suggestions("hang")

        self.assertEqual(suggestions, [("Hang tra", 101)])
        self.quick_page.activate_shared_search_best_match("hang")
        self.assertEqual(len(self.quick_page._quick_items_table.items_payload()), 1)

    def test_invoice_mode_search_api_uses_invoice_code(self) -> None:
        suggestions = self.invoice_page.shared_search_suggestions("hd")

        self.assertEqual(suggestions, [("HD001 | Nguyen Van An", 55)])
        self.invoice_page.activate_shared_search_selection(55)
        self.assertIn("HD001", self.invoice_page._source_header.text())
        quantity_widget = self.invoice_page._invoice_items_table.cellWidget(0, 6)
        self.assertIsNotNone(quantity_widget)
        self.assertLessEqual(quantity_widget.maximumHeight(), 36)
        self.assertEqual(quantity_widget.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Fixed)

    def test_quick_mode_create_still_blocks_unselected_customer_text(self) -> None:
        self.quick_page.activate_shared_search_best_match("hang")
        self.quick_page._customer_picker.search_input.setText("Nguyen")

        with patch.object(MessageBox, "error") as error_mock:
            self.quick_page._create_quick_return_invoice()

        self.assertFalse(self.controller.quick_return_calls)
        error_mock.assert_called_once()

    def test_quick_mode_item_editors_use_compact_height(self) -> None:
        self.quick_page.activate_shared_search_best_match("hang")

        quantity_widget = self.quick_page._quick_items_table.cellWidget(0, 3)
        price_widget = self.quick_page._quick_items_table.cellWidget(0, 4)
        self.assertIsNotNone(quantity_widget)
        self.assertIsNotNone(price_widget)
        self.assertLessEqual(quantity_widget.maximumHeight(), 36)
        self.assertLessEqual(price_widget.maximumHeight(), 36)
        self.assertEqual(quantity_widget.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Fixed)


if __name__ == "__main__":
    unittest.main()
