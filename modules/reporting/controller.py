from __future__ import annotations

from datetime import date, datetime

from modules.reporting.dto import DateRangePresetDTO, RevenueTimeseriesPointDTO, SalesSummaryDTO, TopProductReportRowDTO
from modules.reporting.repository import ReportingRepository
from modules.reporting.service import ReportingService


class ReportingController:
    def __init__(self, repository: ReportingRepository) -> None:
        self._service = ReportingService(repository)

    def resolve_range(
        self,
        preset: str,
        *,
        custom_start: datetime | None = None,
        custom_end: datetime | None = None,
    ) -> DateRangePresetDTO:
        return self._service.resolve_preset_range(
            preset,
            custom_start=custom_start,
            custom_end=custom_end,
        )

    def load_summary(self, start_datetime: datetime, end_datetime: datetime) -> SalesSummaryDTO:
        return self._service.get_sales_summary(start_datetime, end_datetime)

    def load_top_products(
        self,
        start_datetime: datetime,
        end_datetime: datetime,
        *,
        sort_by: str,
        limit: int,
    ) -> list[TopProductReportRowDTO]:
        return self._service.get_top_products(start_datetime, end_datetime, sort_by=sort_by, limit=limit)

    def load_timeseries(self, start_date: date, end_date: date) -> list[RevenueTimeseriesPointDTO]:
        return self._service.get_revenue_timeseries(start_date, end_date, bucket="day")
