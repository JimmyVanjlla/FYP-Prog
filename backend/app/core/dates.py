"""Date helpers shared by the services."""
from datetime import date, datetime, timedelta, timezone

from app.core.config import get_settings


def end_of_day(d: date) -> datetime:
    """The last instant of `d`, timezone-aware.

    created_at / logged_at columns are timezone-aware datetimes. Comparing
    one against a bare date (`col <= some_date`) casts the date to midnight
    at the *start* of that day, which silently excludes everything that
    happened later on the day itself — so "through today", "through the end
    of the month" and "through the last day of the week" all lost their final
    day. Bound ranges with this instead.
    """
    return datetime(d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=timezone.utc)


def restaurant_today() -> date:
    """Today's date where the restaurant is. The server runs on UTC, which is
    still "yesterday" in Malaysia for the first eight hours of every day, so a
    forecast or prep list for "today" would otherwise be a day behind."""
    return (datetime.now(timezone.utc) + timedelta(hours=get_settings().restaurant_utc_offset_hours)).date()
