from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.db import SessionFactory
from core.enums import InvoiceStatus, PaymentMethod, UnitType
from core.exceptions import ValidationError
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.sales.dto import InvoiceDTO
from modules.sales.mappers import to_dto
from modules.sales.models import Invoice, InvoiceItem
from modules.sales.repository import SalesRepository


@dataclass(frozen=True, slots=True)
class SalesLineInput:
    product_id: int
    unit_type: UnitType
    quantity: Decimal


class SalesService:
    def __init__(
        self,
        repository: SalesRepository,
        inventory_service: InventoryService | None = None,
        customer_service: CustomerService | None = None,
    ) -> None:
        self._repository = repository
        self._inventory_service = inventory_service or InventoryService(InventoryRepository(repository._session_factory))
        self._customer_service = customer_service or CustomerService(CustomerRepository(repository._session_factory))

    def list_invoices(self) -> Sequence[InvoiceDTO]:
        return [to_dto(invoice) for invoice in self._repository.list_invoices()]

    def create_invoice(
        self,
        *,
        customer_id: int | None,
        customer_snapshot_name: str,
        invoice_datetime: datetime,
        items: list[Mapping[str, object]],
        paid_amount: Decimal | int | str | None = None,
        payment_method: PaymentMethod | str | None = None,
        note: str | None = None,
    ) -> Invoice:
        session = self._repository.session
        self._bind_shared_session(session)

        normalized_items = self._normalize_items(items)
        normalized_payment_method = self._normalize_payment_method(payment_method)
        actual_paid_amount = self._normalize_paid_amount(paid_amount)

        with session.begin():
            customer = self._customer_service.get_customer(customer_id) if customer_id is not None else None
            snapshot_name = self._resolve_customer_snapshot_name(customer, customer_snapshot_name)
            invoice = Invoice(
                invoice_code=self._repository.generate_invoice_code(invoice_datetime),
                customer_id=customer.id if customer is not None else None,
                customer_snapshot_name=snapshot_name,
                invoice_datetime=invoice_datetime,
                total_amount=Decimal("0"),
                paid_amount=None,
                payment_method=normalized_payment_method,
                note=note,
                status=InvoiceStatus.COMPLETED,
            )
            session.add(invoice)
            session.flush()

            total_amount = Decimal("0")
            for line in normalized_items:
                product = self._inventory_service.get_product(line.product_id)
                if not product.is_active:
                    raise ValidationError(f"Product {product.product_code_base} is inactive.")
                product.validate_price_unit_type(line.unit_type)

                price_row = next(
                    (price for price in product.prices if price.unit_type == line.unit_type and price.is_enabled),
                    None,
                )
                if price_row is None:
                    raise ValidationError(
                        f"No enabled price found for product {product.product_code_base} and unit {line.unit_type.value}."
                    )

                line_total = line.quantity * price_row.price
                total_amount += line_total
                self._inventory_service.decrease_stock(product.id, line.quantity, line.unit_type)

                invoice.items.append(
                    InvoiceItem(
                        product_id=product.id,
                        unit_type=line.unit_type,
                        quantity=line.quantity,
                        unit_price=price_row.price,
                        line_total=line_total,
                        product_code_snapshot=product.product_code_base,
                        product_name_snapshot=product.product_name,
                    )
                )

            invoice.total_amount = total_amount
            invoice.paid_amount = self._recorded_paid_amount_for_schema(actual_paid_amount, total_amount)

            if customer is not None:
                self._customer_service.adjust_balance(
                    customer.id,
                    total_amount,
                    "INVOICE",
                    invoice.id,
                    note=f"Invoice charge {invoice.invoice_code}",
                    event_type="INVOICE_CHARGE",
                )
                if actual_paid_amount != Decimal("0"):
                    self._customer_service.adjust_balance(
                        customer.id,
                        -actual_paid_amount,
                        "INVOICE",
                        invoice.id,
                        note=f"Invoice payment {invoice.invoice_code}",
                        event_type="INVOICE_PAYMENT",
                    )
                self._customer_service.increase_sales(customer.id, total_amount)

            session.flush()
            return invoice

    def _bind_shared_session(self, session: object) -> None:
        self._repository.use_session(session)
        self._inventory_service.use_session(session)
        self._customer_service.use_session(session)

    def _normalize_items(self, items: list[Mapping[str, object]]) -> list[SalesLineInput]:
        if not items:
            raise ValidationError("items must not be empty.")

        normalized: list[SalesLineInput] = []
        for item in items:
            product_id = self._require_int(item, "product_id")
            unit_type = self._normalize_unit_type(item.get("unit_type"))
            quantity = self._require_positive_decimal(item.get("quantity"), "quantity")
            normalized.append(SalesLineInput(product_id=product_id, unit_type=unit_type, quantity=quantity))
        return normalized

    def _normalize_unit_type(self, value: object) -> UnitType:
        if isinstance(value, UnitType):
            return value
        if value is None:
            raise ValidationError("unit_type is required.")
        try:
            return UnitType(str(value))
        except ValueError as exc:
            raise ValidationError(f"Unsupported unit_type: {value}") from exc

    def _normalize_payment_method(self, value: PaymentMethod | str | None) -> PaymentMethod | None:
        if value is None:
            return None
        if isinstance(value, PaymentMethod):
            return value
        try:
            return PaymentMethod(str(value))
        except ValueError as exc:
            raise ValidationError(f"Unsupported payment_method: {value}") from exc

    def _normalize_paid_amount(self, value: Decimal | int | str | None) -> Decimal:
        if value is None:
            return Decimal("0")
        amount = self._to_decimal(value)
        if amount < Decimal("0"):
            raise ValidationError("paid_amount must be >= 0.")
        return amount

    def _resolve_customer_snapshot_name(self, customer: object, raw_name: str) -> str:
        normalized = raw_name.strip()
        if customer is None:
            return normalized or "Khach le"
        return normalized or customer.customer_name

    def _recorded_paid_amount_for_schema(self, actual_paid_amount: Decimal, total_amount: Decimal) -> Decimal | None:
        if actual_paid_amount == Decimal("0"):
            return Decimal("0")
        return min(actual_paid_amount, total_amount)

    def _require_int(self, item: Mapping[str, object], key: str) -> int:
        raw_value = item.get(key)
        if raw_value is None:
            raise ValidationError(f"{key} is required.")
        return int(raw_value)

    def _require_positive_decimal(self, value: object, field_name: str) -> Decimal:
        if value is None:
            raise ValidationError(f"{field_name} is required.")
        amount = self._to_decimal(value)
        if amount <= Decimal("0"):
            raise ValidationError(f"{field_name} must be > 0.")
        return amount

    @staticmethod
    def _to_decimal(value: Decimal | int | str | object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
