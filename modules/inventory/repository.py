from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from core.enums import UnitMode
from core.exceptions import NotFoundError
from modules.inventory.models import InventoryBalance, Product


class InventoryRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = self._session_factory()
        return self._session

    def use_session(self, session: Session) -> None:
        self._session = session

    def list_products(self, *, include_inactive: bool = False) -> Sequence[Product]:
        statement = (
            select(Product)
            .options(selectinload(Product.prices), selectinload(Product.inventory_balance))
            .order_by(Product.product_name.asc())
        )
        if not include_inactive:
            statement = statement.where(Product.is_active.is_(True))
        return self.session.scalars(statement).all()

    def get_product(self, product_id: int) -> Product:
        statement = (
            select(Product)
            .options(
                selectinload(Product.prices),
                selectinload(Product.inventory_balance),
                selectinload(Product.invoice_items),
                selectinload(Product.return_items),
                selectinload(Product.receipt_items),
                selectinload(Product.adjustment_items),
            )
            .where(Product.id == product_id)
        )
        product = self.session.scalars(statement).one_or_none()
        if product is None:
            raise NotFoundError(f"Product {product_id} was not found.")
        return product

    def get_or_create_balance(self, product: Product) -> InventoryBalance:
        if product.inventory_balance is not None:
            return product.inventory_balance

        balance = InventoryBalance(
            product_id=product.id,
            on_hand_bao_decimal=Decimal("0") if product.unit_mode == UnitMode.BAO_KG else None,
            on_hand_bich_integer=Decimal("0") if product.unit_mode == UnitMode.BICH else None,
        )
        product.inventory_balance = balance
        self.session.add(balance)
        return balance
