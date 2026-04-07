from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from core.enums import ReturnHandlingMode
from core.exceptions import ValidationError
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.returns.dto import ReturnInvoiceDTO
from modules.returns.mappers import to_dto
from modules.returns.models import ReturnInvoice, ReturnInvoiceItem
from modules.returns.repository import ReturnsRepository
from modules.sales.repository import SalesRepository


@dataclass(frozen=True, slots=True)
class ReturnLineInput:
    source_invoice_item_id: int
    quantity: Decimal


class ReturnService:
    def __init__(
        self,
        repository: ReturnsRepository,
        sales_repository: SalesRepository | None = None,
        inventory_service: InventoryService | None = None,
        customer_service: CustomerService | None = None,
    ) -> None:
        self._repository = repository
        sales_repository = sales_repository or SalesRepository(repository._session_factory)
        self._sales_repository = sales_repository
        self._inventory_service = inventory_service or InventoryService(InventoryRepository(repository._session_factory))
        self._customer_service = customer_service or CustomerService(CustomerRepository(repository._session_factory))

    def use_session(self, session: Session) -> None:
        self._repository.use_session(session)
        self._sales_repository.use_session(session)
        self._inventory_service.use_session(session)
        self._customer_service.use_session(session)

    def list_return_invoices(self) -> Sequence[ReturnInvoiceDTO]:
        return [to_dto(item) for item in self._repository.list_return_invoices()]

    def create_return_invoice(
        self,
        *,
        source_invoice_id: int,
        return_datetime: datetime,
        items: list[Mapping[str, object]],
        handling_mode: ReturnHandlingMode | str,
        note: str | None = None,
    ) -> ReturnInvoice:
        session = self._repository.session
        self.use_session(session)
        normalized_items = self._normalize_items(items)
        normalized_mode = self._normalize_handling_mode(handling_mode)
        transaction_context = session.begin_nested() if session.in_transaction() else session.begin()

        with transaction_context:
            source_invoice = self._sales_repository.get_invoice(source_invoice_id)
            if source_invoice.customer_id is None and normalized_mode != ReturnHandlingMode.REFUND_NOW:
                raise ValidationError("Hóa đơn khách lẻ chỉ hỗ trợ hoàn tiền ngay.")

            requested_by_source_item: dict[int, Decimal] = {}
            for line in normalized_items:
                requested_by_source_item[line.source_invoice_item_id] = requested_by_source_item.get(line.source_invoice_item_id, Decimal("0")) + line.quantity

            return_invoice = ReturnInvoice(
                return_code=self._repository.generate_return_code(return_datetime),
                source_invoice_id=source_invoice.id,
                return_datetime=return_datetime,
                total_amount=Decimal("0"),
                handling_mode=normalized_mode,
                note=note,
            )
            session.add(return_invoice)
            session.flush()

            total_amount = Decimal("0")
            positive_customer_balance = None
            if source_invoice.customer_id is not None:
                positive_customer_balance = max(self._customer_service.get_customer(source_invoice.customer_id).current_balance, Decimal("0"))

            validated_source_items: dict[int, object] = {}
            for source_item_id, requested_total in requested_by_source_item.items():
                source_item = self._sales_repository.get_invoice_item(source_item_id)
                if source_item.invoice_id != source_invoice.id:
                    raise ValidationError("Dòng hàng trả không thuộc hóa đơn nguồn đã chọn.")

                previously_returned = self._repository.get_total_returned_quantity(source_item.id)
                if previously_returned + requested_total > source_item.quantity:
                    raise ValidationError("Số lượng trả vượt quá số lượng đã mua.")
                validated_source_items[source_item_id] = source_item

            for line in normalized_items:
                source_item = validated_source_items[line.source_invoice_item_id]
                line_total = line.quantity * source_item.unit_price
                total_amount += line_total
                self._inventory_service.increase_stock(source_item.product_id, line.quantity, source_item.unit_type)
                return_invoice.items.append(
                    ReturnInvoiceItem(
                        source_invoice_item_id=source_item.id,
                        product_id=source_item.product_id,
                        unit_type=source_item.unit_type,
                        quantity=line.quantity,
                        unit_price=source_item.unit_price,
                        line_total=line_total,
                        product_code_snapshot=source_item.product_code_snapshot,
                        product_name_snapshot=source_item.product_name_snapshot,
                    )
                )

            return_invoice.total_amount = total_amount

            if source_invoice.customer_id is not None:
                self._customer_service.decrease_sales(source_invoice.customer_id, total_amount)
                if normalized_mode == ReturnHandlingMode.STORE_CREDIT:
                    self._customer_service.adjust_balance(
                        source_invoice.customer_id,
                        -total_amount,
                        "RETURN",
                        return_invoice.id,
                        note=f"Return store credit {return_invoice.return_code}",
                        event_type="RETURN_STORE_CREDIT",
                    )
                else:
                    assert positive_customer_balance is not None
                    applied_delta = min(positive_customer_balance, total_amount)
                    if applied_delta > Decimal("0"):
                        self._customer_service.adjust_balance(
                            source_invoice.customer_id,
                            -applied_delta,
                            "RETURN",
                            return_invoice.id,
                            note=f"Return refund now {return_invoice.return_code}",
                            event_type="RETURN_REFUND_NOW",
                        )

            session.flush()
            return return_invoice

    def _normalize_items(self, items: list[Mapping[str, object]]) -> list[ReturnLineInput]:
        if not items:
            raise ValidationError("Danh sách trả hàng không được để trống.")

        normalized: list[ReturnLineInput] = []
        for item in items:
            source_invoice_item_id = self._require_int(item, "source_invoice_item_id")
            quantity = self._require_positive_decimal(item.get("quantity"), "quantity")
            normalized.append(ReturnLineInput(source_invoice_item_id=source_invoice_item_id, quantity=quantity))
        return normalized

    def _normalize_handling_mode(self, value: ReturnHandlingMode | str) -> ReturnHandlingMode:
        if isinstance(value, ReturnHandlingMode):
            return value
        try:
            return ReturnHandlingMode(str(value))
        except ValueError as exc:
            raise ValidationError(f"Cách xử lý trả hàng không được hỗ trợ: {value}") from exc

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
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

# Backward-compatible alias for existing shell/UI wiring.
ReturnsService = ReturnService
