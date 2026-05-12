from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication

from modules.customer.ui.debt_payment_list_view import DebtPaymentListView
from modules.returns.ui.return_list_view import ReturnListView
from modules.sales.controller import TransactionHistoryRow
from modules.sales.ui.invoice_list_view import InvoiceListView
from modules.sales.ui.transaction_history_view import TransactionHistoryView


class _InvoiceListControllerStub:
    def __init__(self, invoices: list[object]) -> None:
        self._invoices = invoices

    def list_invoices(self) -> list[object]:
        return list(self._invoices)


class _ReturnListControllerStub:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def list_return_invoices(self) -> list[object]:
        return list(self._rows)


class _DebtListControllerStub:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def list_debt_payments(self) -> list[object]:
        return list(self._rows)

    def search_debt_payments(self, query: str) -> list[object]:
        needle = query.strip().lower()
        return [
            row for row in self._rows
            if row.customer and needle in row.customer.customer_name.lower()
        ]


class _TransactionHistoryControllerStub:
    def __init__(self, rows: list[TransactionHistoryRow]) -> None:
        self._rows = rows

    def list_transaction_history(self, **kwargs) -> list[TransactionHistoryRow]:
        needle = str(kwargs.get("query", "")).strip().lower()
        if not needle:
            return list(self._rows)
        return [row for row in self._rows if needle in row.customer_name.lower()]


class HistorySearchSuggestionsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_invoice_return_debt_and_transaction_history_suggestions_show_customer_name_only(self) -> None:
        invoice_view = InvoiceListView(
            _InvoiceListControllerStub(
                [
                    SimpleNamespace(
                        id=1,
                        invoice_code="HD001",
                        customer_snapshot_name="Nguyen Van A",
                        total_amount=Decimal("100"),
                        paid_amount=Decimal("100"),
                        payment_method=SimpleNamespace(value="Tiền mặt"),
                        items=[1],
                        invoice_datetime=datetime(2026, 4, 10, 9, 0, 0),
                    ),
                    SimpleNamespace(
                        id=2,
                        invoice_code="HD002",
                        customer_snapshot_name="Nguyen Van A",
                        total_amount=Decimal("200"),
                        paid_amount=Decimal("150"),
                        payment_method=SimpleNamespace(value="Chuyển khoản"),
                        items=[1, 2],
                        invoice_datetime=datetime(2026, 4, 10, 10, 0, 0),
                    ),
                ]
            )
        )
        return_view = ReturnListView(
            _ReturnListControllerStub(
                [
                    SimpleNamespace(
                        id=3,
                        return_code="TR001",
                        customer_snapshot_name="Tran Thi B",
                        total_amount=Decimal("50"),
                        handling_mode=SimpleNamespace(value="Hoàn tiền"),
                        return_datetime=datetime(2026, 4, 10, 11, 0, 0),
                    )
                ]
            )
        )
        debt_view = DebtPaymentListView(
            _DebtListControllerStub(
                [
                    SimpleNamespace(
                        id=4,
                        ref_id=7001,
                        amount_delta=Decimal("-25"),
                        customer=SimpleNamespace(customer_name="Le Van C", phone="0909123456"),
                        effective_transaction_datetime=datetime(2026, 4, 10, 12, 0, 0),
                    )
                ]
            )
        )
        history_view = TransactionHistoryView(
            _TransactionHistoryControllerStub(
                [
                    TransactionHistoryRow("INVOICE", 1, datetime(2026, 4, 10, 9, 0, 0), "HD001", "Nguyen Van A", Decimal("100")),
                    TransactionHistoryRow("RETURN", 3, datetime(2026, 4, 10, 11, 0, 0), "TR001", "Tran Thi B", Decimal("50")),
                    TransactionHistoryRow("DEBT_PAYMENT", 4, datetime(2026, 4, 10, 12, 0, 0), "7001", "Le Van C", Decimal("25")),
                ]
            )
        )

        try:
            invoice_texts = self._suggestion_texts(invoice_view, "Nguyen")
            return_texts = self._suggestion_texts(return_view, "Tran")
            debt_texts = self._suggestion_texts(debt_view, "Le")
            history_texts = self._suggestion_texts(history_view, "Nguyen")

            self.assertEqual(invoice_texts, ["Nguyen Van A"])
            self.assertEqual(return_texts, ["Tran Thi B"])
            self.assertEqual(debt_texts, ["Le Van C"])
            self.assertEqual(history_texts, ["Nguyen Van A"])

            self.assertNotIn("HD001", "".join(invoice_texts + return_texts + debt_texts + history_texts))
            self.assertNotIn("TR001", "".join(invoice_texts + return_texts + debt_texts + history_texts))
            self.assertNotIn("7001", "".join(invoice_texts + return_texts + debt_texts + history_texts))
            self.assertNotIn("0909123456", "".join(invoice_texts + return_texts + debt_texts + history_texts))
            self.assertNotIn("Hóa đơn", "".join(invoice_texts + return_texts + debt_texts + history_texts))
        finally:
            invoice_view.deleteLater()
            return_view.deleteLater()
            debt_view.deleteLater()
            history_view.deleteLater()

    def _suggestion_texts(self, view: object, query: str) -> list[str]:
        view.show()
        view._search_input.setText(query)
        self._app.processEvents()
        popup = view._search_input._popup_ref()
        self.assertIsNotNone(popup)
        return [popup.item(index).text() for index in range(popup.count())]


if __name__ == "__main__":
    unittest.main()
