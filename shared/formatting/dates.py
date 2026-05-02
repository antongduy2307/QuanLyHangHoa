from __future__ import annotations

from datetime import date, datetime



def format_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")



def format_datetime(value: datetime) -> str:
    return value.strftime("%d/%m/%Y %H:%M")


def format_datetime_seconds(value: datetime) -> str:
    return value.strftime("%d/%m/%Y %H:%M:%S")
