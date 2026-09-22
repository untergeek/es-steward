"""Epoch math for age/period predicates (Curator-compatible)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

_UNIT_SECONDS = {
    "seconds": 1,
    "minutes": 60,
    "hours": 3600,
    "days": 86400,
    "weeks": 604800,
    "months": 2592000,
    "years": 31536000,
}

_DATE_WIDTH = {
    "Y": "4",
    "G": "4",
    "y": "2",
    "m": "2",
    "W": "2",
    "V": "2",
    "U": "2",
    "d": "2",
    "H": "2",
    "M": "2",
    "S": "2",
    "j": "3",
    "w": "1",
}

_RELATIVE_UNITS = frozenset({"hours", "days", "weeks", "months", "years"})


def fix_epoch(epoch: float | str) -> int:
    """Normalize ES/cat timestamps to epoch seconds."""
    value = int(float(epoch))
    digits = len(str(abs(value)))
    if digits <= 10:
        return value
    if digits <= 13:
        return value // 1000
    return value // 10 ** (digits - 10)


def point_of_reference(unit: str, count: int, epoch: int | None = None) -> int:
    """Return ``epoch - unit*count`` in seconds (now if ``epoch`` is omitted)."""
    try:
        multiplier = _UNIT_SECONDS[unit]
    except KeyError as exc:
        raise ValueError(f"invalid unit: {unit}") from exc
    if epoch is None:
        epoch = int(datetime.now(UTC).timestamp())
    return fix_epoch(epoch) - multiplier * count


def timestring_regex(timestring: str) -> str:
    """Build a date-capture regex from an ``strftime`` timestring."""
    prev = ""
    parts: list[str] = []
    for char in timestring:
        if char == "%":
            pass
        elif char in _DATE_WIDTH and prev == "%":
            parts.append(r"\d{" + _DATE_WIDTH[char] + "}")
        elif char in ".-":
            parts.append("\\" + char)
        else:
            parts.append(char)
        prev = char
    return "(?P<date>" + "".join(parts) + ")"


def parse_timestring(stamp: str, timestring: str) -> datetime:
    """Parse ``stamp`` with ``timestring`` as UTC.

    Monthly ``%Y.%m`` and week tokens get a dummy day/weekday so ``strptime``
    can fill a complete date (same compensation Curator uses).
    """
    ts = timestring
    text = stamp
    if "%W" in ts or "%U" in ts or "%V" in ts:
        ts += "%w"
        text += "1"
        ts = ts.replace("%G", "%Y").replace("%V", "%W")
    elif "%m" in ts and "%d" not in ts:
        ts += "%d"
        text += "1"
    return datetime.strptime(text, ts).replace(tzinfo=UTC)


def name_epoch(name: str, timestring: str) -> int | None:
    """Extract an epoch from ``name`` using ``timestring``, or None."""
    match = re.search(timestring_regex(timestring), name)
    if not match or not match.group("date"):
        return None
    try:
        return int(parse_timestring(match.group("date"), timestring).timestamp())
    except ValueError:
        return None


def relative_range(
    unit: str,
    range_from: int,
    range_to: int,
    epoch: int | None = None,
    week_starts_on: str = "sunday",
) -> tuple[int, int]:
    """Inclusive epoch window for a relative period (truncated to whole units)."""
    if unit not in _RELATIVE_UNITS:
        raise ValueError(f"invalid period unit: {unit}")
    if range_to < range_from:
        raise ValueError("range_to must be >= range_from")
    if epoch is None:
        epoch = int(datetime.now(UTC).timestamp())
    epoch = fix_epoch(epoch)
    raw = datetime.fromtimestamp(epoch, UTC)
    origin = range_from * -1
    if unit == "hours":
        start = datetime(raw.year, raw.month, raw.day, raw.hour, tzinfo=UTC) - timedelta(
            hours=origin
        )
    elif unit == "days":
        start = datetime(raw.year, raw.month, raw.day, tzinfo=UTC) - timedelta(days=origin)
    elif unit == "weeks":
        point = datetime(raw.year, raw.month, raw.day, tzinfo=UTC)
        weekday = point.weekday()
        if week_starts_on.lower() == "sunday":
            weekday += 1
        start = point - timedelta(days=weekday, weeks=origin)
    elif unit == "months":
        year, month = raw.year, raw.month
        if origin > 0:
            for _ in range(origin):
                year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        else:
            for _ in range(origin, 0):
                year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        start = datetime(year, month, 1, tzinfo=UTC)
    else:
        start = datetime(raw.year - origin, 1, 1, tzinfo=UTC)
    start_epoch = int(start.timestamp())
    count = (range_to - range_from) + 1
    if unit == "months":
        year, month = start.year, start.month
        for _ in range(count):
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        end_epoch = int(datetime(year, month, 1, tzinfo=UTC).timestamp()) - 1
    elif unit == "years":
        end_epoch = int(datetime(start.year + count, 1, 1, tzinfo=UTC).timestamp()) - 1
    else:
        end_epoch = point_of_reference(unit, -count, epoch=start_epoch) - 1
    return start_epoch, end_epoch


def absolute_range(
    unit: str,
    date_from: str,
    date_to: str,
    date_from_format: str,
    date_to_format: str,
) -> tuple[int, int]:
    """Inclusive epoch window from absolute ``date_from``/``date_to`` strings."""
    if unit not in _UNIT_SECONDS:
        raise ValueError(f"invalid unit: {unit}")
    start_epoch = int(parse_timestring(date_from, date_from_format).timestamp())
    end_date = parse_timestring(date_to, date_to_format)
    if unit == "months":
        year, month = end_date.year, end_date.month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        end_epoch = int(datetime(year, month, 1, tzinfo=UTC).timestamp()) - 1
    elif unit == "years":
        end_epoch = int(datetime(end_date.year + 1, 1, 1, tzinfo=UTC).timestamp()) - 1
    else:
        end_epoch = point_of_reference(unit, -1, epoch=int(end_date.timestamp())) - 1
    return start_epoch, end_epoch
