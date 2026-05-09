from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.attendance.models import BagType, Team, WorkInputType, WorkType


DEFAULT_WORK_TYPES: tuple[tuple[str, WorkInputType, int], ...] = (
    ("Thừa máy", WorkInputType.QUANTITY, 80000),
    ("Máy nhỏ", WorkInputType.QUANTITY, 30000),
    ("Máy to", WorkInputType.QUANTITY, 40000),
    ("Phụ cắt", WorkInputType.QUANTITY, 50000),
    ("Phụ găng 1 máy", WorkInputType.TICK, 30000),
    ("Phụ găng 2 máy", WorkInputType.TICK, 50000),
)

DEFAULT_BAG_TYPES: tuple[tuple[str, int, int, int, bool], ...] = (
    ("Bao 25kg", 3500, 0, 3500, True),
    ("Bao 50kg", 4200, 0, 4200, True),
    ("Bao PP", 3900, 0, 3900, False),
)


def seed_attendance_defaults(session: Session) -> None:
    existing_work_names = set(session.scalars(select(WorkType.name).where(WorkType.team == Team.BLOW)).all())
    for name, input_type, unit_price in DEFAULT_WORK_TYPES:
        if name not in existing_work_names:
            session.add(
                WorkType(
                    name=name,
                    team=Team.BLOW,
                    input_type=input_type,
                    unit_price=unit_price,
                    is_active=True,
                )
            )

    existing_bag_names = set(session.scalars(select(BagType.name)).all())
    for name, unit_price, quota_quantity, excess_unit_price, is_active in DEFAULT_BAG_TYPES:
        if name not in existing_bag_names:
            session.add(
                BagType(
                    name=name,
                    unit_price=unit_price,
                    quota_quantity=quota_quantity,
                    excess_unit_price=excess_unit_price,
                    is_active=is_active,
                )
            )
