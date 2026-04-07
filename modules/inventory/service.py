from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.enums import BAO_TO_KG_RATIO, UnitMode, UnitType
from core.exceptions import ValidationError
from modules.inventory.dto import InventoryProductDTO
from modules.inventory.mappers import to_dto
from modules.inventory.models import (
    InventoryAdjustment,
    InventoryAdjustmentItem,
    InventoryBalance,
    InventoryReceipt,
    InventoryReceiptItem,
    Product,
)
from modules.inventory.repository import InventoryRepository


@dataclass(frozen=True, slots=True)
class ReceiptLineInput:
    product_id: int
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class AdjustmentLineInput:
    product_id: int
    new_quantity: Decimal


class InventoryService:
    def __init__(self, repository: InventoryRepository) -> None:
        self._repository = repository

    def use_session(self, session: Session) -> None:
        self._repository.use_session(session)

    def get_product(self, product_id: int) -> Product:
        return self._repository.get_product(product_id)

    def list_products(self) -> Sequence[InventoryProductDTO]:
        return [to_dto(product) for product in self._repository.list_products()]

    def kg_to_bao(self, kg: Decimal | int | str) -> Decimal:
        return self._to_decimal(kg) / BAO_TO_KG_RATIO

    def bao_to_kg(self, bao: Decimal | int | str) -> Decimal:
        return self._to_decimal(bao) * BAO_TO_KG_RATIO

    def get_balance(self, product_id: int) -> InventoryBalance:
        product = self._repository.get_product(product_id)
        return self._repository.get_or_create_balance(product)

    def get_available_quantity(self, product_id: int, unit_type: UnitType) -> Decimal:
        product = self._repository.get_product(product_id)
        self._validate_unit_type(product, unit_type)
        balance = self._repository.get_or_create_balance(product)

        if product.unit_mode == UnitMode.BAO_KG:
            bao_quantity = balance.on_hand_bao_decimal or Decimal("0")
            if unit_type == UnitType.BAO:
                return bao_quantity
            return self.bao_to_kg(bao_quantity)

        return Decimal(balance.on_hand_bich_integer or 0)

    def increase_stock(self, product_id: int, quantity: Decimal | int | str, unit_type: UnitType) -> InventoryBalance:
        return self._apply_stock_change(product_id, quantity, unit_type, increase=True)

    def decrease_stock(self, product_id: int, quantity: Decimal | int | str, unit_type: UnitType) -> InventoryBalance:
        return self._apply_stock_change(product_id, quantity, unit_type, increase=False)

    def create_receipt(self, items: list[Mapping[str, object]]) -> InventoryReceipt:
        session = self._repository.session
        normalized_items = [self._normalize_receipt_line(item) for item in items]

        with session.begin():
            receipt = InventoryReceipt(receipt_code=self._generate_receipt_code())
            session.add(receipt)
            session.flush()

            for line in normalized_items:
                if line.quantity == Decimal("0"):
                    raise ValidationError("Receipt item quantity must be greater than 0 to be persisted.")

                product = self._repository.get_product(line.product_id)
                unit_type = self._canonical_unit_type(product)
                self.increase_stock(product.id, line.quantity, unit_type)
                receipt.items.append(
                    InventoryReceiptItem(
                        product_id=product.id,
                        quantity=line.quantity,
                    )
                )

            session.flush()
            return receipt

    def create_adjustment(self, items: list[Mapping[str, object]]) -> InventoryAdjustment:
        session = self._repository.session
        normalized_items = [self._normalize_adjustment_line(item) for item in items]

        with session.begin():
            adjustment = InventoryAdjustment()
            session.add(adjustment)
            session.flush()

            for line in normalized_items:
                product = self._repository.get_product(line.product_id)
                balance = self._repository.get_or_create_balance(product)
                old_quantity = self._get_canonical_balance_quantity(product, balance)
                self._validate_canonical_quantity(product, line.new_quantity)
                self._set_canonical_balance(product, balance, line.new_quantity)

                adjustment.items.append(
                    InventoryAdjustmentItem(
                        product_id=product.id,
                        old_quantity=old_quantity,
                        new_quantity=line.new_quantity,
                        delta_quantity=line.new_quantity - old_quantity,
                    )
                )

            session.flush()
            return adjustment

    def _apply_stock_change(
        self,
        product_id: int,
        quantity: Decimal | int | str,
        unit_type: UnitType,
        *,
        increase: bool,
    ) -> InventoryBalance:
        product = self._repository.get_product(product_id)
        self._validate_unit_type(product, unit_type)
        normalized_quantity = self._to_decimal(quantity)
        balance = self._repository.get_or_create_balance(product)

        sign = Decimal("1") if increase else Decimal("-1")
        if product.unit_mode == UnitMode.BAO_KG:
            bao_delta = normalized_quantity if unit_type == UnitType.BAO else self.kg_to_bao(normalized_quantity)
            balance.on_hand_bao_decimal = (balance.on_hand_bao_decimal or Decimal("0")) + (bao_delta * sign)
            return balance

        if normalized_quantity != normalized_quantity.to_integral_value():
            raise ValidationError("BICH stock only accepts whole-number quantities.")

        balance.on_hand_bich_integer = (balance.on_hand_bich_integer or 0) + int(normalized_quantity * sign)
        return balance

    def _generate_receipt_code(self) -> str:
        prefix = f"NK{datetime.now().strftime('%Y%m%d')}-"
        statement = (
            select(InventoryReceipt.receipt_code)
            .where(InventoryReceipt.receipt_code.like(f"{prefix}%"))
            .order_by(InventoryReceipt.receipt_code.desc())
            .limit(1)
        )
        last_code = self._repository.session.scalar(statement)
        next_number = int(last_code.rsplit("-", 1)[1]) + 1 if last_code else 1
        return f"{prefix}{next_number:03d}"

    def _normalize_receipt_line(self, item: Mapping[str, object]) -> ReceiptLineInput:
        product_id = self._require_int(item, "product_id")
        quantity = self._require_non_negative_decimal(item, "quantity")
        return ReceiptLineInput(product_id=product_id, quantity=quantity)

    def _normalize_adjustment_line(self, item: Mapping[str, object]) -> AdjustmentLineInput:
        product_id = self._require_int(item, "product_id")
        new_quantity = self._require_non_negative_decimal(item, "new_quantity")
        return AdjustmentLineInput(product_id=product_id, new_quantity=new_quantity)

    def _validate_unit_type(self, product: Product, unit_type: UnitType) -> None:
        product.validate_price_unit_type(unit_type)

    def _canonical_unit_type(self, product: Product) -> UnitType:
        return UnitType.BAO if product.unit_mode == UnitMode.BAO_KG else UnitType.BICH

    def _get_canonical_balance_quantity(self, product: Product, balance: InventoryBalance) -> Decimal:
        if product.unit_mode == UnitMode.BAO_KG:
            return balance.on_hand_bao_decimal or Decimal("0")
        return Decimal(balance.on_hand_bich_integer or 0)

    def _set_canonical_balance(self, product: Product, balance: InventoryBalance, quantity: Decimal) -> None:
        if product.unit_mode == UnitMode.BAO_KG:
            balance.on_hand_bao_decimal = quantity
            return

        if quantity != quantity.to_integral_value():
            raise ValidationError("BICH stock only accepts whole-number quantities.")
        balance.on_hand_bich_integer = int(quantity)

    def _validate_canonical_quantity(self, product: Product, quantity: Decimal) -> None:
        if product.unit_mode == UnitMode.BICH and quantity != quantity.to_integral_value():
            raise ValidationError("BICH stock only accepts whole-number quantities.")

    def _require_int(self, item: Mapping[str, object], key: str) -> int:
        raw_value = item.get(key)
        if raw_value is None:
            raise ValidationError(f"{key} is required.")
        return int(raw_value)

    def _require_non_negative_decimal(self, item: Mapping[str, object], key: str) -> Decimal:
        raw_value = item.get(key)
        if raw_value is None:
            raise ValidationError(f"{key} is required.")
        value = self._to_decimal(raw_value)
        if value < 0:
            raise ValidationError(f"{key} must be >= 0.")
        return value

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
