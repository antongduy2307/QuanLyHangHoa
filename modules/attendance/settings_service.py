from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.exceptions import NotFoundError, ValidationError
from modules.attendance.db import AttendanceSessionLocal
from modules.attendance.models import BagType, Team, WorkInputType, WorkType


class AttendanceSettingsService:
    def __init__(self, session_factory: sessionmaker[Session] = AttendanceSessionLocal) -> None:
        self._session_factory = session_factory

    def list_work_types(self, *, include_inactive: bool = True) -> Sequence[WorkType]:
        with self._session_factory() as session:
            statement = select(WorkType).where(WorkType.team == Team.BLOW).order_by(WorkType.id.asc())
            if not include_inactive:
                statement = statement.where(WorkType.is_active.is_(True))
            return session.scalars(statement).all()

    def create_work_type(
        self,
        *,
        name: str,
        input_type: WorkInputType | str,
        unit_price: int,
        is_active: bool = True,
    ) -> WorkType:
        normalized_name = self._normalize_name(name)
        normalized_input_type = self._coerce_input_type(input_type)
        normalized_price = self._validate_price(unit_price)
        with self._session_factory() as session:
            with session.begin():
                if self._work_type_name_exists(session, normalized_name):
                    raise ValidationError("Tên công việc đã tồn tại.")
                work_type = WorkType(
                    name=normalized_name,
                    team=Team.BLOW,
                    input_type=normalized_input_type,
                    unit_price=normalized_price,
                    is_active=is_active,
                )
                session.add(work_type)
                session.flush()
                return work_type

    def update_work_type(self, work_type_id: int, *, name: str, unit_price: int, is_active: bool) -> WorkType:
        normalized_name = self._normalize_name(name)
        normalized_price = self._validate_price(unit_price)
        with self._session_factory() as session:
            with session.begin():
                work_type = self._get_work_type(session, work_type_id)
                if self._work_type_name_exists(session, normalized_name, exclude_id=work_type_id):
                    raise ValidationError("Tên công việc đã tồn tại.")
                work_type.name = normalized_name
                work_type.unit_price = normalized_price
                work_type.is_active = is_active
                session.flush()
                return work_type

    def set_work_type_active(self, work_type_id: int, is_active: bool) -> WorkType:
        with self._session_factory() as session:
            with session.begin():
                work_type = self._get_work_type(session, work_type_id)
                work_type.is_active = is_active
                session.flush()
                return work_type

    def list_bag_types(self, *, include_inactive: bool = True) -> Sequence[BagType]:
        with self._session_factory() as session:
            statement = select(BagType).order_by(BagType.id.asc())
            if not include_inactive:
                statement = statement.where(BagType.is_active.is_(True))
            return session.scalars(statement).all()

    def create_bag_type(self, *, name: str, unit_price: int, is_active: bool = True) -> BagType:
        normalized_name = self._normalize_name(name)
        normalized_price = self._validate_price(unit_price)
        with self._session_factory() as session:
            with session.begin():
                if self._bag_type_name_exists(session, normalized_name):
                    raise ValidationError("Tên loại bao đã tồn tại.")
                bag_type = BagType(name=normalized_name, unit_price=normalized_price, is_active=is_active)
                session.add(bag_type)
                session.flush()
                return bag_type

    def update_bag_type(self, bag_type_id: int, *, name: str, unit_price: int, is_active: bool) -> BagType:
        normalized_name = self._normalize_name(name)
        normalized_price = self._validate_price(unit_price)
        with self._session_factory() as session:
            with session.begin():
                bag_type = self._get_bag_type(session, bag_type_id)
                if self._bag_type_name_exists(session, normalized_name, exclude_id=bag_type_id):
                    raise ValidationError("Tên loại bao đã tồn tại.")
                bag_type.name = normalized_name
                bag_type.unit_price = normalized_price
                bag_type.is_active = is_active
                session.flush()
                return bag_type

    def set_bag_type_active(self, bag_type_id: int, is_active: bool) -> BagType:
        with self._session_factory() as session:
            with session.begin():
                bag_type = self._get_bag_type(session, bag_type_id)
                bag_type.is_active = is_active
                session.flush()
                return bag_type

    def _normalize_name(self, name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise ValidationError("Tên không được để trống.")
        return normalized

    def _validate_price(self, unit_price: int) -> int:
        price = int(unit_price)
        if price < 0:
            raise ValidationError("Đơn giá không được âm.")
        return price

    def _coerce_input_type(self, input_type: WorkInputType | str) -> WorkInputType:
        if isinstance(input_type, WorkInputType):
            return input_type
        try:
            return WorkInputType(input_type)
        except ValueError as exc:
            raise ValidationError("Loại nhập không hợp lệ.") from exc

    def _get_work_type(self, session: Session, work_type_id: int) -> WorkType:
        work_type = session.get(WorkType, work_type_id)
        if work_type is None:
            raise NotFoundError("Không tìm thấy công việc.")
        return work_type

    def _get_bag_type(self, session: Session, bag_type_id: int) -> BagType:
        bag_type = session.get(BagType, bag_type_id)
        if bag_type is None:
            raise NotFoundError("Không tìm thấy loại bao.")
        return bag_type

    def _work_type_name_exists(self, session: Session, name: str, *, exclude_id: int | None = None) -> bool:
        statement = select(WorkType.id).where(WorkType.team == Team.BLOW).where(WorkType.name == name)
        if exclude_id is not None:
            statement = statement.where(WorkType.id != exclude_id)
        return session.scalar(statement.limit(1)) is not None

    def _bag_type_name_exists(self, session: Session, name: str, *, exclude_id: int | None = None) -> bool:
        statement = select(BagType.id).where(BagType.name == name)
        if exclude_id is not None:
            statement = statement.where(BagType.id != exclude_id)
        return session.scalar(statement.limit(1)) is not None
