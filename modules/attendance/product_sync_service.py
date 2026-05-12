from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from core.db import SessionFactory, _import_models
from modules.attendance.db import AttendanceSessionLocal
from modules.attendance.models import BagType, CutLog, ExtraCutWorkLog
from modules.inventory.models import Product

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProductCutWorkItem:
    id: int
    name: str
    source_product_id: int | None
    quota_quantity: Decimal
    excess_unit_price: Decimal
    is_excluded_from_attendance: bool


@dataclass(frozen=True)
class ProductCutSyncProduct:
    id: int
    name: str
    is_active: bool


@dataclass
class AttendanceProductSyncResult:
    created_count: int = 0
    updated_count: int = 0
    deactivated_count: int = 0
    legacy_count: int = 0
    incomplete_items: list[ProductCutWorkItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class AttendanceProductSyncService:
    """One-way sync from inventory products into attendance CUT work items."""

    def __init__(
        self,
        *,
        product_session_factory: sessionmaker[Session] = SessionFactory,
        attendance_session_factory: sessionmaker[Session] = AttendanceSessionLocal,
    ) -> None:
        self._product_session_factory = product_session_factory
        self._attendance_session_factory = attendance_session_factory

    def sync_products_to_cut_work(self) -> AttendanceProductSyncResult:
        products = self._read_products()
        result = AttendanceProductSyncResult()
        duplicate_active_names = self._duplicate_active_product_names(products)
        for name in sorted(duplicate_active_names):
            warning = f"Duplicate active product name cannot be synced safely: {name}"
            result.warnings.append(warning)
            logger.warning(warning)

        with self._attendance_session_factory() as session:
            with session.begin():
                linked_by_product_id = self._linked_bag_types_by_product_id(session, result)
                product_ids = {product.id for product in products}
                active_products = [product for product in products if product.is_active]

                for product in active_products:
                    if product.name in duplicate_active_names:
                        continue
                    bag_type = linked_by_product_id.get(product.id)
                    if bag_type is None:
                        self._create_linked_bag_type(session, product, result)
                    else:
                        self._update_linked_bag_type(session, bag_type, product, result)

                for bag_type in linked_by_product_id.values():
                    if bag_type.source_product_id not in product_ids:
                        self._deactivate_linked_bag_type(session, bag_type, result, missing_product=True)

                inactive_product_ids = {product.id for product in products if not product.is_active}
                for product_id in inactive_product_ids:
                    bag_type = linked_by_product_id.get(product_id)
                    if bag_type is not None:
                        self._deactivate_linked_bag_type(session, bag_type, result, missing_product=False)

                self._deactivate_manual_bag_types(session, result)

            result.incomplete_items = self.list_incomplete_cut_work_items(session=session)
        return result

    def list_incomplete_cut_work_items(self, *, session: Session | None = None) -> list[ProductCutWorkItem]:
        if session is not None:
            return self._list_incomplete_cut_work_items(session)
        with self._attendance_session_factory() as managed_session:
            return self._list_incomplete_cut_work_items(managed_session)

    def _read_products(self) -> list[ProductCutSyncProduct]:
        _import_models()
        with self._product_session_factory() as session:
            rows = session.execute(
                select(Product.id, Product.product_name, Product.is_active).order_by(Product.id.asc())
            ).all()
        return [
            ProductCutSyncProduct(id=int(product_id), name=str(product_name).strip(), is_active=bool(is_active))
            for product_id, product_name, is_active in rows
        ]

    def _duplicate_active_product_names(self, products: list[ProductCutSyncProduct]) -> set[str]:
        counts = Counter(product.name for product in products if product.is_active)
        return {name for name, count in counts.items() if count > 1}

    def _linked_bag_types_by_product_id(
        self,
        session: Session,
        result: AttendanceProductSyncResult,
    ) -> dict[int, BagType]:
        duplicate_rows = session.execute(
            select(BagType.source_product_id, func.count(BagType.id))
            .where(BagType.source_product_id.is_not(None))
            .group_by(BagType.source_product_id)
            .having(func.count(BagType.id) > 1)
        ).all()
        duplicate_ids = {int(source_product_id) for source_product_id, _count in duplicate_rows}
        for source_product_id in sorted(duplicate_ids):
            warning = f"Duplicate attendance source_product_id detected: {source_product_id}"
            result.warnings.append(warning)
            logger.warning(warning)

        linked_rows = session.scalars(
            select(BagType)
            .where(BagType.is_product_linked.is_(True))
            .where(BagType.source_product_id.is_not(None))
            .order_by(BagType.id.asc())
        ).all()
        linked_by_product_id: dict[int, BagType] = {}
        for bag_type in linked_rows:
            source_product_id = int(bag_type.source_product_id)
            if source_product_id in duplicate_ids:
                continue
            linked_by_product_id[source_product_id] = bag_type
        return linked_by_product_id

    def _create_linked_bag_type(
        self,
        session: Session,
        product: ProductCutSyncProduct,
        result: AttendanceProductSyncResult,
    ) -> None:
        if self._name_conflict_exists(session, product.name):
            warning = f"Product name conflicts with existing attendance CUT work item: {product.name}"
            result.warnings.append(warning)
            logger.warning(warning)
            return
        bag_type = BagType(
            name=product.name,
            unit_price=0,
            quota_quantity=Decimal("0"),
            excess_unit_price=Decimal("0"),
            is_active=True,
            is_product_linked=True,
            source_product_id=product.id,
            source_product_name_snapshot=product.name,
            is_excluded_from_attendance=False,
            is_legacy=False,
        )
        session.add(bag_type)
        result.created_count += 1

    def _update_linked_bag_type(
        self,
        session: Session,
        bag_type: BagType,
        product: ProductCutSyncProduct,
        result: AttendanceProductSyncResult,
    ) -> None:
        changed = False
        if bag_type.name != product.name:
            if self._name_conflict_exists(session, product.name, exclude_id=bag_type.id):
                warning = f"Product rename conflicts with existing attendance CUT work item: {product.name}"
                result.warnings.append(warning)
                logger.warning(warning)
                return
            bag_type.name = product.name
            changed = True
        if bag_type.source_product_name_snapshot != product.name:
            bag_type.source_product_name_snapshot = product.name
            changed = True
        if not bag_type.is_active:
            bag_type.is_active = True
            changed = True
        if bag_type.is_legacy:
            bag_type.is_legacy = False
            changed = True
        if changed:
            result.updated_count += 1

    def _deactivate_linked_bag_type(
        self,
        session: Session,
        bag_type: BagType,
        result: AttendanceProductSyncResult,
        *,
        missing_product: bool,
    ) -> None:
        changed_deactivated = False
        if bag_type.is_active:
            bag_type.is_active = False
            changed_deactivated = True
        if changed_deactivated:
            result.deactivated_count += 1
        if missing_product or self._bag_type_has_history(session, bag_type.id):
            if not bag_type.is_legacy:
                bag_type.is_legacy = True
                result.legacy_count += 1

    def _deactivate_manual_bag_types(self, session: Session, result: AttendanceProductSyncResult) -> None:
        manual_rows = session.scalars(
            select(BagType)
            .where(BagType.is_product_linked.is_(False))
            .where(BagType.is_active.is_(True))
            .order_by(BagType.id.asc())
        ).all()
        for bag_type in manual_rows:
            has_history = self._bag_type_has_history(session, bag_type.id)
            bag_type.is_active = False
            result.deactivated_count += 1
            if has_history and not bag_type.is_legacy:
                bag_type.is_legacy = True
                result.legacy_count += 1

    def _bag_type_has_history(self, session: Session, bag_type_id: int) -> bool:
        cut_log_id = session.scalar(select(CutLog.id).where(CutLog.bag_type_id == bag_type_id).limit(1))
        if cut_log_id is not None:
            return True
        extra_log_id = session.scalar(
            select(ExtraCutWorkLog.id).where(ExtraCutWorkLog.bag_type_id == bag_type_id).limit(1)
        )
        return extra_log_id is not None

    def _name_conflict_exists(self, session: Session, name: str, *, exclude_id: int | None = None) -> bool:
        statement = select(BagType.id).where(BagType.name == name)
        if exclude_id is not None:
            statement = statement.where(BagType.id != exclude_id)
        return session.scalar(statement.limit(1)) is not None

    def _list_incomplete_cut_work_items(self, session: Session) -> list[ProductCutWorkItem]:
        rows = session.scalars(
            select(BagType)
            .where(BagType.is_product_linked.is_(True))
            .where(BagType.is_active.is_(True))
            .where(BagType.is_excluded_from_attendance.is_(False))
            .where((BagType.quota_quantity == 0) | (BagType.excess_unit_price == 0))
            .order_by(BagType.id.asc())
        ).all()
        return [
            ProductCutWorkItem(
                id=int(row.id),
                name=row.name,
                source_product_id=row.source_product_id,
                quota_quantity=Decimal(str(row.quota_quantity)),
                excess_unit_price=Decimal(str(row.excess_unit_price)),
                is_excluded_from_attendance=bool(row.is_excluded_from_attendance),
            )
            for row in rows
        ]
