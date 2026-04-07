from __future__ import annotations

from collections.abc import Sequence

from modules.returns.dto import ReturnInvoiceDTO
from modules.returns.mappers import to_dto
from modules.returns.repository import ReturnsRepository


class ReturnsService:
    def __init__(self, repository: ReturnsRepository) -> None:
        self._repository = repository

    def list_return_invoices(self) -> Sequence[ReturnInvoiceDTO]:
        return [to_dto(item) for item in self._repository.list_return_invoices()]
