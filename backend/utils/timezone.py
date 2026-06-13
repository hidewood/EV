from datetime import datetime, timedelta, timezone


LOCAL_OFFSET = timedelta(hours=8)


def local_now():
    return datetime.now(timezone.utc).replace(tzinfo=None) + LOCAL_OFFSET


def to_local_iso(dt):
    if not dt:
        return None
    return dt.isoformat(timespec="seconds")
