from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from modules.reporting.dto import (
    DateRangePresetDTO,
    ReportingSummaryDTO,
    RevenueTimeseriesPointDTO,
    SalesSummaryDTO,
    TopProductReportRowDTO,
)
from modules.reporting.repository import ProductAggregateRow, ReportingRepository


class ReportingService:
    def __init__(self, repository: ReportingRepository) -> None:
        self._repository = repository

    def get_summary(self) -> ReportingSummaryDTO:
        return self._repository.get_summary()

    def get_sales_summary(self, start_datetime: datetime, end_datetime: datetime) -> SalesSummaryDTO:
        self._validate_datetime_range(start_datetime, end_datetime)
        aggregate = self._repository.get_sales_summary_aggregate(start_datetime, end_datetime)
        return SalesSummaryDTO(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            gross_sales_amount=aggregate.gross_sales_amount,
            return_amount=aggregate.return_amount,
            net_revenue=aggregate.gross_sales_amount - aggregate.return_amount,
            invoice_count=aggregate.invoice_count,
            return_count=aggregate.return_count,
        )

    def get_top_products(
        self,
        start_datetime: datetime,
        end_datetime: datetime,
        *,
        sort_by: str = "revenue",
        limit: int = 10,
    ) -> list[TopProductReportRowDTO]:
        self._validate_datetime_range(start_datetime, end_datetime)
        self._validate_sort_by(sort_by)
        self._validate_limit(limit)

        sold_rows = list(self._repository.get_sold_product_rows(start_datetime, end_datetime))
        returned_rows = list(self._repository.get_returned_product_rows(start_datetime, end_datetime))
        merged_rows = self._merge_product_rows(sold_rows, returned_rows)

        if sort_by == "revenue":
            merged_rows.sort(key=lambda row: (row.net_revenue, row.gross_revenue, row.net_quantity), reverse=True)
        else:
            merged_rows.sort(key=lambda row: (row.net_quantity, row.net_revenue, row.gross_revenue), reverse=True)
        return merged_rows[:limit]

    def get_revenue_timeseries(
        self,
        start_date: date,
        end_date: date,
        *,
        bucket: str = "day",
    ) -> list[RevenueTimeseriesPointDTO]:
        if bucket != "day":
            raise ValueError("Only bucket='day' is supported in V1.")
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date.")

        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.max)
        sales_rows = {row.bucket_date: row.amount for row in self._repository.get_daily_sales_rows(start_datetime, end_datetime)}
        return_rows = {row.bucket_date: row.amount for row in self._repository.get_daily_return_rows(start_datetime, end_datetime)}

        points: list[RevenueTimeseriesPointDTO] = []
        cursor = start_date
        while cursor <= end_date:
            key = cursor.isoformat()
            gross = sales_rows.get(key, Decimal("0"))
            returned = return_rows.get(key, Decimal("0"))
            points.append(
                RevenueTimeseriesPointDTO(
                    bucket_date=cursor,
                    gross_sales_amount=gross,
                    return_amount=returned,
                    net_revenue=gross - returned,
                )
            )
            cursor += timedelta(days=1)
        return points

    def resolve_preset_range(
        self,
        preset: str,
        *,
        now: datetime | None = None,
        custom_start: datetime | None = None,
        custom_end: datetime | None = None,
    ) -> DateRangePresetDTO:
        current = now or datetime.now()
        today = current.date()
        preset_key = preset.lower()

        if preset_key == "today":
            return self._range_for_day(today)
        if preset_key == "yesterday":
            return self._range_for_day(today - timedelta(days=1))
        if preset_key == "last_7_days":
            return DateRangePresetDTO(
                start_datetime=datetime.combine(today - timedelta(days=6), time.min),
                end_datetime=datetime.combine(today, time.max),
            )
        if preset_key == "this_week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return DateRangePresetDTO(datetime.combine(start, time.min), datetime.combine(end, time.max))
        if preset_key == "last_week":
            current_week_start = today - timedelta(days=today.weekday())
            start = current_week_start - timedelta(days=7)
            end = start + timedelta(days=6)
            return DateRangePresetDTO(datetime.combine(start, time.min), datetime.combine(end, time.max))
        if preset_key == "this_month":
            start = today.replace(day=1)
            end = self._month_end(start)
            return DateRangePresetDTO(datetime.combine(start, time.min), datetime.combine(end, time.max))
        if preset_key == "last_month":
            this_month_start = today.replace(day=1)
            end = this_month_start - timedelta(days=1)
            start = end.replace(day=1)
            return DateRangePresetDTO(datetime.combine(start, time.min), datetime.combine(end, time.max))
        if preset_key == "this_quarter":
            start = self._quarter_start(today)
            end = self._quarter_end(today)
            return DateRangePresetDTO(datetime.combine(start, time.min), datetime.combine(end, time.max))
        if preset_key == "last_quarter":
            this_quarter_start = self._quarter_start(today)
            last_quarter_end = this_quarter_start - timedelta(days=1)
            last_quarter_start = self._quarter_start(last_quarter_end)
            return DateRangePresetDTO(datetime.combine(last_quarter_start, time.min), datetime.combine(last_quarter_end, time.max))
        if preset_key == "last_year":
            year = today.year - 1
            return DateRangePresetDTO(datetime(year, 1, 1, 0, 0, 0), datetime(year, 12, 31, 23, 59, 59, 999999))
        if preset_key == "custom":
            if custom_start is None or custom_end is None:
                raise ValueError("custom preset requires custom_start and custom_end.")
            self._validate_datetime_range(custom_start, custom_end)
            return DateRangePresetDTO(custom_start, custom_end)
        raise ValueError(f"Unsupported preset: {preset}")

    def _merge_product_rows(
        self,
        sold_rows: list[ProductAggregateRow],
        returned_rows: list[ProductAggregateRow],
    ) -> list[TopProductReportRowDTO]:
        merged: dict[tuple[int, str], TopProductReportRowDTO] = {}

        for row in sold_rows:
            key = (row.product_id, row.unit_type)
            merged[key] = TopProductReportRowDTO(
                product_id=row.product_id,
                product_code=row.product_code,
                product_name=row.product_name,
                unit_type=row.unit_type,
                sold_quantity=row.quantity,
                gross_revenue=row.amount,
                returned_quantity=Decimal("0"),
                return_amount=Decimal("0"),
                net_quantity=row.quantity,
                net_revenue=row.amount,
            )

        for row in returned_rows:
            key = (row.product_id, row.unit_type)
            existing = merged.get(key)
            if existing is None:
                merged[key] = TopProductReportRowDTO(
                    product_id=row.product_id,
                    product_code=row.product_code,
                    product_name=row.product_name,
                    unit_type=row.unit_type,
                    sold_quantity=Decimal("0"),
                    gross_revenue=Decimal("0"),
                    returned_quantity=row.quantity,
                    return_amount=row.amount,
                    net_quantity=Decimal("0") - row.quantity,
                    net_revenue=Decimal("0") - row.amount,
                )
                continue

            returned_quantity = existing.returned_quantity + row.quantity
            return_amount = existing.return_amount + row.amount
            merged[key] = TopProductReportRowDTO(
                product_id=existing.product_id,
                product_code=existing.product_code,
                product_name=existing.product_name,
                unit_type=existing.unit_type,
                sold_quantity=existing.sold_quantity,
                gross_revenue=existing.gross_revenue,
                returned_quantity=returned_quantity,
                return_amount=return_amount,
                net_quantity=existing.sold_quantity - returned_quantity,
                net_revenue=existing.gross_revenue - return_amount,
            )

        return list(merged.values())

    def _range_for_day(self, target_day: date) -> DateRangePresetDTO:
        return DateRangePresetDTO(
            start_datetime=datetime.combine(target_day, time.min),
            end_datetime=datetime.combine(target_day, time.max),
        )

    def _month_end(self, target_day: date) -> date:
        if target_day.month == 12:
            return date(target_day.year, 12, 31)
        next_month_start = date(target_day.year, target_day.month + 1, 1)
        return next_month_start - timedelta(days=1)

    def _quarter_start(self, target_day: date) -> date:
        quarter_month = ((target_day.month - 1) // 3) * 3 + 1
        return date(target_day.year, quarter_month, 1)

    def _quarter_end(self, target_day: date) -> date:
        start = self._quarter_start(target_day)
        month = start.month + 2
        end_month_anchor = date(start.year, month, 1)
        return self._month_end(end_month_anchor)

    def _validate_datetime_range(self, start_datetime: datetime, end_datetime: datetime) -> None:
        if start_datetime > end_datetime:
            raise ValueError("start_datetime must be <= end_datetime.")

    def _validate_sort_by(self, sort_by: str) -> None:
        if sort_by not in {"revenue", "quantity"}:
            raise ValueError("sort_by must be either 'revenue' or 'quantity'.")

    def _validate_limit(self, limit: int) -> None:
        if limit <= 0:
            raise ValueError("limit must be > 0.")
