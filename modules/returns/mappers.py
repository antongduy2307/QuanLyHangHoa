from __future__ import annotations

from modules.returns.dto import ReturnInvoiceDTO
from modules.returns.models import ReturnInvoice



def to_dto(model: ReturnInvoice) -> ReturnInvoiceDTO:
    return ReturnInvoiceDTO(
        id=model.id,
        return_code=model.return_code,
        source_invoice_id=model.source_invoice_id,
        total_amount=model.total_amount,
        handling_mode=model.handling_mode.value,
        return_datetime=model.return_datetime,
    )
