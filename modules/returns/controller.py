from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session, sessionmaker

from core.enums import ReturnHandlingMode, UnitType
from modules.customer.dto import CustomerDTO
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.repository import InventoryRepository
from modules.returns.repository import ReturnsRepository
from modules.returns.service import ReturnService
from modules.sales.repository import SalesRepository

if TYPE_CHECKING:
    from modules.returns.models import ReturnInvoice


@dataclass(frozen=True, slots=True)
class SourceInvoiceSearchRow:
    invoice_id: int
    invoice_code: str
    customer_label: str
    invoice_datetime: datetime


@dataclass(frozen=True, slots=True)
class SourceInvoiceItemRow:
    source_invoice_item_id: int
    product_code_snapshot: str
    product_name_snapshot: str
    unit_type: str
    purchased_quantity: Decimal
    already_returned_quantity: Decimal
    remaining_returnable_quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True, slots=True)
class SourceInvoiceDetail:
    invoice_id: int
    invoice_code: str
    invoice_datetime: datetime
    customer_name: str
    customer_id: int | None
    current_balance: Decimal | None
    items: tuple[SourceInvoiceItemRow, ...]


@dataclass(frozen=True, slots=True)
class ReturnEditDetail:
    return_invoice_id: int
    return_code: str
    return_datetime: datetime
    source_invoice_id: int
    source_invoice_code: str
    customer_name: str
    customer_id: int | None
    current_balance: Decimal | None
    handling_mode: ReturnHandlingMode
    note: str | None
    items: tuple[SourceInvoiceItemRow, ...]
    selected_quantities: dict[int, Decimal]


@dataclass(frozen=True, slots=True)
class QuickReturnProductOption:
    product_id: int
    product_code_base: str
    product_name: str
    enabled_prices: dict[UnitType, Decimal]


class ReturnController:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_return_invoices(self) -> Sequence[ReturnInvoice]:
        repository = ReturnsRepository(self._session_factory)
        invoices = repository.list_return_invoices()
        repository.session.close()
        return invoices

    def search_return_invoices(self, query: str) -> Sequence[ReturnInvoice]:
        repository = ReturnsRepository(self._session_factory)
        invoices = repository.search_return_invoices_by_code(query)
        repository.session.close()
        return invoices

    def get_return_invoice_detail(self, return_invoice_id: int) -> ReturnInvoice:
        repository = ReturnsRepository(self._session_factory)
        invoice = repository.get_return_invoice(return_invoice_id)
        repository.session.close()
        return invoice

    def get_return_edit_detail(self, return_invoice_id: int) -> ReturnEditDetail:
        returns_repository = ReturnsRepository(self._session_factory)
        sales_repository = SalesRepository(self._session_factory)
        customer_service = CustomerService(CustomerRepository(self._session_factory))

        return_invoice = returns_repository.get_return_invoice(return_invoice_id)
        if return_invoice.source_invoice_id is None:
            returns_repository.session.close()
            sales_repository.session.close()
            raise ValueError("Chưa hỗ trợ sửa phiếu trả hàng nhanh ở bước này.")

        source_invoice = sales_repository.get_invoice(return_invoice.source_invoice_id)
        current_balance = None
        if return_invoice.customer_id is not None:
            current_balance = customer_service.get_customer(return_invoice.customer_id).current_balance

        current_quantities = {item.source_invoice_item_id: item.quantity for item in return_invoice.items if item.source_invoice_item_id is not None}
        item_rows: list[SourceInvoiceItemRow] = []
        for item in source_invoice.items:
            already_returned = returns_repository.get_total_returned_quantity_excluding_return(item.id, return_invoice.id)
            item_rows.append(
                SourceInvoiceItemRow(
                    source_invoice_item_id=item.id,
                    product_code_snapshot=item.product_code_snapshot,
                    product_name_snapshot=item.product_name_snapshot,
                    unit_type=item.unit_type.value,
                    purchased_quantity=item.quantity,
                    already_returned_quantity=already_returned,
                    remaining_returnable_quantity=item.quantity - already_returned,
                    unit_price=item.unit_price,
                )
            )

        returns_repository.session.close()
        sales_repository.session.close()
        customer_service._repository.session.close()
        return ReturnEditDetail(
            return_invoice_id=return_invoice.id,
            return_code=return_invoice.return_code,
            return_datetime=return_invoice.return_datetime,
            source_invoice_id=source_invoice.id,
            source_invoice_code=source_invoice.invoice_code,
            customer_name=return_invoice.customer_snapshot_name,
            customer_id=return_invoice.customer_id,
            current_balance=current_balance,
            handling_mode=return_invoice.handling_mode,
            note=return_invoice.note,
            items=tuple(item_rows),
            selected_quantities=current_quantities,
        )

    def list_quick_return_customers(self, *, include_inactive: bool = False) -> Sequence[CustomerDTO]:
        service = CustomerService(CustomerRepository(self._session_factory))
        customers = service.list_customers(include_inactive=include_inactive)
        service._repository.session.close()
        return customers

    def list_quick_return_products(self) -> list[QuickReturnProductOption]:
        repository = InventoryRepository(self._session_factory)
        products = repository.list_products()
        options: list[QuickReturnProductOption] = []
        for product in products:
            enabled_prices = {price.unit_type: price.price for price in product.prices if price.is_enabled}
            if enabled_prices:
                options.append(
                    QuickReturnProductOption(
                        product_id=product.id,
                        product_code_base=product.product_code_base,
                        product_name=product.product_name,
                        enabled_prices=enabled_prices,
                    )
                )
        repository.session.close()
        return options

    def search_source_invoices(self, query: str) -> Sequence[SourceInvoiceSearchRow]:
        repository = SalesRepository(self._session_factory)
        invoices = repository.search_invoices_by_code(query)
        repository.session.close()
        return [
            SourceInvoiceSearchRow(
                invoice_id=invoice.id,
                invoice_code=invoice.invoice_code,
                customer_label=invoice.customer_snapshot_name,
                invoice_datetime=invoice.invoice_datetime,
            )
            for invoice in invoices
        ]

    def load_source_invoice_details(self, invoice_id: int) -> SourceInvoiceDetail:
        sales_repository = SalesRepository(self._session_factory)
        returns_repository = ReturnsRepository(self._session_factory)
        customer_service = CustomerService(CustomerRepository(self._session_factory))

        invoice = sales_repository.get_invoice(invoice_id)
        current_balance = None
        if invoice.customer_id is not None:
            current_balance = customer_service.get_customer(invoice.customer_id).current_balance

        item_rows: list[SourceInvoiceItemRow] = []
        for item in invoice.items:
            already_returned = returns_repository.get_total_returned_quantity(item.id)
            item_rows.append(
                SourceInvoiceItemRow(
                    source_invoice_item_id=item.id,
                    product_code_snapshot=item.product_code_snapshot,
                    product_name_snapshot=item.product_name_snapshot,
                    unit_type=item.unit_type.value,
                    purchased_quantity=item.quantity,
                    already_returned_quantity=already_returned,
                    remaining_returnable_quantity=item.quantity - already_returned,
                    unit_price=item.unit_price,
                )
            )

        sales_repository.session.close()
        returns_repository.session.close()
        customer_service._repository.session.close()
        return SourceInvoiceDetail(
            invoice_id=invoice.id,
            invoice_code=invoice.invoice_code,
            invoice_datetime=invoice.invoice_datetime,
            customer_name=invoice.customer_snapshot_name,
            customer_id=invoice.customer_id,
            current_balance=current_balance,
            items=tuple(item_rows),
        )

    def create_return_invoice(
        self,
        *,
        source_invoice_id: int,
        return_datetime: datetime,
        items: list[Mapping[str, object]],
        handling_mode: str,
        note: str | None = None,
    ) -> object:
        service = ReturnService(ReturnsRepository(self._session_factory), sales_repository=SalesRepository(self._session_factory))
        return service.create_return_invoice(
            source_invoice_id=source_invoice_id,
            return_datetime=return_datetime,
            items=items,
            handling_mode=handling_mode,
            note=note,
        )

    def update_return_invoice(
        self,
        return_invoice_id: int,
        *,
        items: list[Mapping[str, object]],
        handling_mode: str,
        return_datetime: datetime | None = None,
        note: str | None = None,
    ) -> object:
        service = ReturnService(ReturnsRepository(self._session_factory), sales_repository=SalesRepository(self._session_factory))
        return service.update_return_invoice(
            return_invoice_id,
            items=items,
            handling_mode=handling_mode,
            return_datetime=return_datetime,
            note=note,
        )

    def update_return_datetime(self, return_invoice_id: int, new_datetime: datetime) -> ReturnInvoice:
        service = ReturnService(ReturnsRepository(self._session_factory), sales_repository=SalesRepository(self._session_factory))
        return service.update_return_datetime(return_invoice_id, new_datetime)

    def delete_return_invoice(self, return_invoice_id: int) -> None:
        service = ReturnService(ReturnsRepository(self._session_factory), sales_repository=SalesRepository(self._session_factory))
        service.delete_return_invoice(return_invoice_id)

    def create_quick_return_invoice(
        self,
        *,
        customer_id: int | None,
        customer_snapshot_name: str,
        return_datetime: datetime,
        items: list[Mapping[str, object]],
        handling_mode: str,
        note: str | None = None,
    ) -> object:
        service = ReturnService(ReturnsRepository(self._session_factory), sales_repository=SalesRepository(self._session_factory))
        return service.create_quick_return_invoice(
            customer_id=customer_id,
            customer_snapshot_name=customer_snapshot_name,
            return_datetime=return_datetime,
            items=items,
            handling_mode=handling_mode,
            note=note,
        )

