from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from modules.customer.controller import CustomerDebtEntry, CustomerDetailData, CustomerHistoryEntry
from modules.customer.dto import CustomerDTO
from modules.customer.ui.customer_detail_popup import CustomerDetailPopup
from modules.customer.ui.customer_list_view import _DebtHistorySection
from modules.returns.ui.return_detail_popup import ReturnDetailPopup
from modules.sales.ui.invoice_detail_popup import InvoiceDetailPopup
from modules.sales.ui.customer_picker_widget import CustomerPickerWidget


class _CustomerControllerStub:
    def __init__(self) -> None:
        self.updated_calls: list[tuple[int, str]] = []
        self.deleted_ids: list[int] = []
        self.debt_calls: list[tuple[int, Decimal]] = []

    def update_customer(self, customer_id: int, **payload: object) -> None:
        self.updated_calls.append((customer_id, str(payload["customer_name"])))

    def get_delete_mode(self, customer_id: int) -> str:
        del customer_id
        return "hard_delete"

    def delete_customer(self, customer_id: int) -> object:
        self.deleted_ids.append(customer_id)
        return SimpleNamespace(action="hard_deleted")

    def pay_debt(self, customer_id: int, amount: Decimal, **_kwargs: object) -> None:
        self.debt_calls.append((customer_id, amount))


class _FakeMainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.navigation_calls: list[tuple[str, int]] = []

    def navigate_to_history_transaction(self, transaction_kind: str, transaction_id: int) -> None:
        self.navigation_calls.append((transaction_kind, transaction_id))


class CustomerUiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.customers = [
            CustomerDTO(
                id=1,
                customer_name="Nguyen Van An",
                phone="0901000001",
                address="123 Le Loi",
                current_balance=Decimal("150000"),
                total_sales=Decimal("500000"),
                is_walk_in=False,
                created_at=datetime(2026, 4, 10, 8, 0, 0),
                note="Khach than thiet",
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

    def tearDown(self) -> None:
        self._app.processEvents()

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

    def test_customer_picker_keeps_input_focus_while_suggestions_are_open(self) -> None:
        widget = CustomerPickerWidget(self.customers)
        window = self._show_in_active_window(widget)
        widget.customer_radio.setChecked(True)
        widget.search_input.setFocus()
        self._app.processEvents()

        QTest.keyClick(widget.search_input, Qt.Key.Key_A)
        self._app.processEvents()

        popup = widget.search_input._popup_ref()
        self.assertIsNotNone(popup)
        self.assertTrue(popup.isVisible())
        self.assertEqual(popup.focusPolicy(), Qt.FocusPolicy.NoFocus)

        QTest.keyClick(widget.search_input, Qt.Key.Key_N)
        self._app.processEvents()

        self.assertEqual(widget.search_input.text(), "an")
        self.assertIsNone(widget.selected_customer_id())

        QTest.keyClick(widget.search_input, Qt.Key.Key_Return)
        self._app.processEvents()

        self.assertEqual(widget.selected_customer_id(), 1)
        self.assertIn("Nguyen Van An", widget.current_label.text())
        window.close()
        widget.deleteLater()

    def test_customer_picker_suggestions_show_customer_name_only_and_search_by_phone_no_longer_matches(self) -> None:
        widget = CustomerPickerWidget(self.customers)
        widget.show()
        widget.customer_radio.setChecked(True)
        widget.search_input.setText("Nguyen")
        widget._handle_search_text_edited("Nguyen")
        self._app.processEvents()

        popup = widget.search_input._popup_ref()
        self.assertIsNotNone(popup)
        self.assertEqual(popup.count(), 1)
        self.assertEqual(popup.item(0).text(), "Nguyen Van An")

        widget.search_input.setText("0901")
        widget._handle_search_text_edited("0901")
        self._app.processEvents()

        self.assertFalse(popup.isVisible())
        widget.deleteLater()

    def test_customer_detail_popup_displays_actions_and_history_items_column(self) -> None:
        controller = _CustomerControllerStub()
        popup = CustomerDetailPopup(
            CustomerDetailData(
                customer=self.customers[0],
                recent_history=(
                    CustomerHistoryEntry(
                        transaction_id=101,
                        transaction_kind="INVOICE",
                        transaction_datetime=datetime(2026, 4, 10, 9, 30, 0),
                        transaction_type="Bán hàng",
                        item_summary="Gạo ST25, Nước mắm",
                        amount=Decimal("150000"),
                    ),
                ),
            ),
            controller=controller,
        )
        popup.show()
        self._app.processEvents()

        labels = [label.text() for label in popup.findChildren(QLabel)]
        buttons = [button.text() for button in popup.findChildren(QPushButton)]
        headers = [popup._history_table.horizontalHeaderItem(index).text() for index in range(popup._history_table.columnCount())]
        self.assertIn("Ghi chú", labels)
        self.assertIn("Khach than thiet", labels)
        self.assertIn("Sửa", buttons)
        self.assertIn("Xóa", buttons)
        self.assertIn("Thanh toán nợ", buttons)
        self.assertEqual(headers, ["Thời điểm", "Loại giao dịch", "Hàng đã giao dịch", "Số tiền"])
        self.assertEqual(popup._history_table.item(0, 2).text(), "Gạo ST25, Nước mắm")
        popup.deleteLater()

    def test_customer_detail_popup_double_click_routes_to_history_tab(self) -> None:
        controller = _CustomerControllerStub()
        main_window = _FakeMainWindow()
        popup = CustomerDetailPopup(
            CustomerDetailData(
                customer=self.customers[0],
                recent_history=(
                    CustomerHistoryEntry(
                        transaction_id=501,
                        transaction_kind="RETURN",
                        transaction_datetime=datetime(2026, 4, 10, 9, 30, 0),
                        transaction_type="Trả hàng",
                        item_summary="Gạo ST25",
                        amount=Decimal("50000"),
                    ),
                ),
            ),
            parent=main_window,
            controller=controller,
        )
        popup.show()
        self._app.processEvents()

        popup._history_table.setCurrentCell(0, 0)
        popup._open_transaction_from_history()

        self.assertEqual(main_window.navigation_calls, [("RETURN", 501)])
        popup.deleteLater()
        main_window.deleteLater()

    def test_debt_history_section_paginates_after_receiving_newest_first_entries(self) -> None:
        entries = [
            CustomerDebtEntry(
                transaction_id=index,
                transaction_kind="DEBT_PAYMENT",
                transaction_datetime=datetime(2026, 4, 10, 12, 0, 0),
                transaction_type="Trả nợ",
                amount=Decimal(str(index * 1000)),
                balance_after=Decimal(str(index * 1000)),
            )
            for index in range(8, 0, -1)
        ]
        widget = _DebtHistorySection(entries, Decimal("8000"), lambda *_args: None, lambda: None)
        widget.show()
        self._app.processEvents()

        self.assertEqual(widget.table.rowCount(), 7)
        self.assertEqual(widget.table.item(0, 2).text(), "8,000 VND")
        self.assertEqual(widget.table.item(6, 2).text(), "2,000 VND")

        widget._go_next()
        self._app.processEvents()
        self.assertEqual(widget.table.rowCount(), 1)
        self.assertEqual(widget.table.item(0, 2).text(), "1,000 VND")
        widget.deleteLater()

    def test_invoice_detail_popup_shows_edit_next_to_open_record_and_dispatches_separately(self) -> None:
        open_calls: list[str] = []
        edit_calls: list[str] = []
        invoice = SimpleNamespace(
            id=11,
            invoice_code="HD001",
            invoice_datetime=datetime(2026, 4, 10, 9, 0, 0),
            customer_id=1,
            customer_snapshot_name="Khach A",
            total_amount=Decimal("100"),
            paid_amount=Decimal("80"),
            note=None,
            items=[],
        )

        with patch("modules.sales.ui.invoice_detail_popup.SalesController.get_invoice_balance_after", return_value=None):
            popup = InvoiceDetailPopup(
                invoice,
                on_open_record=lambda: open_calls.append("open"),
                on_edit_record=lambda: edit_calls.append("edit"),
            )
        popup.show()
        self._app.processEvents()

        buttons = [button.text() for button in popup.findChildren(QPushButton)]
        self.assertIn("Sửa", buttons)
        self.assertIn("Mở phiếu", buttons)
        self.assertLess(popup._edit_record_button.geometry().left(), popup._open_record_button.geometry().left())

        popup._edit_record_button.click()
        self.assertEqual(edit_calls, ["edit"])
        self.assertEqual(open_calls, [])
        popup.deleteLater()

        with patch("modules.sales.ui.invoice_detail_popup.SalesController.get_invoice_balance_after", return_value=None):
            popup = InvoiceDetailPopup(
                invoice,
                on_open_record=lambda: open_calls.append("open"),
                on_edit_record=lambda: edit_calls.append("edit"),
            )
        popup._open_record_button.click()
        self.assertEqual(open_calls, ["open"])
        self.assertEqual(edit_calls, ["edit"])
        popup.deleteLater()

    def test_return_detail_popup_shows_edit_next_to_open_record_and_dispatches_separately(self) -> None:
        open_calls: list[str] = []
        edit_calls: list[str] = []
        return_invoice = SimpleNamespace(
            id=22,
            return_code="TR001",
            return_datetime=datetime(2026, 4, 10, 10, 0, 0),
            customer=None,
            customer_snapshot_name="Khach A",
            total_amount=Decimal("50"),
            handling_mode=SimpleNamespace(value="Hoàn tiền"),
            note=None,
            items=[],
        )

        popup = ReturnDetailPopup(
            return_invoice,
            on_open_record=lambda: open_calls.append("open"),
            on_edit_record=lambda: edit_calls.append("edit"),
        )
        popup.show()
        self._app.processEvents()

        buttons = [button.text() for button in popup.findChildren(QPushButton)]
        self.assertIn("Sửa", buttons)
        self.assertIn("Mở phiếu", buttons)
        self.assertLess(popup._edit_record_button.geometry().left(), popup._open_record_button.geometry().left())

        popup._edit_record_button.click()
        self.assertEqual(edit_calls, ["edit"])
        self.assertEqual(open_calls, [])
        popup.deleteLater()

        popup = ReturnDetailPopup(
            return_invoice,
            on_open_record=lambda: open_calls.append("open"),
            on_edit_record=lambda: edit_calls.append("edit"),
        )
        popup._open_record_button.click()
        self.assertEqual(open_calls, ["open"])
        self.assertEqual(edit_calls, ["edit"])
        popup.deleteLater()


if __name__ == "__main__":
    unittest.main()
