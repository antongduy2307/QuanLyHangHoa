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
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


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
            self._validate_walk_in_mode(customer_id, normalized_mode)

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

            total_amount = self._populate_linked_return_items(
                return_invoice=return_invoice,
                source_invoice_id=source_invoice.id,
                normalized_items=normalized_items,
            )
            return_invoice.total_amount = total_amount
            self._apply_customer_effects(
                customer_id=customer_id,
                total_amount=total_amount,
                handling_mode=normalized_mode,
                return_code=return_invoice.return_code,
                return_id=return_invoice.id,
                transaction_datetime=return_invoice.return_datetime,
            )

            session.flush()
            return return_invoice

    def update_return_invoice(
        self,
        return_invoice_id: int,
        *,
        items: list[Mapping[str, object]],
        handling_mode: ReturnHandlingMode | str,
        return_datetime: datetime | None = None,
        note: str | None = None,
    ) -> ReturnInvoice:
        session = self._repository.session
        self.use_session(session)
        normalized_mode = self._normalize_handling_mode(handling_mode)
        normalized_return_datetime = self._require_datetime(return_datetime, "return_datetime") if return_datetime is not None else None
        transaction_context = session.begin_nested() if session.in_transaction() else session.begin()

        with transaction_context:
            return_invoice = self._repository.get_return_invoice(return_invoice_id)
            customer_id = return_invoice.customer_id
            self._validate_walk_in_mode(customer_id, normalized_mode)
            if normalized_return_datetime is not None:
                return_invoice.return_datetime = normalized_return_datetime

            self._rollback_return_effects(return_invoice)
            return_invoice.items.clear()
            session.flush()

            if return_invoice.source_invoice_id is None:
                normalized_quick_items = self._normalize_quick_items(items)
                total_amount = self._populate_quick_return_items(return_invoice=return_invoice, normalized_items=normalized_quick_items)
            else:
                source_invoice = self._sales_repository.get_invoice(return_invoice.source_invoice_id)
                normalized_items = self._normalize_items(items)
                total_amount = self._populate_linked_return_items(
                    return_invoice=return_invoice,
                    source_invoice_id=source_invoice.id,
                    normalized_items=normalized_items,
                )
            return_invoice.handling_mode = normalized_mode
            return_invoice.note = note
            return_invoice.total_amount = total_amount
            self._apply_customer_effects(
                customer_id=customer_id,
                total_amount=total_amount,
                handling_mode=normalized_mode,
                return_code=return_invoice.return_code,
                return_id=return_invoice.id,
                transaction_datetime=return_invoice.return_datetime,
            )

            session.flush()
            return return_invoice

    def update_return_datetime(self, return_invoice_id: int, new_datetime: datetime) -> ReturnInvoice:
        session = self._repository.session
        self.use_session(session)
        transaction_context = session.begin_nested() if session.in_transaction() else session.begin()

        with transaction_context:
            normalized_datetime = self._require_datetime(new_datetime, "new_datetime")
            return_invoice = self._repository.get_return_invoice(return_invoice_id)
            return_invoice.return_datetime = normalized_datetime
            if return_invoice.customer_id is not None:
                self._customer_service.sync_reference_transaction_datetime(
                    return_invoice.customer_id,
                    "RETURN",
                    return_invoice.id,
                    normalized_datetime,
                )
            session.flush()
            return return_invoice

    def delete_return_invoice(self, return_invoice_id: int) -> None:
        session = self._repository.session
        self.use_session(session)
        transaction_context = session.begin_nested() if session.in_transaction() else session.begin()

        with transaction_context:
            return_invoice = self._repository.get_return_invoice(return_invoice_id)
            self._rollback_return_effects(return_invoice)
            session.delete(return_invoice)
            session.flush()

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
            self._validate_walk_in_mode(customer_id, normalized_mode)
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
            total_amount = self._populate_quick_return_items(return_invoice=return_invoice, normalized_items=normalized_items)

            return_invoice.total_amount = total_amount
            self._apply_customer_effects(
                customer_id=customer_id,
                total_amount=total_amount,
                handling_mode=normalized_mode,
                return_code=return_invoice.return_code,
                return_id=return_invoice.id,
                transaction_datetime=return_invoice.return_datetime,
            )

            session.flush()
            return return_invoice

    def _populate_linked_return_items(
        self,
        *,
        return_invoice: ReturnInvoice,
        source_invoice_id: int,
        normalized_items: list[ReturnLineInput],
    ) -> Decimal:
        requested_by_source_item: dict[int, Decimal] = {}
        for line in normalized_items:
            requested_by_source_item[line.source_invoice_item_id] = requested_by_source_item.get(line.source_invoice_item_id, Decimal("0")) + line.quantity

        validated_source_items: dict[int, object] = {}
        for source_item_id, requested_total in requested_by_source_item.items():
            source_item = self._sales_repository.get_invoice_item(source_item_id)
            if source_item.invoice_id != source_invoice_id:
                raise ValidationError("Dòng hàng trả không thuộc hóa đơn nguồn đã chọn.")

            previously_returned = self._repository.get_total_returned_quantity(source_item.id)
            if previously_returned + requested_total > source_item.quantity:
                raise ValidationError("Số lượng trả vượt quá số lượng đã mua.")
            validated_source_items[source_item_id] = source_item

        total_amount = Decimal("0")
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
        return total_amount

    def _populate_quick_return_items(
        self,
        *,
        return_invoice: ReturnInvoice,
        normalized_items: list[QuickReturnLineInput],
    ) -> Decimal:
        total_amount = Decimal("0")
        for line in normalized_items:
            product = self._inventory_service.get_product(line.product_id)
            product.validate_price_unit_type(line.unit_type)
            price_row = next((price for price in product.prices if price.unit_type == line.unit_type and price.is_enabled), None)
            if price_row is None:
                raise ValidationError(f"Không tìm thấy giá đang bật cho hàng {product.product_code_base} với đơn vị {line.unit_type.value}.")
            unit_price = line.unit_price if line.unit_price is not None else price_row.price
            line_total = line.line_total if line.line_total is not None else line.quantity * unit_price
            total_amount += line_total
            self._inventory_service.increase_stock(product.id, line.quantity, line.unit_type)
            return_invoice.items.append(
                ReturnInvoiceItem(
                    source_invoice_item_id=None,
                    product_id=product.id,
                    unit_type=line.unit_type,
                    quantity=line.quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                    product_code_snapshot=product.product_code_base,
                    product_name_snapshot=product.product_name,
                )
            )
        return total_amount

    def _rollback_return_effects(self, return_invoice: ReturnInvoice) -> None:
        for item in list(return_invoice.items):
            self._inventory_service.decrease_stock(item.product_id, item.quantity, item.unit_type)
        if return_invoice.customer_id is not None:
            self._customer_service.increase_sales(return_invoice.customer_id, return_invoice.total_amount)
            ledgers = list(self._customer_service.list_reference_ledgers(return_invoice.customer_id, "RETURN", return_invoice.id))
            if ledgers:
                self._customer_service.remove_reference_balance_effect(return_invoice.customer_id, "RETURN", return_invoice.id)

    def _apply_customer_effects(
        self,
        *,
        customer_id: int | None,
        total_amount: Decimal,
        handling_mode: ReturnHandlingMode,
        return_code: str,
        return_id: int,
        transaction_datetime: datetime,
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
                transaction_datetime=transaction_datetime,
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
                transaction_datetime=transaction_datetime,
            )

    def _validate_walk_in_mode(self, customer_id: int | None, handling_mode: ReturnHandlingMode) -> None:
        if customer_id is None and handling_mode != ReturnHandlingMode.REFUND_NOW:
            raise ValidationError("Hóa đơn khách lẻ chỉ hỗ trợ hoàn tiền ngay.")

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
            unit_price = self._require_optional_non_negative_decimal(item.get("unit_price"), "unit_price")
            line_total = self._require_optional_non_negative_decimal(item.get("line_total"), "line_total")
            normalized.append(
                QuickReturnLineInput(
                    product_id=product_id,
                    unit_type=unit_type,
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )
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

    def _require_optional_non_negative_decimal(self, value: object, field_name: str) -> Decimal | None:
        if value is None:
            return None
        amount = self._to_decimal(value)
        if amount < Decimal("0"):
            raise ValidationError(f"{field_name} phải >= 0.")
        return amount

    def _require_datetime(self, value: object, field_name: str) -> datetime:
        if not isinstance(value, datetime):
            raise ValidationError(f"{field_name} phải là datetime hợp lệ.")
        return value

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))


ReturnsService = ReturnService
