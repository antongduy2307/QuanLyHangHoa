from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QWidget

from modules.customer.ui.debt_payment_list_view import DebtPaymentListView
from modules.returns.ui.return_list_view import ReturnListView
from modules.sales.controller import TransactionHistoryRow
from modules.sales.ui.invoice_list_view import InvoiceListView
from modules.sales.ui.transaction_history_view import TransactionHistoryView
from shared.widgets.message_box import MessageBox


class _InvoiceListControllerStub:
    def __init__(self, invoices: list[object] | None = None) -> None:
        self._invoices = invoices or []

    def list_invoices(self) -> list[object]:
        return list(self._invoices)


class _ReturnListControllerStub:
    def __init__(self, return_rows: list[object] | None = None) -> None:
        self._return_rows = return_rows or []

    def list_return_invoices(self) -> list[object]:
        return list(self._return_rows)


class _DebtListControllerStub:
    def __init__(self, payments: list[object] | None = None) -> None:
        self._payments = payments or []

    def list_debt_payments(self) -> list[object]:
        return list(self._payments)

    def search_debt_payments(self, _query: str) -> list[object]:
        return list(self._payments)


class _TransactionHistoryControllerStub:
    def __init__(self, rows: list[TransactionHistoryRow]) -> None:
        self._rows = rows

    def list_transaction_history(self, **_kwargs) -> list[TransactionHistoryRow]:
        return list(self._rows)

    def get_invoice_detail(self, invoice_id: int) -> object:
        return SimpleNamespace(id=invoice_id, invoice_code="HD001", invoice_datetime=datetime(2026, 4, 10, 9, 0, 0))


class _FakeMainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.invoice_edit_calls: list[int] = []
        self.return_edit_calls: list[int] = []

    def open_sales_invoice_editor(self, invoice_id: int) -> None:
        self.invoice_edit_calls.append(invoice_id)

    def open_sales_return_editor(self, return_id: int) -> None:
        self.return_edit_calls.append(return_id)


class HistoryEditActionsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_history_tabs_use_single_edit_action_without_separate_edit_datetime(self) -> None:
        invoice_view = InvoiceListView(_InvoiceListControllerStub())
        return_view = ReturnListView(_ReturnListControllerStub())
        debt_view = DebtPaymentListView(_DebtListControllerStub())
        history_view = TransactionHistoryView(_TransactionHistoryControllerStub([]))

        try:
            self.assertFalse(hasattr(invoice_view, "_edit_datetime_button"))
            self.assertFalse(hasattr(return_view, "_edit_datetime_button"))
            self.assertFalse(hasattr(debt_view, "_edit_datetime_button"))
            self.assertFalse(hasattr(history_view, "_edit_datetime_button"))
        finally:
            invoice_view.deleteLater()
            return_view.deleteLater()
            debt_view.deleteLater()
            history_view.deleteLater()

    def test_invoice_list_edit_routes_to_sales_workspace_editor(self) -> None:
        window = _FakeMainWindow()
        view = InvoiceListView(
            _InvoiceListControllerStub(
                [
                    SimpleNamespace(
                        id=11,
                        invoice_code="HD001",
                        customer_snapshot_name="Khach A",
                        total_amount=100,
                        paid_amount=80,
                        payment_method=SimpleNamespace(value="Tiền mặt"),
                        items=[1, 2],
                        invoice_datetime=datetime(2026, 4, 10, 9, 0, 0),
                    )
                ]
            )
        )
        view.setParent(window)
        try:
            view._table.setCurrentCell(0, 0)
            view._open_edit()
            self.assertEqual(window.invoice_edit_calls, [11])
        finally:
            view.deleteLater()
            window.deleteLater()

    def test_return_list_edit_routes_to_sales_workspace_editor(self) -> None:
        window = _FakeMainWindow()
        view = ReturnListView(
            _ReturnListControllerStub(
                [
                    SimpleNamespace(
                        id=22,
                        return_code="TR001",
                        customer_snapshot_name="Khach B",
                        total_amount=200,
                        handling_mode=SimpleNamespace(value="Hoàn tiền"),
                        return_datetime=datetime(2026, 4, 10, 10, 0, 0),
                    )
                ]
            )
        )
        view.setParent(window)
        try:
            view._table.setCurrentCell(0, 0)
            view._open_edit()
            self.assertEqual(window.return_edit_calls, [22])
        finally:
            view.deleteLater()
            window.deleteLater()

    def test_transaction_history_edit_routes_invoice_and_return_to_sales_workspace(self) -> None:
        window = _FakeMainWindow()
        controller = _TransactionHistoryControllerStub(
            [
                TransactionHistoryRow("INVOICE", 11, datetime(2026, 4, 10, 9, 0, 0), "HD001", "Khach A", 100),
                TransactionHistoryRow("RETURN", 22, datetime(2026, 4, 10, 10, 0, 0), "TR001", "Khach B", 200),
            ]
        )
        view = TransactionHistoryView(controller)
        view.setParent(window)
        try:
            view._table.setCurrentCell(0, 0)
            view._open_edit()
            view._table.setCurrentCell(1, 0)
            view._open_edit()
            self.assertEqual(window.invoice_edit_calls, [11])
            self.assertEqual(window.return_edit_calls, [22])
        finally:
            view.deleteLater()
            window.deleteLater()

    def test_transaction_history_edit_warns_for_debt_payment(self) -> None:
        controller = _TransactionHistoryControllerStub(
            [TransactionHistoryRow("DEBT_PAYMENT", 33, datetime(2026, 4, 10, 11, 0, 0), "7001", "Khach C", 50)]
        )
        view = TransactionHistoryView(controller)
        try:
            view._table.setCurrentCell(0, 0)
            with patch.object(MessageBox, "warning") as warning_mock:
                view._open_edit()
            warning_mock.assert_called_once()
        finally:
            view.deleteLater()


if __name__ == "__main__":
    unittest.main()
