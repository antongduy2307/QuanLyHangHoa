from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QMessageBox

from modules.customer.ui.debt_payment_list_view import DebtPaymentListView
from modules.returns.ui.return_list_view import ReturnListView
from modules.sales.controller import TransactionHistoryRow
from modules.sales.ui.transaction_history_view import TransactionHistoryView
from shared.widgets.message_box import MessageBox


class _TransactionHistoryControllerStub:
    def __init__(self, rows: list[TransactionHistoryRow]) -> None:
        self._rows = rows
        self.deleted_invoice_ids: list[int] = []

    def list_transaction_history(self, **_kwargs) -> list[TransactionHistoryRow]:
        return list(self._rows)

    def delete_invoice(self, invoice_id: int) -> None:
        self.deleted_invoice_ids.append(invoice_id)


class _ReturnControllerStub:
    def __init__(self, rows: list[object] | None = None) -> None:
        self._rows = rows or []
        self.deleted_return_ids: list[int] = []

    def list_return_invoices(self) -> list[object]:
        return list(self._rows)

    def delete_return_invoice(self, return_id: int) -> None:
        self.deleted_return_ids.append(return_id)


class _DebtControllerStub:
    def __init__(self, rows: list[object] | None = None) -> None:
        self._rows = rows or []
        self.deleted_ledger_ids: list[int] = []

    def list_debt_payments(self) -> list[object]:
        return list(self._rows)

    def search_debt_payments(self, _query: str) -> list[object]:
        return list(self._rows)

    def delete_debt_payment(self, ledger_id: int) -> None:
        self.deleted_ledger_ids.append(ledger_id)


class HistoryDeleteActionsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_transaction_history_delete_routes_by_transaction_type(self) -> None:
        invoice_controller = _TransactionHistoryControllerStub([
            TransactionHistoryRow("INVOICE", 11, datetime(2026, 4, 10, 9, 0, 0), "HD001", "Khach A", 100),
        ])
        return_controller = _ReturnControllerStub()
        debt_controller = _DebtControllerStub()
        view = TransactionHistoryView(invoice_controller)
        try:
            view._table.setCurrentCell(0, 0)
            with patch("modules.sales.ui.transaction_history_view.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
                 patch("modules.sales.ui.transaction_history_view.ReturnController", return_value=return_controller), \
                 patch("modules.sales.ui.transaction_history_view.CustomerController", return_value=debt_controller), \
                 patch.object(MessageBox, "info"), patch.object(MessageBox, "error") as error_mock:
                view._delete_transaction()
            error_mock.assert_not_called()
            self.assertEqual(invoice_controller.deleted_invoice_ids, [11])
            self.assertEqual(return_controller.deleted_return_ids, [])
            self.assertEqual(debt_controller.deleted_ledger_ids, [])
        finally:
            view.deleteLater()

    def test_return_and_debt_list_views_have_delete_actions(self) -> None:
        return_view = ReturnListView(
            _ReturnControllerStub(
                [
                    SimpleNamespace(
                        id=22,
                        customer_snapshot_name="Khach B",
                        total_amount=200,
                        handling_mode=SimpleNamespace(value="Hoàn tiền"),
                        return_datetime=datetime(2026, 4, 10, 10, 0, 0),
                    )
                ]
            )
        )
        debt_controller = _DebtControllerStub(
            [
                SimpleNamespace(
                    id=33,
                    ref_id=7001,
                    amount_delta=-50,
                    customer=SimpleNamespace(customer_name="Khach C", phone="0909"),
                    effective_transaction_datetime=datetime(2026, 4, 10, 11, 0, 0),
                )
            ]
        )
        debt_view = DebtPaymentListView(debt_controller)
        try:
            return_view._table.setCurrentCell(0, 0)
            debt_view._table.setCurrentCell(0, 0)
            with patch("modules.returns.ui.return_list_view.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
                 patch.object(MessageBox, "info"), patch.object(MessageBox, "error") as error_mock:
                return_view._delete_return()
            error_mock.assert_not_called()
            self.assertEqual(return_view._controller.deleted_return_ids, [22])  # type: ignore[attr-defined]

            with patch("modules.customer.ui.debt_payment_list_view.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
                 patch.object(MessageBox, "info"), patch.object(MessageBox, "error") as error_mock:
                debt_view._delete_payment()
            error_mock.assert_not_called()
            self.assertEqual(debt_controller.deleted_ledger_ids, [33])
        finally:
            return_view.deleteLater()
            debt_view.deleteLater()


if __name__ == "__main__":
    unittest.main()
