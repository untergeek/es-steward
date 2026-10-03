"""Tests for Steward predicates (not IndexList)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from es_mgmt.select import PatternFilter, SelectContext
from pydantic import ValidationError

from es_steward.select import (
    AgeFilter,
    AllocatedFilter,
    CountFilter,
    EmptyFilter,
    ForcemergedFilter,
    IlmFilter,
    OpenedFilter,
    PeriodFilter,
    ShardsFilter,
    SizeFilter,
    SpaceFilter,
    resolve,
)


class _Cat:
    def __init__(
        self,
        rows: list[dict[str, str]],
        segment_counts: dict[str, int] | None = None,
    ) -> None:
        self.rows = rows
        self.segment_counts = segment_counts or {}
        self.calls: list[str | None] = []

    def indices(self, index: str | None = None, **kwargs: object) -> list[dict[str, str]]:
        self.calls.append(index)
        if index and "," not in str(index) and "*" in str(index):
            return [r for r in self.rows if r["index"].startswith(str(index).rstrip("*"))]
        wanted = set(str(index).split(",")) if index and index != "*" else None
        if wanted:
            return [r for r in self.rows if r["index"] in wanted]
        return list(self.rows)

    def segments(self, index: str | None = None, **kwargs: object) -> list[dict[str, str]]:
        wanted = set(str(index).split(",")) if index and index != "*" else None
        rows: list[dict[str, str]] = []
        for name, count in self.segment_counts.items():
            if wanted and name not in wanted:
                continue
            rows.extend({"index": name} for _ in range(count))
        return rows


class _Ilm:
    def __init__(self, managed: dict[str, bool]) -> None:
        self.managed = managed

    def explain_lifecycle(self, index: str | None = None) -> dict:
        names = str(index).split(",") if index else list(self.managed)
        return {
            "indices": {
                n: {"managed": self.managed.get(n, False), "phase": "hot"} for n in names
            }
        }


class _Indices:
    def __init__(self, settings: dict[str, dict[str, Any]]) -> None:
        self.settings = settings

    def get_settings(self, index: str | None = None, **kwargs: object) -> dict[str, Any]:
        names = str(index).split(",") if index else list(self.settings)
        return {n: {"settings": self.settings.get(n, {})} for n in names}


class _Client:
    def __init__(
        self,
        rows: list[dict[str, str]],
        managed: dict[str, bool],
        settings: dict[str, dict[str, Any]] | None = None,
        segment_counts: dict[str, int] | None = None,
    ) -> None:
        self.cat = _Cat(rows, segment_counts)
        self.ilm = _Ilm(managed)
        self.indices = _Indices(settings or {})


def _rows() -> list[dict[str, str]]:
    return [
        {
            "index": "logs-1",
            "status": "open",
            "pri.store.size": "2000000000",
            "store.size": "2000000000",
            "docs.count": "10",
            "pri": "1",
            "rep": "0",
            "creation.date": "1491200000000",
        },
        {
            "index": "logs-2",
            "status": "open",
            "pri.store.size": "100",
            "store.size": "100",
            "docs.count": "0",
            "pri": "5",
            "rep": "0",
            "creation.date": "1491500000000",
        },
        {
            "index": "logs-3",
            "status": "close",
            "pri.store.size": "9000000000",
            "store.size": "9000000000",
            "docs.count": "0",
            "pri": "1",
            "rep": "0",
            "creation.date": "1000000000000",
        },
    ]


def _resolve(client: _Client, extra: object) -> list[str]:
    ctx = SelectContext(client=client, target="index")
    return resolve(ctx, [PatternFilter(pattern_kind="prefix", value="logs-"), extra])


def test_size_keeps_over_threshold() -> None:
    client = _Client(_rows(), {})
    ctx = SelectContext(client=client, target="index")
    names = resolve(
        ctx,
        [
            PatternFilter(pattern_kind="prefix", value="logs-"),
            SizeFilter(size_threshold_gb=1.0),
        ],
    )
    assert names == ["logs-1"]


def test_predicate_cannot_be_first() -> None:
    ctx = SelectContext(client=object(), target="index")
    with pytest.raises(ValueError, match="selector"):
        resolve(ctx, [SizeFilter(size_threshold_gb=1.0)])


def test_ilm_exclude_default_drops_managed() -> None:
    client = _Client(_rows(), {"logs-1": True, "logs-2": False, "logs-3": False})
    ctx = SelectContext(client=client, target="index")
    names = resolve(
        ctx,
        [
            PatternFilter(pattern_kind="prefix", value="logs-"),
            IlmFilter(),
        ],
    )
    assert "logs-1" not in names
    assert "logs-2" in names


def test_opened_drops_closed() -> None:
    client = _Client(_rows(), {})
    ctx = SelectContext(client=client, target="index")
    names = resolve(
        ctx,
        [
            PatternFilter(pattern_kind="prefix", value="logs-"),
            OpenedFilter(),
        ],
    )
    assert names == ["logs-1", "logs-2"]


def test_opened_drops_unknown_status() -> None:
    rows = [
        {"index": "logs-1", "status": "open", "pri.store.size": "1", "store.size": "1"},
        {"index": "logs-2", "status": "", "pri.store.size": "1", "store.size": "1"},
    ]
    names = _resolve(_Client(rows, {}), OpenedFilter())
    assert names == ["logs-1"]


def test_count_takes_first_n() -> None:
    client = _Client(_rows(), {})
    ctx = SelectContext(client=client, target="index")
    names = resolve(
        ctx,
        [
            PatternFilter(pattern_kind="prefix", value="logs-"),
            CountFilter(count=1, reverse=False),
        ],
    )
    assert names == ["logs-1"]


def test_count_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        CountFilter(count=0)


def test_empty_default_drops_empty_and_closed() -> None:
    names = _resolve(_Client(_rows(), {}), EmptyFilter())
    assert names == ["logs-1"]


def test_empty_exclude_false_keeps_only_empty_open() -> None:
    names = _resolve(_Client(_rows(), {}), EmptyFilter(exclude=False))
    assert names == ["logs-2"]


def test_shards_greater_than() -> None:
    names = _resolve(_Client(_rows(), {}), ShardsFilter(number_of_shards=1))
    assert names == ["logs-2"]


def test_shards_equal() -> None:
    names = _resolve(
        _Client(_rows(), {}),
        ShardsFilter(number_of_shards=1, shard_filter_behavior="equal"),
    )
    assert names == ["logs-1", "logs-3"]


def test_shards_less_than_one_raises() -> None:
    with pytest.raises(ValueError, match="less_than"):
        _resolve(
            _Client(_rows(), {}),
            ShardsFilter(number_of_shards=1, shard_filter_behavior="less_than"),
        )


def test_allocated_default_drops_matching() -> None:
    settings = {
        "logs-1": {"index": {"routing": {"allocation": {"require": {"tag": "hot"}}}}},
        "logs-2": {},
    }
    names = _resolve(
        _Client(_rows(), {}, settings=settings),
        AllocatedFilter(key="tag", value="hot"),
    )
    assert names == ["logs-2", "logs-3"]


def test_allocated_exclude_false_keeps_matching() -> None:
    settings = {
        "logs-1": {"index": {"routing": {"allocation": {"require": {"tag": "hot"}}}}},
    }
    names = _resolve(
        _Client(_rows(), {}, settings=settings),
        AllocatedFilter(key="tag", value="hot", exclude=False),
    )
    assert names == ["logs-1"]


def test_forcemerged_default_drops_merged() -> None:
    names = _resolve(
        _Client(_rows(), {}, segment_counts={"logs-1": 1, "logs-2": 8}),
        ForcemergedFilter(max_num_segments=1),
    )
    assert names == ["logs-2"]


def test_age_creation_date_older() -> None:
    epoch = int(datetime(2017, 4, 7, 15, tzinfo=UTC).timestamp())
    names = _resolve(
        _Client(_rows(), {}),
        AgeFilter(direction="older", unit="days", unit_count=3, epoch=epoch),
    )
    assert names == ["logs-1", "logs-3"]


def test_age_name_timestring() -> None:
    rows = [
        {
            "index": "logs-2017.04.01",
            "status": "open",
            "pri.store.size": "1",
            "store.size": "1",
        },
        {
            "index": "logs-2017.04.06",
            "status": "open",
            "pri.store.size": "1",
            "store.size": "1",
        },
    ]
    epoch = int(datetime(2017, 4, 7, 15, tzinfo=UTC).timestamp())
    names = _resolve(
        _Client(rows, {}),
        AgeFilter(
            source="name",
            timestring="%Y.%m.%d",
            direction="older",
            unit="days",
            unit_count=3,
            epoch=epoch,
        ),
    )
    assert names == ["logs-2017.04.01"]


def test_age_name_requires_timestring() -> None:
    with pytest.raises(ValidationError, match="timestring"):
        AgeFilter(source="name", direction="older", unit="days", unit_count=3)


def test_period_relative_previous_day() -> None:
    rows = [
        {
            "index": "logs-2017.04.02",
            "status": "open",
            "pri.store.size": "1",
            "store.size": "1",
        },
        {
            "index": "logs-2017.04.03",
            "status": "open",
            "pri.store.size": "1",
            "store.size": "1",
        },
    ]
    epoch = int(datetime(2017, 4, 3, 13, 45, 23, tzinfo=UTC).timestamp())
    names = _resolve(
        _Client(rows, {}),
        PeriodFilter(
            source="name",
            timestring="%Y.%m.%d",
            unit="days",
            range_from=-1,
            range_to=-1,
            epoch=epoch,
        ),
    )
    assert names == ["logs-2017.04.02"]


def test_period_absolute_month() -> None:
    rows = [
        {
            "index": "logs-2017.01.15",
            "status": "open",
            "pri.store.size": "1",
            "store.size": "1",
        },
        {
            "index": "logs-2017.02.01",
            "status": "open",
            "pri.store.size": "1",
            "store.size": "1",
        },
    ]
    names = _resolve(
        _Client(rows, {}),
        PeriodFilter(
            period_type="absolute",
            source="name",
            timestring="%Y.%m.%d",
            unit="months",
            date_from="2017.01",
            date_to="2017.01",
            date_from_format="%Y.%m",
            date_to_format="%Y.%m",
        ),
    )
    assert names == ["logs-2017.01.15"]


def test_space_cumulative_keeps_oldest_when_over() -> None:
    ten_g = str(10 * 1024**3)
    rows = [
        {
            "index": f"idx-{i}",
            "status": "open",
            "pri.store.size": ten_g,
            "store.size": ten_g,
        }
        for i in range(1, 6)
    ]
    client = _Client(rows, {})
    ctx = SelectContext(client=client, target="index")
    names = resolve(
        ctx,
        [
            PatternFilter(pattern_kind="prefix", value="idx-"),
            SpaceFilter(disk_space=21),
        ],
    )
    assert names == ["idx-1", "idx-2", "idx-3"]


def test_space_skips_closed() -> None:
    ten_g = str(10 * 1024**3)
    rows = [
        {
            "index": "idx-1",
            "status": "close",
            "pri.store.size": ten_g,
            "store.size": ten_g,
        },
        {
            "index": "idx-2",
            "status": "open",
            "pri.store.size": ten_g,
            "store.size": ten_g,
        },
        {
            "index": "idx-3",
            "status": "open",
            "pri.store.size": ten_g,
            "store.size": ten_g,
        },
    ]
    client = _Client(rows, {})
    ctx = SelectContext(client=client, target="index")
    names = resolve(
        ctx,
        [
            PatternFilter(pattern_kind="prefix", value="idx-"),
            SpaceFilter(disk_space=5),
        ],
    )
    assert names == ["idx-2", "idx-3"]
