from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.db import SessionFactory
from core.enums import UnitMode, UnitType
from core.exceptions import ValidationError
from modules.attendance.models import DailyRecordStatus
from modules.inventory.models import InventoryStockEffect, Product
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService


ATTENDANCE_DAILY_RECORD_SOURCE_TYPE = "ATTENDANCE_DAILY_RECORD"
CUT_LOG_SOURCE_LINE_TYPE = "CUT_LOG"
EXTRA_CUT_WORK_LOG_SOURCE_LINE_TYPE = "EXTRA_CUT_WORK_LOG"
ATTENDANCE_STOCK_EFFECT_NOTE = "Chấm công tổ cắt"


@dataclass(frozen=True, slots=True)
class AttendanceInventoryEffectLine:
    source_line_type: str
    source_line_id: int
    attendance_bag_type_id: int | None
    product_id: int | None
    quantity: Decimal | int | str


@dataclass(frozen=True, slots=True)
class AttendanceInventoryEffectSnapshot:
    daily_record_id: int
    employee_id: int | None
    work_date: date | None
    status: DailyRecordStatus | str
    is_absent: bool
    cut_lines: Sequence[AttendanceInventoryEffectLine] = field(default_factory=tuple)
    extra_cut_lines: Sequence[AttendanceInventoryEffectLine] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AttendanceInventoryEffectProductDelta:
    product_id: int
    unit_type: UnitType
    quantity_delta: Decimal


@dataclass(frozen=True, slots=True)
class AttendanceInventoryEffectResult:
    rolled_back_count: int
    applied_count: int
    product_deltas: tuple[AttendanceInventoryEffectProductDelta, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _PreparedEffectLine:
    source_line_type: str
    source_line_id: int
    attendance_bag_type_id: int | None
    product_id: int
    quantity: Decimal
    unit_type: UnitType


class AttendanceInventoryEffectService:
    def __init__(self, session_factory: sessionmaker[Session] = SessionFactory) -> None:
        self._session_factory = session_factory

    def reconcile_daily_record_effects(
        self,
        snapshot: AttendanceInventoryEffectSnapshot,
    ) -> AttendanceInventoryEffectResult:
        self._validate_snapshot_identity(snapshot)
        warnings: list[str] = []

        with self._session_factory() as session:
            transaction_context = nullcontext() if session.in_transaction() else session.begin()
            with transaction_context:
                inventory_service = InventoryService(InventoryRepository(self._session_factory))
                inventory_service.use_session(session)

                prepared_lines = self._prepare_lines(session, snapshot)
                old_effects = self._list_existing_effects(session, snapshot.daily_record_id)
                for effect in old_effects:
                    self._apply_inverse_effect(inventory_service, effect)
                    session.delete(effect)
                if old_effects:
                    session.flush()

                applied_count = 0
                product_totals: dict[tuple[int, UnitType], Decimal] = defaultdict(Decimal)
                if self._should_apply(snapshot):
                    movement_datetime = self._movement_datetime(snapshot.work_date)
                    for line in prepared_lines:
                        inventory_service.increase_stock(line.product_id, line.quantity, line.unit_type)
                        session.add(
                            InventoryStockEffect(
                                source_type=ATTENDANCE_DAILY_RECORD_SOURCE_TYPE,
                                source_id=snapshot.daily_record_id,
                                source_line_type=line.source_line_type,
                                source_line_id=line.source_line_id,
                                attendance_employee_id=snapshot.employee_id,
                                attendance_work_date=snapshot.work_date,
                                attendance_bag_type_id=line.attendance_bag_type_id,
                                product_id=line.product_id,
                                quantity_delta=line.quantity,
                                unit_type=line.unit_type,
                                movement_datetime=movement_datetime,
                                note=ATTENDANCE_STOCK_EFFECT_NOTE,
                            )
                        )
                        product_totals[(line.product_id, line.unit_type)] += line.quantity
                        applied_count += 1

                session.flush()

        deltas = tuple(
            AttendanceInventoryEffectProductDelta(
                product_id=product_id,
                unit_type=unit_type,
                quantity_delta=quantity_delta,
            )
            for (product_id, unit_type), quantity_delta in sorted(product_totals.items())
        )
        return AttendanceInventoryEffectResult(
            rolled_back_count=len(old_effects),
            applied_count=applied_count,
            product_deltas=deltas,
            warnings=tuple(warnings),
        )

    def _prepare_lines(
        self,
        session: Session,
        snapshot: AttendanceInventoryEffectSnapshot,
    ) -> list[_PreparedEffectLine]:
        if not self._should_apply(snapshot):
            return []

        raw_lines = [
            *snapshot.cut_lines,
            *snapshot.extra_cut_lines,
        ]
        product_ids = self._collect_product_ids(raw_lines)
        products_by_id = self._load_products_by_id(session, product_ids)
        prepared: list[_PreparedEffectLine] = []
        seen_source_lines: set[tuple[str, int]] = set()
        for line in raw_lines:
            if line.source_line_type not in {CUT_LOG_SOURCE_LINE_TYPE, EXTRA_CUT_WORK_LOG_SOURCE_LINE_TYPE}:
                raise ValidationError("Loại dòng chấm công không hợp lệ để cập nhật tồn kho.")
            if line.source_line_id is None:
                raise ValidationError("Thiếu mã dòng nguồn tồn kho từ chấm công.")
            source_line_id = int(line.source_line_id)
            source_key = (line.source_line_type, source_line_id)
            if source_key in seen_source_lines:
                raise ValidationError("Dòng nguồn tồn kho từ chấm công bị trùng.")
            seen_source_lines.add(source_key)
            if line.product_id is None:
                raise ValidationError("Dòng chấm công chưa liên kết hàng hóa tồn kho.")
            quantity = self._to_decimal(line.quantity)
            if quantity < Decimal("0"):
                raise ValidationError("Số lượng cập nhật tồn kho từ chấm công phải >= 0.")
            product = products_by_id.get(line.product_id)
            if product is None:
                raise ValidationError(f"Không tìm thấy hàng hóa tồn kho id={line.product_id}.")
            prepared.append(
                _PreparedEffectLine(
                    source_line_type=line.source_line_type,
                    source_line_id=source_line_id,
                    attendance_bag_type_id=line.attendance_bag_type_id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_type=self._unit_type_for_product(product),
                )
            )
        return prepared

    def _collect_product_ids(self, lines: Sequence[AttendanceInventoryEffectLine]) -> set[int]:
        product_ids: set[int] = set()
        for line in lines:
            if line.product_id is None:
                raise ValidationError("Dòng chấm công chưa liên kết hàng hóa tồn kho.")
            product_ids.add(int(line.product_id))
        return product_ids

    def _load_products_by_id(self, session: Session, product_ids: set[int]) -> dict[int, Product]:
        if not product_ids:
            return {}
        products = session.scalars(select(Product).where(Product.id.in_(product_ids))).all()
        return {product.id: product for product in products}

    def _list_existing_effects(self, session: Session, daily_record_id: int) -> list[InventoryStockEffect]:
        statement = (
            select(InventoryStockEffect)
            .where(
                InventoryStockEffect.source_type == ATTENDANCE_DAILY_RECORD_SOURCE_TYPE,
                InventoryStockEffect.source_id == daily_record_id,
            )
            .order_by(InventoryStockEffect.id.asc())
        )
        return list(session.scalars(statement).all())

    def _apply_inverse_effect(self, inventory_service: InventoryService, effect: InventoryStockEffect) -> None:
        quantity = self._to_decimal(effect.quantity_delta)
        if quantity >= Decimal("0"):
            inventory_service.decrease_stock(effect.product_id, quantity, effect.unit_type)
            return
        inventory_service.increase_stock(effect.product_id, abs(quantity), effect.unit_type)

    def _unit_type_for_product(self, product: Product) -> UnitType:
        if product.unit_mode == UnitMode.BAO_KG:
            return UnitType.BAO
        if product.unit_mode == UnitMode.BICH:
            return UnitType.BICH
        raise ValidationError("Kiểu đơn vị hàng hóa không hỗ trợ cập nhật tồn kho từ chấm công.")

    def _should_apply(self, snapshot: AttendanceInventoryEffectSnapshot) -> bool:
        status = snapshot.status.value if isinstance(snapshot.status, DailyRecordStatus) else str(snapshot.status)
        return status == DailyRecordStatus.DONE.value and not snapshot.is_absent

    def _validate_snapshot_identity(self, snapshot: AttendanceInventoryEffectSnapshot) -> None:
        if snapshot.daily_record_id <= 0:
            raise ValidationError("daily_record_id là bắt buộc để cập nhật tồn kho từ chấm công.")

    def _movement_datetime(self, work_date: date | None) -> datetime | None:
        if work_date is None:
            return None
        return datetime.combine(work_date, time.min)

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
