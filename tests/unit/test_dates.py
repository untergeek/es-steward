"""Tests for age/period epoch math."""

from __future__ import annotations

from datetime import UTC, datetime

from es_steward.select.dates import name_epoch, relative_range


def test_relative_range_matches_curator_table() -> None:
    epoch = int(datetime(2017, 4, 3, 13, 45, 23, tzinfo=UTC).timestamp())
    day_m1, _ = relative_range("days", -1, -1, epoch=epoch)
    day_0, _ = relative_range("days", 0, 0, epoch=epoch)
    assert day_m1 == int(datetime(2017, 4, 2, tzinfo=UTC).timestamp())
    assert day_0 == int(datetime(2017, 4, 3, tzinfo=UTC).timestamp())

    hour_m1, _ = relative_range("hours", -1, -1, epoch=epoch)
    assert hour_m1 == int(datetime(2017, 4, 3, 12, tzinfo=UTC).timestamp())

    sun_0, _ = relative_range("weeks", 0, 0, epoch=epoch, week_starts_on="sunday")
    sun_m1, _ = relative_range("weeks", -1, -1, epoch=epoch, week_starts_on="sunday")
    assert sun_0 == int(datetime(2017, 4, 2, tzinfo=UTC).timestamp())
    assert sun_m1 == int(datetime(2017, 3, 26, tzinfo=UTC).timestamp())

    mon_0, _ = relative_range("weeks", 0, 0, epoch=epoch, week_starts_on="monday")
    assert mon_0 == int(datetime(2017, 4, 3, tzinfo=UTC).timestamp())

    month_0, _ = relative_range("months", 0, 0, epoch=epoch)
    month_m1, _ = relative_range("months", -1, -1, epoch=epoch)
    assert month_0 == int(datetime(2017, 4, 1, tzinfo=UTC).timestamp())
    assert month_m1 == int(datetime(2017, 3, 1, tzinfo=UTC).timestamp())

    year_0, _ = relative_range("years", 0, 0, epoch=epoch)
    year_m1, _ = relative_range("years", -1, -1, epoch=epoch)
    assert year_0 == int(datetime(2017, 1, 1, tzinfo=UTC).timestamp())
    assert year_m1 == int(datetime(2016, 1, 1, tzinfo=UTC).timestamp())


def test_name_epoch_parses_daily_timestring() -> None:
    assert name_epoch("logs-2017.04.01", "%Y.%m.%d") == int(
        datetime(2017, 4, 1, tzinfo=UTC).timestamp()
    )
    assert name_epoch("no-date", "%Y.%m.%d") is None
