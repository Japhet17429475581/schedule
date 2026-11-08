from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Moscow")


def local_today() -> date:
    return datetime.now(LOCAL_TZ).date()


def utc_now() -> datetime:
    """UTC without tzinfo, matching the existing database timestamps."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


WEEKDAYS_RU = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def week_bounds(target: date | None = None) -> tuple[date, date]:
    target = target or local_today()
    monday = target - timedelta(days=target.weekday())
    return monday, monday + timedelta(days=6)


def weekday_ru(value: date) -> str:
    return WEEKDAYS_RU[value.weekday()]
