from datetime import datetime, timezone


def datetime_no_microseconds() -> datetime:
    return datetime.now(tz=timezone.utc).replace(microsecond=0)
