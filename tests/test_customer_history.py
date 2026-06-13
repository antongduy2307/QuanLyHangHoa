from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.enums import PaymentMethod, ReturnHandlingMode, UnitMode, UnitType
from modules.customer.controller import CustomerController
from modules.customer.models import Customer
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.models import Product, ProductPrice
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.returns.repository import ReturnsRepository
from modules.returns.service import ReturnService
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService
import modules.returns.models  # noqa: F401


class CustomerHistoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

        self.customer_repository = CustomerRepository(self.Session)
        self.sales_repository = SalesRepository(self.Session)
        self.inventory_repository = InventoryRepository(self.Session)
        self.returns_repository = ReturnsRepository(self.Session)

        self.customer_service = CustomerService(self.customer_repository)
        self.inventory_service = InventoryService(self.inventory_repository)
        self.sales_service = SalesService(
            self.sales_repository,
            inventory_service=self.inventory_service,
            customer_service=self.customer_service,
        )
        self.return_service = ReturnService(
            self.returns_repository,
            sales_repository=self.sales_repository,
            inventory_service=self.inventory_service,
            customer_service=self.customer_service,
        )
        self.customer_controller = CustomerController(self.Session)

        self.product_id = self._create_product_with_price("P-BAO", UnitMode.BAO_KG, [(UnitType.BAO, "100")])
        self.customer_id = self._create_customer("Khach lich su")

    def tearDown(self) -> None:
        self.customer_repository.session.close()
        self.sales_repository.session.close()
        self.inventory_repository.session.close()
        self.returns_repository.session.close()
        self.engine.dispose()

    def _create_product_with_price(self, code: str, unit_mode: UnitMode, prices: list[tuple[UnitType, str]]) -> int:
        session = self.sales_repository.session
        product = Product(product_code_base=code, product_name=code, unit_mode=unit_mode, is_active=True)
        session.add(product)
        session.flush()
        for unit_type, price in prices:
            session.add(ProductPrice(product_id=product.id, unit_type=unit_type, price=Decimal(price), is_enabled=True))
        session.commit()
        return product.id

    def _create_customer(self, name: str) -> int:
        customer = Customer(customer_name=name, phone="0909", address="123", current_balance=Decimal("0"), total_sales=Decimal("0"))
        self.sales_repository.session.add(customer)
        self.sales_repository.session.commit()
        return customer.id

    def test_customer_history_with_only_sales_invoice_still_shows_invoice(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=datetime(2026, 4, 10, 9, 0, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("2")}],
            paid_amount=Decimal("0"),
            payment_method=PaymentMethod.CASH,
        )

        detail = self.customer_controller.get_customer_with_recent_history(self.customer_id, limit=3)

        self.assertEqual(len(detail.recent_history), 1)
        self.assertEqual(detail.recent_history[0].transaction_type, "Bán hàng")
        self.assertEqual(detail.recent_history[0].transaction_kind, "INVOICE")
        self.assertEqual(detail.recent_history[0].transaction_id, invoice.id)
        self.assertEqual(detail.recent_history[0].item_summary, "P-BAO")
        self.assertEqual(detail.recent_history[0].amount, Decimal("200"))

    def test_customer_history_keeps_trade_tab_separate_and_debt_tab_complete(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=datetime(2026, 4, 10, 9, 0, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("3")}],
            paid_amount=Decimal("100"),
            payment_method=PaymentMethod.CASH,
        )
        self.customer_service.pay_debt(
            self.customer_id,
            Decimal("25"),
            note="Khach tra no",
            payment_datetime=datetime(2026, 4, 10, 10, 0, 0),
        )
        return_invoice = self.return_service.create_return_invoice(
            source_invoice_id=invoice.id,
            return_datetime=datetime(2026, 4, 10, 11, 0, 0),
            items=[{"source_invoice_item_id": invoice.items[0].id, "quantity": Decimal("1")}],
            handling_mode=ReturnHandlingMode.REFUND_NOW,
        )

        trade_entries = self.customer_controller.list_customer_trade_history(self.customer_id)
        debt_entries = self.customer_controller.list_customer_debt_history(self.customer_id)

        self.assertEqual(
            [(entry.transaction_kind, entry.transaction_id, entry.transaction_type) for entry in trade_entries],
            [("RETURN", return_invoice.id, "Trả hàng"), ("INVOICE", invoice.id, "Bán hàng")],
        )
        self.assertEqual(
            [(entry.transaction_kind, entry.transaction_type, entry.amount) for entry in debt_entries],
            [
                ("RETURN", "Trả hàng", Decimal("100")),
                ("DEBT_PAYMENT", "Trả nợ", Decimal("25")),
                ("DEBT_PAYMENT", "Trả nợ", Decimal("100")),
                ("INVOICE", "Bán hàng", Decimal("300")),
            ],
        )
        self.assertFalse(any(entry.transaction_kind == "DEBT_PAYMENT" for entry in trade_entries))

    def test_customer_history_shows_overpayment_as_separate_debt_payment_entry(self) -> None:
        self.customer_service.adjust_balance(self.customer_id, Decimal("120"), "MANUAL", 9)
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=datetime(2026, 4, 10, 12, 0, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1")}],
            paid_amount=Decimal("180"),
            payment_method=PaymentMethod.CASH,
        )

        trade_entries = self.customer_controller.list_customer_trade_history(self.customer_id)
        debt_entries = self.customer_controller.list_customer_debt_history(self.customer_id)

        self.assertTrue(any(entry.transaction_kind == "INVOICE" and entry.transaction_id == invoice.id for entry in trade_entries))
        self.assertTrue(any(entry.transaction_kind == "DEBT_PAYMENT" and entry.amount == Decimal("180") for entry in debt_entries))
        self.assertFalse(any(entry.transaction_kind == "DEBT_PAYMENT" for entry in trade_entries))
        self.assertTrue(any(entry.transaction_kind == "INVOICE" and entry.transaction_id == invoice.id for entry in debt_entries))

    def test_customer_debt_history_includes_opening_balance_and_first_overpayment_invoice_uses_it(self) -> None:
        self.customer_service.update_customer(
            self.customer_id,
            customer_name="Khach lich su",
            phone="0909",
            address="123",
            note=None,
            target_balance=Decimal("5000000"),
        )
        self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=datetime(2026, 4, 10, 13, 0, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1150")}],
            paid_amount=Decimal("150000"),
            payment_method=PaymentMethod.CASH,
        )

        debt_entries = self.customer_controller.list_customer_debt_history(self.customer_id)

        self.assertEqual(
            [(entry.transaction_type, entry.amount, entry.balance_after) for entry in debt_entries[:3]],
            [
                ("Trả nợ", Decimal("150000"), Decimal("4965000")),
                ("Bán hàng", Decimal("115000"), Decimal("5115000")),
                ("Điều chỉnh công nợ", Decimal("5000000"), Decimal("5000000")),
            ],
        )

    def test_customer_debt_history_uses_selected_balance_adjustment_datetime(self) -> None:
        selected_datetime = datetime(2026, 5, 11, 9, 30, 0)
        self.customer_service.adjust_balance(
            self.customer_id,
            Decimal("100"),
            "MANUAL",
            90,
            transaction_datetime=datetime(2026, 5, 10, 8, 0, 0),
        )
        self.customer_service.update_customer(
            self.customer_id,
            customer_name="Khach lich su",
            phone="0909",
            address="123",
            note=None,
            target_balance=Decimal("80"),
            balance_transaction_datetime=selected_datetime,
        )

        debt_entries = self.customer_controller.list_customer_debt_history(self.customer_id)
        adjustment = next(
            entry
            for entry in debt_entries
            if entry.transaction_kind == "BALANCE_ADJUSTMENT"
        )

        self.assertEqual(adjustment.transaction_datetime, selected_datetime)
        self.assertEqual(adjustment.balance_after, Decimal("80"))

    def test_customer_debt_history_continues_from_initial_debt_across_following_invoices(self) -> None:
        self.customer_service.update_customer(
            self.customer_id,
            customer_name="Khach lich su",
            phone="0909",
            address="123",
            note=None,
            target_balance=Decimal("5000000"),
        )
        self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=datetime(2026, 4, 10, 13, 0, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1150")}],
            paid_amount=Decimal("150000"),
            payment_method=PaymentMethod.CASH,
        )
        self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=datetime(2026, 4, 10, 14, 0, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1000")}],
            paid_amount=Decimal("0"),
            payment_method=PaymentMethod.CASH,
        )

        debt_entries = self.customer_controller.list_customer_debt_history(self.customer_id)

        self.assertEqual(
            [(entry.transaction_type, entry.amount, entry.balance_after) for entry in debt_entries[:4]],
            [
                ("Bán hàng", Decimal("100000"), Decimal("5065000")),
                ("Trả nợ", Decimal("150000"), Decimal("4965000")),
                ("Bán hàng", Decimal("115000"), Decimal("5115000")),
                ("Điều chỉnh công nợ", Decimal("5000000"), Decimal("5000000")),
            ],
        )

    def test_customer_debt_history_reads_as_newest_first_batch_snapshot_for_overpayment(self) -> None:
        self.customer_service.adjust_balance(
            self.customer_id,
            Decimal("22000000"),
            "MANUAL",
            11,
            transaction_datetime=datetime(2026, 4, 10, 12, 0, 0),
        )
        invoice_datetime = datetime(2026, 4, 10, 13, 0, 0)
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=invoice_datetime,
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("340000")}],
            paid_amount=Decimal("56000000"),
            payment_method=PaymentMethod.CASH,
        )

        debt_entries = self.customer_controller.list_customer_debt_history(self.customer_id)
        paired_entries = [entry for entry in debt_entries if entry.transaction_datetime == invoice_datetime]

        self.assertEqual(
            [(entry.transaction_kind, entry.amount, entry.balance_after) for entry in paired_entries],
            [
                ("DEBT_PAYMENT", Decimal("56000000"), Decimal("0")),
                ("INVOICE", invoice.total_amount, Decimal("56000000")),
            ],
        )
        self.assertEqual(paired_entries[0].source_ref_type, "INVOICE")
        self.assertEqual(paired_entries[0].source_ref_id, invoice.id)

    def test_recent_customer_history_newest_first_shows_overpayment_debt_payment_before_invoice_on_same_timestamp(self) -> None:
        self.customer_service.adjust_balance(
            self.customer_id,
            Decimal("22000000"),
            "MANUAL",
            12,
            transaction_datetime=datetime(2026, 4, 23, 1, 0, 0),
        )
        invoice_datetime = datetime(2026, 4, 23, 1, 50, 0)
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=invoice_datetime,
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("340000")}],
            paid_amount=Decimal("56000000"),
            payment_method=PaymentMethod.CASH,
        )

        detail = self.customer_controller.get_customer_with_recent_history(self.customer_id, limit=2)

        self.assertEqual(
            [(entry.transaction_kind, entry.amount) for entry in detail.recent_history],
            [
                ("DEBT_PAYMENT", Decimal("56000000")),
                ("INVOICE", invoice.total_amount),
            ],
        )

    def test_customer_debt_history_newest_first_keeps_snapshot_balance_for_each_row(self) -> None:
        self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=datetime(2026, 4, 23, 18, 14, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1150")}],
            paid_amount=Decimal("0"),
            payment_method=PaymentMethod.CASH,
        )
        self.customer_service.pay_debt(
            self.customer_id,
            Decimal("100000"),
            payment_datetime=datetime(2026, 4, 23, 18, 19, 0),
        )
        self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=datetime(2026, 4, 23, 18, 20, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1150")}],
            paid_amount=Decimal("0"),
            payment_method=PaymentMethod.CASH,
        )
        self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach lich su",
            invoice_datetime=datetime(2026, 4, 23, 18, 23, 0),
            items=[{"product_id": self.product_id, "unit_type": UnitType.BAO, "quantity": Decimal("1100")}],
            paid_amount=Decimal("25000"),
            payment_method=PaymentMethod.CASH,
        )
        self.customer_service.pay_debt(
            self.customer_id,
            Decimal("5000"),
            payment_datetime=datetime(2026, 4, 23, 18, 23, 30),
        )

        debt_entries = self.customer_controller.list_customer_debt_history(self.customer_id)

        self.assertEqual(
            [(entry.transaction_type, entry.amount, entry.balance_after) for entry in debt_entries],
            [
                ("Trả nợ", Decimal("5000"), Decimal("210000")),
                ("Trả nợ", Decimal("25000"), Decimal("215000")),
                ("Bán hàng", Decimal("110000"), Decimal("240000")),
                ("Bán hàng", Decimal("115000"), Decimal("130000")),
                ("Trả nợ", Decimal("100000"), Decimal("15000")),
                ("Bán hàng", Decimal("115000"), Decimal("115000")),
            ],
        )


if __name__ == "__main__":
    unittest.main()
