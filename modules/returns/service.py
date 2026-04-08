from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from core.enums import ReturnHandlingMode, UnitType
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


@dataclass(frozen=True, slots=True)
class QuickReturnLineInput:
    product_id: int
    unit_type: UnitType
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
            customer_snapshot_name = source_invoice.customer_snapshot_name
            customer_id = source_invoice.customer_id
            if customer_id is None and normalized_mode != ReturnHandlingMode.REFUND_NOW:
                raise ValidationError("Hóa đơn khách lẻ chỉ hỗ trợ hoàn tiền ngay.")

            requested_by_source_item: dict[int, Decimal] = {}
            for line in normalized_items:
                requested_by_source_item[line.source_invoice_item_id] = requested_by_source_item.get(line.source_invoice_item_id, Decimal("0")) + line.quantity

            return_invoice = ReturnInvoice(
                return_code=self._repository.generate_return_code(return_datetime),
                source_invoice_id=source_invoice.id,
                customer_id=customer_id,
                customer_snapshot_name=customer_snapshot_name,
                is_quick_return=False,
                return_datetime=return_datetime,
                total_amount=Decimal("0"),
                handling_mode=normalized_mode,
                note=note,
            )
            session.add(return_invoice)
            session.flush()

            total_amount = Decimal("0")
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
            self._apply_customer_effects(
                customer_id=customer_id,
                total_amount=total_amount,
                handling_mode=normalized_mode,
                return_code=return_invoice.return_code,
                return_id=return_invoice.id,
            )

            session.flush()
            return return_invoice

    def create_quick_return_invoice(
        self,
        *,
        customer_id: int | None,
        customer_snapshot_name: str,
        return_datetime: datetime,
        items: list[Mapping[str, object]],
        handling_mode: ReturnHandlingMode | str,
        note: str | None = None,
    ) -> ReturnInvoice:
        session = self._repository.session
        self.use_session(session)
        normalized_items = self._normalize_quick_items(items)
        normalized_mode = self._normalize_handling_mode(handling_mode)
        snapshot_name = (customer_snapshot_name or "").strip() or "Khách lẻ"
        transaction_context = session.begin_nested() if session.in_transaction() else session.begin()

        with transaction_context:
            if customer_id is None and normalized_mode != ReturnHandlingMode.REFUND_NOW:
                raise ValidationError("Khách lẻ chỉ hỗ trợ hoàn tiền ngay.")
            if customer_id is not None:
                customer = self._customer_service.get_customer(customer_id)
                snapshot_name = customer.customer_name

            return_invoice = ReturnInvoice(
                return_code=self._repository.generate_return_code(return_datetime),
                source_invoice_id=None,
                customer_id=customer_id,
                customer_snapshot_name=snapshot_name,
                is_quick_return=True,
                return_datetime=return_datetime,
                total_amount=Decimal("0"),
                handling_mode=normalized_mode,
                note=note,
            )
            session.add(return_invoice)
            session.flush()

            total_amount = Decimal("0")
            for line in normalized_items:
                product = self._inventory_service.get_product(line.product_id)
                product.validate_price_unit_type(line.unit_type)
                price_row = next((price for price in product.prices if price.unit_type == line.unit_type and price.is_enabled), None)
                if price_row is None:
                    raise ValidationError(f"Không tìm thấy giá đang bật cho hàng {product.product_code_base} với đơn vị {line.unit_type.value}.")
                line_total = line.quantity * price_row.price
                total_amount += line_total
                self._inventory_service.increase_stock(product.id, line.quantity, line.unit_type)
                return_invoice.items.append(
                    ReturnInvoiceItem(
                        source_invoice_item_id=None,
                        product_id=product.id,
                        unit_type=line.unit_type,
                        quantity=line.quantity,
                        unit_price=price_row.price,
                        line_total=line_total,
                        product_code_snapshot=product.product_code_base,
                        product_name_snapshot=product.product_name,
                    )
                )

            return_invoice.total_amount = total_amount
            self._apply_customer_effects(
                customer_id=customer_id,
                total_amount=total_amount,
                handling_mode=normalized_mode,
                return_code=return_invoice.return_code,
                return_id=return_invoice.id,
            )

            session.flush()
            return return_invoice

    def _apply_customer_effects(
        self,
        *,
        customer_id: int | None,
        total_amount: Decimal,
        handling_mode: ReturnHandlingMode,
        return_code: str,
        return_id: int,
    ) -> None:
        if customer_id is None:
            return
        positive_customer_balance = max(self._customer_service.get_customer(customer_id).current_balance, Decimal("0"))
        self._customer_service.decrease_sales(customer_id, total_amount)
        if handling_mode == ReturnHandlingMode.STORE_CREDIT:
            self._customer_service.adjust_balance(
                customer_id,
                -total_amount,
                "RETURN",
                return_id,
                note=f"Return store credit {return_code}",
                event_type="RETURN_STORE_CREDIT",
            )
            return
        applied_delta = min(positive_customer_balance, total_amount)
        if applied_delta > Decimal("0"):
            self._customer_service.adjust_balance(
                customer_id,
                -applied_delta,
                "RETURN",
                return_id,
                note=f"Return refund now {return_code}",
                event_type="RETURN_REFUND_NOW",
            )

    def _normalize_items(self, items: list[Mapping[str, object]]) -> list[ReturnLineInput]:
        if not items:
            raise ValidationError("Danh sách trả hàng không được để trống.")

        normalized: list[ReturnLineInput] = []
        for item in items:
            source_invoice_item_id = self._require_int(item, "source_invoice_item_id")
            quantity = self._require_positive_decimal(item.get("quantity"), "quantity")
            normalized.append(ReturnLineInput(source_invoice_item_id=source_invoice_item_id, quantity=quantity))
        return normalized

    def _normalize_quick_items(self, items: list[Mapping[str, object]]) -> list[QuickReturnLineInput]:
        if not items:
            raise ValidationError("Danh sách trả hàng không được để trống.")

        normalized: list[QuickReturnLineInput] = []
        for item in items:
            product_id = self._require_int(item, "product_id")
            unit_type = self._require_unit_type(item.get("unit_type"))
            quantity = self._require_positive_decimal(item.get("quantity"), "quantity")
            normalized.append(QuickReturnLineInput(product_id=product_id, unit_type=unit_type, quantity=quantity))
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

    def _require_unit_type(self, value: object) -> UnitType:
        if isinstance(value, UnitType):
            return value
        if value is None:
            raise ValidationError("unit_type là bắt buộc.")
        try:
            return UnitType(str(value))
        except ValueError as exc:
            raise ValidationError(f"Đơn vị trả hàng không hợp lệ: {value}") from exc

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


ReturnsService = ReturnService
