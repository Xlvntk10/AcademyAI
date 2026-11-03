"""One clock for local calendar days. Stored timestamps remain UTC."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

STUDY_ZONE = ZoneInfo("Asia/Almaty")


def now():
    return datetime.now(timezone.utc)


def as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def local_day(value=None):
    return as_utc(value or now()).astimezone(STUDY_ZONE).date()
