from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from PyQt6.QtWidgets import QApplication
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.db import Base, _ensure_invoice_mixed_sale_return_columns
from core.enums import InvoiceLineType, UnitMode, UnitType
from core.exceptions import ValidationError
from modules.customer.models import Customer
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.models import Product, ProductPrice
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.reporting.repository import ReportingRepository
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService
from modules.sales.ui.invoice_items_table import (
    LINE_TYPE_COLUMN,
    RETURN_ROW_BACKGROUND,
    SALE_ROW_BACKGROUND,
    InvoiceItemsTable,
)
import modules.orders.models  # noqa: F401
import modules.returns.models  # noqa: F401


T0 = datetime(2026, 11, 11, 9, 0, 0)


class _MixedInvoiceBase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.sales_repository = SalesRepository(self.Session)
        self.inventory_service = InventoryService(InventoryRepository(self.Session))
        self.customer_service = CustomerService(CustomerRepository(self.Session))
        self.sales_service = SalesService(
            self.sales_repository,
            inventory_service=self.inventory_service,
            customer_service=self.customer_service,
        )
        self.bao_id = self._create_product("P-BAO", UnitMode.BAO_KG, UnitType.BAO, "100")
        self.bich_id = self._create_product("P-BICH", UnitMode.BICH, UnitType.BICH, "20")
        self.customer_id = self._create_customer("Khach quen")

    def tearDown(self) -> None:
        self.sales_repository.session.close()
        self.engine.dispose()

    def _create_product(self, code: str, mode: UnitMode, unit: UnitType, price: str) -> int:
        session = self.sales_repository.session
        product = Product(product_code_base=code, product_name=code, unit_mode=mode, is_active=True)
        session.add(product)
        session.flush()
        session.add(ProductPrice(product_id=product.id, unit_type=unit, price=Decimal(price), is_enabled=True))
        session.commit()
        return product.id

    def _create_customer(self, name: str) -> int:
        customer = Customer(customer_name=name, phone=None, current_balance=Decimal("0"), total_sales=Decimal("0"))
        self.sales_repository.session.add(customer)
        self.sales_repository.session.commit()
        return customer.id

    def _stock(self, product_id: int, unit: UnitType) -> Decimal:
        return self.inventory_service.get_available_quantity(product_id, unit)

    def _customer(self) -> Customer:
        customer = self.customer_service.get_customer(self.customer_id)
        self.sales_repository.session.refresh(customer)
        return customer

    @staticmethod
    def _sale(product_id: int, unit: UnitType, quantity: str, **extra: object) -> dict[str, object]:
        return {"product_id": product_id, "unit_type": unit, "quantity": Decimal(quantity), **extra}

    @staticmethod
    def _return(product_id: int, unit: UnitType, quantity: str, **extra: object) -> dict[str, object]:
        return {
            "product_id": product_id,
            "unit_type": unit,
            "quantity": Decimal(quantity),
            "line_type": InvoiceLineType.RETURN,
            **extra,
        }


class MixedInvoiceServiceTestCase(_MixedInvoiceBase):
    def test_walk_in_sale_and_return_nets_amount_and_moves_stock_both_ways(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=T0,
            items=[self._sale(self.bao_id, UnitType.BAO, "3"), self._return(self.bich_id, UnitType.BICH, "2")],
            paid_amount=Decimal("260"),
        )

        self.assertEqual(invoice.total_amount, Decimal("300"))
        self.assertEqual(invoice.return_amount, Decimal("40"))
        self.assertEqual(invoice.net_amount, Decimal("260"))
        self.assertTrue(invoice.has_return_lines)
        self.assertEqual(self._stock(self.bao_id, UnitType.BAO), Decimal("-3"))
        self.assertEqual(self._stock(self.bich_id, UnitType.BICH), Decimal("2"))

    def test_walk_in_must_pay_net_amount(self) -> None:
        with self.assertRaises(ValidationError):
            self.sales_service.create_invoice(
                customer_id=None,
                customer_snapshot_name="Khach le",
                invoice_datetime=T0,
                items=[self._sale(self.bao_id, UnitType.BAO, "3"), self._return(self.bich_id, UnitType.BICH, "2")],
                paid_amount=Decimal("259"),
            )

    def test_walk_in_negative_invoice_requires_zero_payment(self) -> None:
        with self.assertRaises(ValidationError):
            self.sales_service.create_invoice(
                customer_id=None,
                customer_snapshot_name="Khach le",
                invoice_datetime=T0,
                items=[self._return(self.bao_id, UnitType.BAO, "2")],
                paid_amount=Decimal("10"),
            )

        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=T0,
            items=[self._sale(self.bich_id, UnitType.BICH, "1"), self._return(self.bao_id, UnitType.BAO, "2")],
            paid_amount=Decimal("0"),
        )
        self.assertEqual(invoice.net_amount, Decimal("-180"))
        self.assertEqual(self._stock(self.bao_id, UnitType.BAO), Decimal("2"))

    def test_custom_return_price_is_used(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=T0,
            items=[
                self._sale(self.bao_id, UnitType.BAO, "1", unit_price=Decimal("150")),
                self._return(self.bao_id, UnitType.BAO, "1", unit_price=Decimal("80")),
            ],
            paid_amount=Decimal("70"),
        )
        self.assertEqual(invoice.total_amount, Decimal("150"))
        self.assertEqual(invoice.return_amount, Decimal("80"))
        self.assertEqual(len(invoice.items), 2)
        self.assertEqual(self._stock(self.bao_id, UnitType.BAO), Decimal("0"))

    def test_customer_negative_invoice_reduces_debt_and_total_sales(self) -> None:
        self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=T0,
            items=[self._sale(self.bao_id, UnitType.BAO, "10")],
            paid_amount=Decimal("0"),
        )
        self.assertEqual(self._customer().current_balance, Decimal("1000"))
        self.assertEqual(self._customer().total_sales, Decimal("1000"))

        mixed = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=datetime(2026, 11, 11, 10, 0, 0),
            items=[self._sale(self.bich_id, UnitType.BICH, "5"), self._return(self.bao_id, UnitType.BAO, "4")],
            paid_amount=Decimal("0"),
        )
        self.assertEqual(mixed.net_amount, Decimal("-300"))
        self.assertEqual(self._customer().current_balance, Decimal("700"))
        self.assertEqual(self._customer().total_sales, Decimal("700"))

        self.sales_service.delete_invoice(mixed.id)
        self.assertEqual(self._customer().current_balance, Decimal("1000"))
        self.assertEqual(self._customer().total_sales, Decimal("1000"))
        self.assertEqual(self._stock(self.bao_id, UnitType.BAO), Decimal("-10"))
        self.assertEqual(self._stock(self.bich_id, UnitType.BICH), Decimal("0"))

    def test_customer_negative_invoice_can_create_store_credit_below_zero(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=T0,
            items=[self._return(self.bao_id, UnitType.BAO, "2")],
            paid_amount=Decimal("0"),
        )
        self.assertEqual(self._customer().current_balance, Decimal("-200"))
        self.assertEqual(self._customer().total_sales, Decimal("0"))
        self.assertEqual(invoice.sales_delta_applied, Decimal("0"))

        self.sales_service.delete_invoice(invoice.id)
        self.assertEqual(self._customer().current_balance, Decimal("0"))
        self.assertEqual(self._stock(self.bao_id, UnitType.BAO), Decimal("0"))

    def test_zero_net_invoice_for_customer_has_no_charge_and_deletes_cleanly(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=T0,
            items=[self._sale(self.bao_id, UnitType.BAO, "1"), self._return(self.bao_id, UnitType.BAO, "1")],
            paid_amount=Decimal("0"),
        )
        self.assertEqual(invoice.net_amount, Decimal("0"))
        self.assertEqual(self._customer().current_balance, Decimal("0"))
        self.sales_service.delete_invoice(invoice.id)
        self.assertEqual(self._stock(self.bao_id, UnitType.BAO), Decimal("0"))

    def test_update_switching_line_to_return_reverses_stock(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=T0,
            items=[self._sale(self.bao_id, UnitType.BAO, "3")],
            paid_amount=Decimal("0"),
        )
        self.assertEqual(self._stock(self.bao_id, UnitType.BAO), Decimal("-3"))

        updated = self.sales_service.update_invoice(
            invoice.id,
            items=[self._return(self.bao_id, UnitType.BAO, "3")],
            paid_amount=Decimal("0"),
        )
        self.assertEqual(updated.total_amount, Decimal("0"))
        self.assertEqual(updated.return_amount, Decimal("300"))
        self.assertEqual(self._stock(self.bao_id, UnitType.BAO), Decimal("3"))
        self.assertEqual(self._customer().current_balance, Decimal("-300"))
        self.assertEqual(self._customer().total_sales, Decimal("0"))

    def test_legacy_invoice_without_sales_delta_rolls_back_total_amount(self) -> None:
        invoice = self.sales_service.create_invoice(
            customer_id=self.customer_id,
            customer_snapshot_name="Khach quen",
            invoice_datetime=T0,
            items=[self._sale(self.bao_id, UnitType.BAO, "2")],
            paid_amount=Decimal("0"),
        )
        invoice.sales_delta_applied = None  # simulate an invoice created before this feature
        self.sales_repository.session.commit()

        self.sales_service.delete_invoice(invoice.id)
        self.assertEqual(self._customer().total_sales, Decimal("0"))

    def test_invalid_line_type_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.sales_service.create_invoice(
                customer_id=None,
                customer_snapshot_name="Khach le",
                invoice_datetime=T0,
                items=[self._sale(self.bao_id, UnitType.BAO, "1", line_type="EXCHANGE")],
                paid_amount=Decimal("100"),
            )


class MixedInvoiceReportingTestCase(_MixedInvoiceBase):
    def test_return_lines_count_as_returns_not_revenue(self) -> None:
        self.sales_service.create_invoice(
            customer_id=None,
            customer_snapshot_name="Khach le",
            invoice_datetime=T0,
            items=[self._sale(self.bao_id, UnitType.BAO, "3"), self._return(self.bao_id, UnitType.BAO, "1")],
            paid_amount=Decimal("200"),
        )
        repository = ReportingRepository(self.Session)
        start, end = datetime(2026, 11, 11), datetime(2026, 11, 11, 23, 59, 59)

        aggregate = repository.get_sales_summary_aggregate(start, end)
        self.assertEqual(aggregate.gross_sales_amount, Decimal("300"))
        self.assertEqual(aggregate.return_amount, Decimal("100"))

        sold = repository.get_sold_product_rows(start, end)
        self.assertEqual([(row.quantity, row.amount) for row in sold], [(Decimal("3"), Decimal("300"))])
        returned = repository.get_returned_product_rows(start, end)
        self.assertEqual([(row.quantity, row.amount) for row in returned], [(Decimal("1"), Decimal("100"))])

        self.assertEqual([row.amount for row in repository.get_daily_sales_rows(start, end)], [Decimal("300")])
        self.assertEqual([row.amount for row in repository.get_daily_return_rows(start, end)], [Decimal("100")])


class MixedInvoiceMigrationTestCase(unittest.TestCase):
    def test_adds_columns_to_legacy_schema_and_is_idempotent(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE invoices (id INTEGER PRIMARY KEY, total_amount NUMERIC(14, 2))"))
            connection.execute(text("CREATE TABLE invoice_items (id INTEGER PRIMARY KEY, invoice_id INTEGER)"))
            connection.execute(text("INSERT INTO invoices (id, total_amount) VALUES (1, 100)"))
            connection.execute(text("INSERT INTO invoice_items (id, invoice_id) VALUES (1, 1)"))

        _ensure_invoice_mixed_sale_return_columns(engine)
        _ensure_invoice_mixed_sale_return_columns(engine)

        with engine.begin() as connection:
            line_type = connection.execute(text("SELECT line_type FROM invoice_items WHERE id = 1")).scalar_one()
            return_amount, sales_delta = connection.execute(
                text("SELECT return_amount, sales_delta_applied FROM invoices WHERE id = 1")
            ).one()
        self.assertEqual(line_type, "SALE")
        self.assertEqual(Decimal(str(return_amount)), Decimal("0"))
        self.assertIsNone(sales_delta)
        engine.dispose()


class InvoiceItemsTableLineTypeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.table = InvoiceItemsTable("test.mixed_items", show_line_type=True)

    def tearDown(self) -> None:
        self.table.deleteLater()

    @staticmethod
    def _item(product_id: int, quantity: str, price: str, line_type: InvoiceLineType | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "product_id": product_id,
            "product_code_base": f"P{product_id}",
            "product_name": f"Hang {product_id}",
            "unit_type": UnitType.BAO,
            "quantity": Decimal(quantity),
            "unit_price": Decimal(price),
            "enabled_prices": {UnitType.BAO: Decimal(price)},
        }
        if line_type is not None:
            payload["line_type"] = line_type
        return payload

    def test_sale_and_return_lines_are_separate_and_net_total(self) -> None:
        self.table.add_or_merge_item(self._item(1, "2", "100"))
        self.table.add_or_merge_item(self._item(1, "1", "100", InvoiceLineType.RETURN))
        self.table.add_or_merge_item(self._item(1, "1", "100"))

        self.assertEqual(self.table.rowCount(), 2)
        self.assertEqual(self.table.sale_total(), Decimal("300"))
        self.assertEqual(self.table.return_total(), Decimal("100"))
        self.assertEqual(self.table.total_amount(), Decimal("200"))
        self.assertEqual(
            [payload["line_type"] for payload in self.table.items_payload()],
            [InvoiceLineType.SALE, InvoiceLineType.RETURN],
        )

    def test_row_background_and_toggle_button(self) -> None:
        self.table.add_or_merge_item(self._item(1, "1", "100"))
        self.table.add_or_merge_item(self._item(2, "1", "50", InvoiceLineType.RETURN))

        self.assertEqual(self.table.item(0, 1).background().color().name().upper(), SALE_ROW_BACKGROUND)
        self.assertEqual(self.table.item(1, 1).background().color().name().upper(), RETURN_ROW_BACKGROUND)
        self.assertEqual(self.table.cellWidget(0, LINE_TYPE_COLUMN).text(), "BÁN")
        self.assertEqual(self.table.cellWidget(1, LINE_TYPE_COLUMN).text(), "TRẢ")

        self.table.cellWidget(0, LINE_TYPE_COLUMN).click()
        self.assertEqual(self.table.line_types(), [InvoiceLineType.RETURN, InvoiceLineType.RETURN])
        self.assertEqual(self.table.total_amount(), Decimal("-150"))
        self.assertEqual(self.table.item(0, 1).background().color().name().upper(), RETURN_ROW_BACKGROUND)

    def test_toggle_merges_into_existing_line_of_same_type(self) -> None:
        self.table.add_or_merge_item(self._item(1, "2", "100"))
        self.table.add_or_merge_item(self._item(1, "1", "100", InvoiceLineType.RETURN))
        self.table.toggle_line_type_at(1)
        self.assertEqual(self.table.rowCount(), 1)
        self.assertEqual(self.table.items_payload()[0]["quantity"], Decimal("3"))

    def test_line_type_column_is_shown_first(self) -> None:
        self.assertEqual(self.table.horizontalHeader().visualIndex(LINE_TYPE_COLUMN), 0)
        self.assertEqual(self.table.horizontalHeaderItem(LINE_TYPE_COLUMN).text(), "Loại")

    def test_table_without_line_type_keeps_seven_columns(self) -> None:
        legacy = InvoiceItemsTable("test.legacy_items")
        try:
            self.assertEqual(legacy.columnCount(), 7)
            legacy.add_or_merge_item(self._item(1, "1", "100"))
            self.assertEqual(legacy.items_payload()[0]["line_type"], InvoiceLineType.SALE)
        finally:
            legacy.deleteLater()


if __name__ == "__main__":
    unittest.main()
