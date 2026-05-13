from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from core.db import SessionFactory
from core.enums import UnitMode, UnitType
from core.exceptions import NotFoundError
from modules.attendance.db import AttendanceSessionLocal
from modules.attendance.inventory_effect_service import (
    ATTENDANCE_DAILY_RECORD_SOURCE_TYPE,
    CUT_LOG_SOURCE_LINE_TYPE,
    EXTRA_CUT_WORK_LOG_SOURCE_LINE_TYPE,
    AttendanceInventoryEffectLine,
    AttendanceInventoryEffectResult,
    AttendanceInventoryEffectService,
    AttendanceInventoryEffectSnapshot,
)
from modules.attendance.models import BagType, CutLog, DailyRecord, DailyRecordStatus, ExtraCutWorkLog
from modules.inventory.models import InventoryStockEffect, Product


class AttendanceInventoryIssueType(StrEnum):
    MISSING_EFFECTS_FOR_DONE_RECORD = "MISSING_EFFECTS_FOR_DONE_RECORD"
    STALE_EFFECTS_FOR_DRAFT_OR_ABSENT_RECORD = "STALE_EFFECTS_FOR_DRAFT_OR_ABSENT_RECORD"
    STALE_EFFECTS_FOR_MISSING_DAILY_RECORD = "STALE_EFFECTS_FOR_MISSING_DAILY_RECORD"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    PRODUCT_MISMATCH = "PRODUCT_MISMATCH"
    MISSING_PRODUCT_LINK = "MISSING_PRODUCT_LINK"
    MISSING_MAIN_PRODUCT = "MISSING_MAIN_PRODUCT"


@dataclass(frozen=True, slots=True)
class AttendanceInventoryDiagnosticIssue:
    issue_type: AttendanceInventoryIssueType
    severity: str
    daily_record_id: int
    employee_id: int | None
    work_date: object | None
    message: str
    expected_lines_summary: str = ""
    actual_effects_summary: str = ""


@dataclass(frozen=True, slots=True)
class _ExpectedEffects:
    aggregate: dict[tuple[int, UnitType], Decimal]
    issues: list[AttendanceInventoryDiagnosticIssue]
    summary: str


class AttendanceInventoryDiagnosticService:
    def __init__(
        self,
        *,
        attendance_session_factory: sessionmaker[Session] = AttendanceSessionLocal,
        main_session_factory: sessionmaker[Session] = SessionFactory,
        effect_service: AttendanceInventoryEffectService | None = None,
    ) -> None:
        self._attendance_session_factory = attendance_session_factory
        self._main_session_factory = main_session_factory
        self._effect_service = effect_service or AttendanceInventoryEffectService(main_session_factory)

    def build_snapshot_for_daily_record(self, daily_record_id: int) -> AttendanceInventoryEffectSnapshot:
        with self._attendance_session_factory() as session:
            record = self._get_daily_record_for_snapshot(session, daily_record_id)
            return self._snapshot_from_record(record)

    def list_issues(self) -> list[AttendanceInventoryDiagnosticIssue]:
        with self._attendance_session_factory() as attendance_session, self._main_session_factory() as main_session:
            records = self._list_attendance_records(attendance_session)
            records_by_id = {record.id: record for record in records}
            effects_by_source_id = self._list_effects_by_source_id(main_session)
            products_by_id = self._list_products_by_id(main_session)
            issues: list[AttendanceInventoryDiagnosticIssue] = []

            for record in records:
                source_effects = effects_by_source_id.get(record.id, [])
                snapshot = self._snapshot_from_record(record)
                if not self._record_should_have_effects(snapshot):
                    if source_effects:
                        issues.append(
                            AttendanceInventoryDiagnosticIssue(
                                issue_type=AttendanceInventoryIssueType.STALE_EFFECTS_FOR_DRAFT_OR_ABSENT_RECORD,
                                severity="error",
                                daily_record_id=record.id,
                                employee_id=record.employee_id,
                                work_date=record.date,
                                message="Daily record is not active DONE production but inventory effects still exist.",
                                expected_lines_summary="",
                                actual_effects_summary=self._summarize_effects(source_effects),
                            )
                        )
                    continue

                expected = self._expected_effects(snapshot, products_by_id)
                issues.extend(expected.issues)
                if expected.issues:
                    continue

                if not source_effects:
                    issues.append(
                        AttendanceInventoryDiagnosticIssue(
                            issue_type=AttendanceInventoryIssueType.MISSING_EFFECTS_FOR_DONE_RECORD,
                            severity="warning",
                            daily_record_id=record.id,
                            employee_id=record.employee_id,
                            work_date=record.date,
                            message="DONE attendance production has no inventory effects. May be historical pre-integration record or failed sync.",
                            expected_lines_summary=expected.summary,
                            actual_effects_summary="",
                        )
                    )
                    continue

                actual = self._aggregate_effects(source_effects)
                if actual != expected.aggregate:
                    issue_type = self._mismatch_type(expected.aggregate, actual)
                    issues.append(
                        AttendanceInventoryDiagnosticIssue(
                            issue_type=issue_type,
                            severity="error",
                            daily_record_id=record.id,
                            employee_id=record.employee_id,
                            work_date=record.date,
                            message="Attendance production and inventory effects do not match.",
                            expected_lines_summary=expected.summary,
                            actual_effects_summary=self._summarize_aggregate(actual),
                        )
                    )

            for source_id, effects in effects_by_source_id.items():
                if source_id in records_by_id:
                    continue
                issues.append(
                    AttendanceInventoryDiagnosticIssue(
                        issue_type=AttendanceInventoryIssueType.STALE_EFFECTS_FOR_MISSING_DAILY_RECORD,
                        severity="error",
                        daily_record_id=source_id,
                        employee_id=None,
                        work_date=None,
                        message="Inventory effects reference a missing attendance daily record.",
                        expected_lines_summary="",
                        actual_effects_summary=self._summarize_effects(effects),
                    )
                )

            return sorted(issues, key=lambda issue: (issue.daily_record_id, issue.issue_type.value))

    def reconcile_daily_record(self, daily_record_id: int) -> AttendanceInventoryEffectResult:
        snapshot = self.build_snapshot_for_daily_record(daily_record_id)
        return self._effect_service.reconcile_daily_record_effects(snapshot)

    def _get_daily_record_for_snapshot(self, session: Session, daily_record_id: int) -> DailyRecord:
        record = session.scalar(
            select(DailyRecord)
            .options(
                selectinload(DailyRecord.cut_logs).selectinload(CutLog.bag_type),
                selectinload(DailyRecord.extra_cut_work_logs).selectinload(ExtraCutWorkLog.bag_type),
            )
            .where(DailyRecord.id == daily_record_id)
        )
        if record is None:
            raise NotFoundError(f"DailyRecord {daily_record_id} was not found.")
        return record

    def _list_attendance_records(self, session: Session) -> list[DailyRecord]:
        return list(
            session.scalars(
                select(DailyRecord)
                .options(
                    selectinload(DailyRecord.cut_logs).selectinload(CutLog.bag_type),
                    selectinload(DailyRecord.extra_cut_work_logs).selectinload(ExtraCutWorkLog.bag_type),
                )
                .order_by(DailyRecord.id.asc())
            ).all()
        )

    def _snapshot_from_record(self, record: DailyRecord) -> AttendanceInventoryEffectSnapshot:
        return AttendanceInventoryEffectSnapshot(
            daily_record_id=record.id,
            employee_id=record.employee_id,
            work_date=record.date,
            status=record.status,
            is_absent=record.is_absent,
            cut_lines=tuple(
                AttendanceInventoryEffectLine(
                    source_line_type=CUT_LOG_SOURCE_LINE_TYPE,
                    source_line_id=log.id,
                    attendance_bag_type_id=log.bag_type_id,
                    product_id=None if log.bag_type is None else log.bag_type.source_product_id,
                    quantity=log.quantity,
                )
                for log in record.cut_logs
            ),
            extra_cut_lines=tuple(
                AttendanceInventoryEffectLine(
                    source_line_type=EXTRA_CUT_WORK_LOG_SOURCE_LINE_TYPE,
                    source_line_id=log.id,
                    attendance_bag_type_id=log.bag_type_id,
                    product_id=None if log.bag_type is None else log.bag_type.source_product_id,
                    quantity=log.quantity,
                )
                for log in record.extra_cut_work_logs
            ),
        )

    def _list_effects_by_source_id(self, session: Session) -> dict[int, list[InventoryStockEffect]]:
        effects = session.scalars(
            select(InventoryStockEffect)
            .where(InventoryStockEffect.source_type == ATTENDANCE_DAILY_RECORD_SOURCE_TYPE)
            .order_by(InventoryStockEffect.source_id.asc(), InventoryStockEffect.id.asc())
        ).all()
        effects_by_source_id: dict[int, list[InventoryStockEffect]] = defaultdict(list)
        for effect in effects:
            effects_by_source_id[effect.source_id].append(effect)
        return effects_by_source_id

    def _list_products_by_id(self, session: Session) -> dict[int, Product]:
        return {product.id: product for product in session.scalars(select(Product)).all()}

    def _record_should_have_effects(self, snapshot: AttendanceInventoryEffectSnapshot) -> bool:
        status = snapshot.status.value if isinstance(snapshot.status, DailyRecordStatus) else str(snapshot.status)
        return (
            status == DailyRecordStatus.DONE.value
            and not snapshot.is_absent
            and bool(snapshot.cut_lines or snapshot.extra_cut_lines)
        )

    def _expected_effects(
        self,
        snapshot: AttendanceInventoryEffectSnapshot,
        products_by_id: dict[int, Product],
    ) -> _ExpectedEffects:
        aggregate: dict[tuple[int, UnitType], Decimal] = defaultdict(Decimal)
        issues: list[AttendanceInventoryDiagnosticIssue] = []
        lines = [*snapshot.cut_lines, *snapshot.extra_cut_lines]
        for line in lines:
            if line.product_id is None:
                issues.append(
                    AttendanceInventoryDiagnosticIssue(
                        issue_type=AttendanceInventoryIssueType.MISSING_PRODUCT_LINK,
                        severity="error",
                        daily_record_id=snapshot.daily_record_id,
                        employee_id=snapshot.employee_id,
                        work_date=snapshot.work_date,
                        message="Attendance production line has no linked inventory product.",
                        expected_lines_summary=self._summarize_snapshot_lines(snapshot),
                        actual_effects_summary="",
                    )
                )
                continue
            product = products_by_id.get(line.product_id)
            if product is None:
                issues.append(
                    AttendanceInventoryDiagnosticIssue(
                        issue_type=AttendanceInventoryIssueType.MISSING_MAIN_PRODUCT,
                        severity="error",
                        daily_record_id=snapshot.daily_record_id,
                        employee_id=snapshot.employee_id,
                        work_date=snapshot.work_date,
                        message=f"Linked inventory product id={line.product_id} does not exist.",
                        expected_lines_summary=self._summarize_snapshot_lines(snapshot),
                        actual_effects_summary="",
                    )
                )
                continue
            aggregate[(product.id, self._unit_type_for_product(product))] += self._to_decimal(line.quantity)
        return _ExpectedEffects(
            aggregate=dict(aggregate),
            issues=issues,
            summary=self._summarize_aggregate(aggregate),
        )

    def _aggregate_effects(self, effects: list[InventoryStockEffect]) -> dict[tuple[int, UnitType], Decimal]:
        aggregate: dict[tuple[int, UnitType], Decimal] = defaultdict(Decimal)
        for effect in effects:
            aggregate[(effect.product_id, effect.unit_type)] += self._to_decimal(effect.quantity_delta)
        return dict(aggregate)

    def _mismatch_type(
        self,
        expected: dict[tuple[int, UnitType], Decimal],
        actual: dict[tuple[int, UnitType], Decimal],
    ) -> AttendanceInventoryIssueType:
        if {product_unit[0] for product_unit in expected} != {product_unit[0] for product_unit in actual}:
            return AttendanceInventoryIssueType.PRODUCT_MISMATCH
        return AttendanceInventoryIssueType.QUANTITY_MISMATCH

    def _unit_type_for_product(self, product: Product) -> UnitType:
        return UnitType.BAO if product.unit_mode == UnitMode.BAO_KG else UnitType.BICH

    def _summarize_snapshot_lines(self, snapshot: AttendanceInventoryEffectSnapshot) -> str:
        parts = []
        for line in [*snapshot.cut_lines, *snapshot.extra_cut_lines]:
            parts.append(
                f"{line.source_line_type}:{line.source_line_id}:product={line.product_id}:qty={self._to_decimal(line.quantity)}"
            )
        return "; ".join(parts)

    def _summarize_effects(self, effects: list[InventoryStockEffect]) -> str:
        return "; ".join(
            f"{effect.source_line_type}:{effect.source_line_id}:product={effect.product_id}:"
            f"unit={effect.unit_type.value}:qty={self._to_decimal(effect.quantity_delta)}"
            for effect in effects
        )

    def _summarize_aggregate(self, aggregate: dict[tuple[int, UnitType], Decimal]) -> str:
        return "; ".join(
            f"product={product_id}:unit={unit_type.value}:qty={quantity}"
            for (product_id, unit_type), quantity in sorted(aggregate.items())
        )

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
