from __future__ import annotations

from modules.reporting.dto import ReportingSummaryDTO
from modules.reporting.repository import ReportingRepository


class ReportingService:
    def __init__(self, repository: ReportingRepository) -> None:
        self._repository = repository

    def get_summary(self) -> ReportingSummaryDTO:
        return self._repository.get_summary()
