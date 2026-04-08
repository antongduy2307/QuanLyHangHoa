from __future__ import annotations

from modules.customer.dto import CustomerDTO
from modules.customer.models import Customer


def to_dto(model: Customer) -> CustomerDTO:
    return CustomerDTO(
        id=model.id,
        customer_name=model.customer_name,
        phone=model.phone,
        address=model.address,
        current_balance=model.current_balance,
        total_sales=model.total_sales,
        is_walk_in=model.is_walk_in,
        created_at=model.created_at,
    )
