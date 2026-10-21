from datetime import UTC, datetime


def seconds_between(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    parse = lambda t: datetime.fromisoformat(t.replace("Z", "+00:00"))
    return (parse(end) - parse(start)).total_seconds()


def now_iso() -> str:
    """The current time as ISO 8601 text with milliseconds, such as 2026-10-21T14:03:12.481Z."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
