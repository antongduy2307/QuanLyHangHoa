from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from core.enums import PaymentMethod, UnitType
from modules.customer.dto import CustomerDTO
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.sales.models import Invoice
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService


@dataclass(frozen=True, slots=True)
class SellableProductOption:
    product_id: int
    product_code_base: str
    product_name: str
    unit_mode: str
    enabled_prices: dict[UnitType, Decimal]


class SalesController:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_customers(self) -> Sequence[CustomerDTO]:
        service = CustomerService(CustomerRepository(self._session_factory))
        return service.list_customers()

    def list_sellable_products(self) -> list[SellableProductOption]:
        repository = InventoryRepository(self._session_factory)
        products = repository.list_products()
        options: list[SellableProductOption] = []
        for product in products:
            enabled_prices = {
                price.unit_type: price.price
                for price in product.prices
                if price.is_enabled
            }
            if enabled_prices:
                options.append(
                    SellableProductOption(
                        product_id=product.id,
                        product_code_base=product.product_code_base,
                        product_name=product.product_name,
                        unit_mode=product.unit_mode.value,
                        enabled_prices=enabled_prices,
                    )
                )
        repository.session.close()
        return options

    def list_invoices(self) -> Sequence[Invoice]:
        repository = SalesRepository(self._session_factory)
        invoices = repository.list_invoices()
        repository.session.close()
        return invoices

    def search_invoices(self, query: str) -> Sequence[Invoice]:
        repository = SalesRepository(self._session_factory)
        invoices = repository.search_invoices_by_code(query)
        repository.session.close()
        return invoices

    def get_invoice_detail(self, invoice_id: int) -> Invoice:
        repository = SalesRepository(self._session_factory)
        invoice = repository.get_invoice(invoice_id)
        repository.session.close()
        return invoice

    def create_invoice(
        self,
        *,
        customer_id: int | None,
        customer_snapshot_name: str,
        invoice_datetime: datetime,
        items: list[Mapping[str, object]],
        paid_amount: Decimal,
        payment_method: PaymentMethod | None,
        note: str | None = None,
    ) -> object:
        service = SalesService(SalesRepository(self._session_factory))
        return service.create_invoice(
            customer_id=customer_id,
            customer_snapshot_name=customer_snapshot_name,
            invoice_datetime=invoice_datetime,
            items=items,
            paid_amount=paid_amount,
            payment_method=payment_method,
            note=note,
        )

    def update_invoice(self, invoice_id: int, *, items: list[Mapping[str, object]], note: str | None = None) -> object:
        service = SalesService(SalesRepository(self._session_factory))
        return service.update_invoice(invoice_id, items=items, note=note)

    def delete_invoice(self, invoice_id: int) -> None:
        service = SalesService(SalesRepository(self._session_factory))
        service.delete_invoice(invoice_id)
