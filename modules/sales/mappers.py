from __future__ import annotations

from modules.sales.dto import InvoiceDTO
from modules.sales.models import Invoice



def to_dto(model: Invoice) -> InvoiceDTO:
    return InvoiceDTO(
        id=model.id,
        invoice_code=model.invoice_code,
        customer_snapshot_name=model.customer_snapshot_name,
        total_amount=model.total_amount,
        status=model.status.value,
        invoice_datetime=model.invoice_datetime,
    )
