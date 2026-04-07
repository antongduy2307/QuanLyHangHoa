from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

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
        transaction_context = session.begin_nested() if session.in_transaction() else session.begin()

        with transaction_context:
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

            self._apply_invoice_state(invoice, normalized_items, actual_paid_amount, note_override=note)
            session.flush()
            return invoice

    def update_invoice(
        self,
        invoice_id: int,
        *,
        items: list[Mapping[str, object]],
        note: str | None = None,
    ) -> Invoice:
        session = self._repository.session
        self._bind_shared_session(session)
        normalized_items = self._normalize_items(items)
        transaction_context = session.begin_nested() if session.in_transaction() else session.begin()

        with transaction_context:
            invoice = self._repository.get_invoice(invoice_id)
            preserved_paid_amount = invoice.paid_amount or Decimal("0")
            self._rollback_invoice_effects(invoice)
            invoice.items.clear()
            session.flush()

            self._apply_invoice_state(invoice, normalized_items, preserved_paid_amount, note_override=note)
            session.flush()
            return invoice

    def delete_invoice(self, invoice_id: int) -> None:
        session = self._repository.session
        self._bind_shared_session(session)
        transaction_context = session.begin_nested() if session.in_transaction() else session.begin()

        with transaction_context:
            invoice = self._repository.get_invoice(invoice_id)
            self._rollback_invoice_effects(invoice)
            session.delete(invoice)
            session.flush()

    def _apply_invoice_state(
        self,
        invoice: Invoice,
        normalized_items: list[SalesLineInput],
        actual_paid_amount: Decimal,
        *,
        note_override: str | None,
    ) -> None:
        total_amount = Decimal("0")
        for line in normalized_items:
            product = self._inventory_service.get_product(line.product_id)
            if not product.is_active:
                raise ValidationError(f"Hàng hóa {product.product_code_base} ngừng hoạt động.")
            product.validate_price_unit_type(line.unit_type)

            price_row = next(
                (price for price in product.prices if price.unit_type == line.unit_type and price.is_enabled),
                None,
            )
            if price_row is None:
                raise ValidationError(
                    f"Không tìm thấy giá đang bật cho hàng {product.product_code_base} với đơn vị {line.unit_type.value}."
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
        invoice.paid_amount = actual_paid_amount
        if note_override is not None:
            invoice.note = note_override

        if invoice.customer_id is not None:
            self._customer_service.adjust_balance(
                invoice.customer_id,
                total_amount,
                "INVOICE",
                invoice.id,
                note=f"Invoice charge {invoice.invoice_code}",
                event_type="INVOICE_CHARGE",
            )
            if actual_paid_amount != Decimal("0"):
                self._customer_service.adjust_balance(
                    invoice.customer_id,
                    -actual_paid_amount,
                    "INVOICE",
                    invoice.id,
                    note=f"Invoice payment {invoice.invoice_code}",
                    event_type="INVOICE_PAYMENT",
                )
            self._customer_service.increase_sales(invoice.customer_id, total_amount)

    def _rollback_invoice_effects(self, invoice: Invoice) -> None:
        for item in list(invoice.items):
            self._inventory_service.increase_stock(item.product_id, item.quantity, item.unit_type)

        if invoice.customer_id is not None:
            self._customer_service.remove_reference_balance_effect(invoice.customer_id, "INVOICE", invoice.id)
            self._customer_service.decrease_sales(invoice.customer_id, invoice.total_amount)

    def _bind_shared_session(self, session: object) -> None:
        self._repository.use_session(session)
        self._inventory_service.use_session(session)
        self._customer_service.use_session(session)

    def _normalize_items(self, items: list[Mapping[str, object]]) -> list[SalesLineInput]:
        if not items:
            raise ValidationError("Danh sách hàng hóa không được để trống.")

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
            raise ValidationError("Đơn vị bán là bắt buộc.")
        try:
            return UnitType(str(value))
        except ValueError as exc:
            raise ValidationError(f"Đơn vị bán không được hỗ trợ: {value}") from exc

    def _normalize_payment_method(self, value: PaymentMethod | str | None) -> PaymentMethod | None:
        if value is None:
            return None
        if isinstance(value, PaymentMethod):
            return value
        try:
            return PaymentMethod(str(value))
        except ValueError as exc:
            raise ValidationError(f"Phương thức thanh toán không được hỗ trợ: {value}") from exc

    def _normalize_paid_amount(self, value: Decimal | int | str | None) -> Decimal:
        if value is None:
            return Decimal("0")
        amount = self._to_decimal(value)
        if amount < Decimal("0"):
            raise ValidationError("Số tiền khách trả phải >= 0.")
        return amount

    def _resolve_customer_snapshot_name(self, customer: object, raw_name: str) -> str:
        normalized = raw_name.strip()
        if customer is None:
            return normalized or "Khách lẻ"
        return normalized or customer.customer_name

    def _require_int(self, item: Mapping[str, object], key: str) -> int:
        raw_value = item.get(key)
        if raw_value is None:
            raise ValidationError(f"{key} là bắt buộc.")
        return int(raw_value)

    def _require_positive_decimal(self, value: object, field_name: str) -> Decimal:
        if value is None:
            raise ValidationError(f"{field_name} là bắt buộc.")
        amount = self._to_decimal(value)
        if amount <= Decimal("0"):
            raise ValidationError(f"{field_name} phải > 0.")
        return amount

    @staticmethod
    def _to_decimal(value: Decimal | int | str | object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

