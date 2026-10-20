from datetime import UTC, datetime


def now_iso() -> str:
    """The current time as ISO 8601 text with milliseconds, such as 2026-10-21T14:03:12.481Z."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
