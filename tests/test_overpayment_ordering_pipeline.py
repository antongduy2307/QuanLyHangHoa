from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import unittest

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import QApplication
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import PaymentMethod, UnitMode, UnitType
from modules.customer.controller import CustomerController
from modules.customer.models import Customer, CustomerBalanceLedger
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.customer.ui.customer_detail_popup import CustomerDetailPopup
from modules.customer.ui.customer_list_view import _CustomerInlineDetailWidget, _DebtHistorySection, _TradeHistorySection
from modules.customer.ui.debt_payment_list_view import DebtPaymentListView
from modules.inventory.models import Product, ProductPrice
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.sales.controller import SalesController
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService
from modules.sales.ui.transaction_history_view import TransactionHistoryView
import modules.returns.models  # noqa: F401


class OverpaymentOrderingPipelineTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

        self.customer_repository = CustomerRepository(self.Session)
        self.sales_repository = SalesRepository(self.Session)
        self.inventory_repository = InventoryRepository(self.Session)
        self.customer_service = CustomerService(self.customer_repository)
        self.inventory_service = InventoryService(self.inventory_repository)
        self.sales_service = SalesService(
            self.sales_repository,
            inventory_service=self.inventory_service,
            customer_service=self.customer_service,
        )
        self.customer_controller = CustomerController(self.Session)
        self.sales_controller = SalesController(self.Session)

        self.product_id = self._create_product_with_price()
        self.customer_id = self._create_customer()

    def tearDown(self) -> None:
        self._app.processEvents()
        self.customer_repository.session.close()
        self.sales_repository.session.close()
        self.inventory_repository.session.close()
        self.engine.dispose()

    def _create_product_with_price(self) -> int:
        session = self.sales_repository.session
        product = Product(product_code_base="P-TRACE", product_name="P-TRACE", unit_mode=UnitMode.BAO_KG, is_active=True)
        session.add(product)
        session.flush()
        session.add(ProductPrice(product_id=product.id, unit_type=UnitType.BAO, price=Decimal("100"), is_enabled=True))
        session.commit()
        return product.id

    def _create_customer(self) -> int:
        customer = Customer(
            customer_name="Khach ordering",
            phone="0909000000",
            address="Trace",
            current_balance=Decimal("0"),
            total_sales=Decimal("0"),
        )
        self.sales_repository.session.add(customer)
        self.sales_repository.session.commit()
        return customer.id

    def _create_overpayment_batch_with_same_displayed_minute(self) -> tuple[int, int]:
        self.customer_service.adjust_balance(
            self.customer_id,
            Decimal("22000000"),
            "MANUAL",
            1,
            transaction_datetime=datetime(2026, 4, 23, 1, 0, 0),
        )
        invoice_datetime = datetime(2026, 4, 23, 1, 50, 5)
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach ordering",
            invoice_datetime=invoice_datetime,
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("340000")}],
            paid_amount=Decimal("56000000"),
            payment_method=PaymentMethod.CASH,
        )
        debt_payment = self.customer_repository.list_ledgers_by_event_type(self.customer_id, "DEBT_PAYMENT")[0]
        debt_payment.transaction_datetime = invoice_datetime + timedelta(seconds=40)
        self.customer_repository.session.commit()
        return invoice.id, debt_payment.id

    def test_full_pipeline_uses_logical_order_then_screen_sort_direction(self) -> None:
        invoice_id, debt_ledger_id = self._create_overpayment_batch_with_same_displayed_minute()

        db_ledgers = list(
            self.sales_repository.session.scalars(
                select(CustomerBalanceLedger)
                .where(CustomerBalanceLedger.customer_id == self.customer_id)
                .where(CustomerBalanceLedger.ref_type.in_(["INVOICE", "DEBT_PAYMENT"]))
                .order_by(CustomerBalanceLedger.id.asc())
            ).all()
        )
        db_trace = [
            (
                ledger.id,
                ledger.event_type,
                ledger.ref_type,
                ledger.transaction_datetime,
                ledger.source_ref_type,
                ledger.source_ref_id,
                ledger.display_order,
                ledger.balance_after,
            )
            for ledger in db_ledgers
        ]
        self.assertEqual([row[1] for row in db_trace], ["INVOICE_CHARGE", "DEBT_PAYMENT"])
        self.assertEqual(db_trace[-1][4:7], ("INVOICE", invoice_id, 20))

        debt_entries = self.customer_controller.list_customer_debt_history(self.customer_id)
        batch_debt_entries = [entry for entry in debt_entries if entry.source_ref_id == invoice_id]
        self.assertEqual(
            [(entry.transaction_kind, entry.amount, entry.balance_after) for entry in batch_debt_entries],
            [
                ("DEBT_PAYMENT", Decimal("56000000"), Decimal("0")),
                ("INVOICE", Decimal("34000000"), Decimal("56000000")),
            ],
        )

        recent_entries = self.customer_controller.get_customer_with_recent_history(self.customer_id, limit=2).recent_history
        self.assertEqual(
            [(entry.transaction_kind, entry.amount) for entry in recent_entries],
            [("DEBT_PAYMENT", Decimal("56000000")), ("INVOICE", Decimal("34000000"))],
        )

        transaction_rows = [
            row for row in self.sales_controller.list_transaction_history(sort_option="newest")
            if row.source_ref_id == invoice_id
        ]
        self.assertEqual(
            [(row.transaction_type, row.amount) for row in transaction_rows],
            [("DEBT_PAYMENT", Decimal("56000000")), ("INVOICE", Decimal("34000000"))],
        )
        oldest_transaction_rows = [
            row for row in self.sales_controller.list_transaction_history(sort_option="oldest")
            if row.source_ref_id == invoice_id
        ]
        self.assertEqual(
            [(row.transaction_type, row.amount) for row in oldest_transaction_rows],
            [("INVOICE", Decimal("34000000")), ("DEBT_PAYMENT", Decimal("56000000"))],
        )

        detail = self.customer_controller.get_customer_with_recent_history(self.customer_id, limit=2)
        inline = _CustomerInlineDetailWidget(
            self.customer_controller,
            detail,
            on_changed=lambda: None,
            on_open_transaction=lambda *_args: None,
            on_edit_transaction=lambda *_args: None,
        )
        inline.show()
        self._app.processEvents()
        debt_section = inline.findChild(_DebtHistorySection)
        trade_section = inline.findChild(_TradeHistorySection)
        self.assertIsNotNone(debt_section)
        self.assertIsNotNone(trade_section)
        assert debt_section is not None
        assert trade_section is not None
        self.assertFalse(debt_section.table.isSortingEnabled())
        self.assertEqual(
            [
                (debt_section.table.item(row, 1).text(), debt_section.table.item(row, 2).text(), debt_section.table.item(row, 3).text())
                for row in range(debt_section.table.rowCount())
            ],
            [
                ("Trả nợ", "56,000,000 VND", "0 VND"),
                ("Bán hàng", "34,000,000 VND", "56,000,000 VND"),
                ("Điều chỉnh công nợ", "22,000,000 VND", "22,000,000 VND"),
            ],
        )
        self.assertTrue(debt_section.table.item(0, 0).text().endswith("01:50:45"))
        self.assertTrue(debt_section.table.item(1, 0).text().endswith("01:50:05"))
        self.assertTrue(debt_section.table.item(2, 0).text().endswith("01:00:00"))
        self.assertEqual(trade_section.table.item(0, 1).text(), "Bán hàng")

        popup = CustomerDetailPopup(detail, controller=self.customer_controller)
        popup.show()
        self._app.processEvents()
        self.assertEqual(
            [(popup._history_table.item(row, 1).text(), popup._history_table.item(row, 3).text()) for row in range(2)],
            [("Trả nợ", "56,000,000 VND"), ("Bán hàng", "34,000,000 VND")],
        )

        history_view = TransactionHistoryView(self.sales_controller)
        history_view._start_date.setDate(QDate(2026, 4, 23))
        history_view._end_date.setDate(QDate(2026, 4, 23))
        history_view.reload()
        self._app.processEvents()
        self.assertFalse(history_view._table.isSortingEnabled())
        self.assertEqual(
            [
                (history_view._table.item(row, 0).data(Qt.ItemDataRole.UserRole)[0], history_view._table.item(row, 2).text())
                for row in range(2)
            ],
            [("DEBT_PAYMENT", "56,000,000 VND"), ("INVOICE", "34,000,000 VND")],
        )

        debt_payment_view = DebtPaymentListView(self.customer_controller)
        debt_payment_view.show()
        self._app.processEvents()
        self.assertEqual(debt_payment_view._table.item(0, 2).text(), "56,000,000 VND")
        self.assertEqual(debt_payment_view._table.item(0, 0).data(Qt.ItemDataRole.UserRole), debt_ledger_id)

        inline.deleteLater()
        popup.deleteLater()
        history_view.deleteLater()
        debt_payment_view.deleteLater()


if __name__ == "__main__":
    unittest.main()
