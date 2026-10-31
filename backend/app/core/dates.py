"""Date helpers shared by the services."""
from datetime import date, datetime, timezone


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
