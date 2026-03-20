from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def today_for_tz(tz: str = "UTC") -> date:
    """Return today's date in the given IANA timezone."""

    try:
        return datetime.now(ZoneInfo(tz)).date()
    except (KeyError, ValueError):
        return datetime.now(timezone.utc).date()


def get_first_date_of_current_month(tz: str = "UTC") -> date:
    """Get the first date of the current month."""

    return today_for_tz(tz).replace(day=1)


def get_previous_month_range(tz: str = "UTC") -> tuple[date, date]:
    """Get the first and last dates of the previous month."""

    first_of_current = today_for_tz(tz).replace(day=1)
    last_day = first_of_current - timedelta(days=1)
    first_day = last_day.replace(day=1)

    return first_day, last_day


def first_year_date(tz: str = "UTC") -> date:
    """Return the first date of the current year."""

    return date(year=today_for_tz(tz).year, month=1, day=1)
