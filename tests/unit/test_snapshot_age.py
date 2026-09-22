"""Age/period creation_date on snapshot names uses snapshot.get."""

from __future__ import annotations

from datetime import UTC, datetime
from fnmatch import fnmatch
from typing import Any
from unittest.mock import MagicMock

import pytest
from es_tools.select import SelectContext

from es_steward.select import AgeFilter, PeriodFilter
from es_steward.select.predicates import apply_predicates

EPOCH = 1_700_000_000
OLD_MS = (EPOCH - 2 * 86400) * 1000
NEW_MS = EPOCH * 1000


class _Snapshot:
    def __init__(self, snapshots: list[dict[str, Any]]) -> None:
        self.snapshots = snapshots
        self.calls = 0

    def get(self, repository: str | None = None, snapshot: str | None = None, **kwargs: object) -> dict:
        del repository, kwargs
        self.calls += 1
        if not snapshot or snapshot == "*":
            return {"snapshots": list(self.snapshots)}
        pats = str(snapshot).split(",")
        found = [
            s
            for s in self.snapshots
            if any(fnmatch(str(s.get("snapshot") or ""), p) for p in pats)
        ]
        return {"snapshots": found}


class _Client:
    def __init__(self, snapshots: list[dict[str, Any]]) -> None:
        self.snapshot = _Snapshot(snapshots)


def _snaps() -> list[dict[str, Any]]:
    return [
        {"snapshot": "snap-old", "start_time_in_millis": OLD_MS},
        {"snapshot": "snap-new", "start_time_in_millis": NEW_MS},
    ]


def test_age_snapshot_creation_date_older() -> None:
    ctx = SelectContext(client=_Client(_snaps()), target="snapshot", repository="repo")
    names = apply_predicates(
        ctx,
        ["snap-old", "snap-new"],
        [
            AgeFilter(
                source="creation_date",
                direction="older",
                unit="days",
                unit_count=1,
                epoch=EPOCH,
            )
        ],
    )
    assert names == ["snap-old"]


def test_period_snapshot_creation_date() -> None:
    ctx = SelectContext(client=_Client(_snaps()), target="snapshot", repository="repo")
    names = apply_predicates(
        ctx,
        ["snap-old", "snap-new"],
        [
            PeriodFilter(
                source="creation_date",
                period_type="relative",
                unit="days",
                range_from=-3,
                range_to=-1,
                epoch=EPOCH,
            )
        ],
    )
    assert names == ["snap-old"]


def test_snapshot_age_unknown_name_always_dropped() -> None:
    ctx = SelectContext(client=_Client(_snaps()), target="snapshot", repository="repo")
    names = apply_predicates(
        ctx,
        ["snap-old", "ghost"],
        [
            AgeFilter(
                source="creation_date",
                direction="older",
                unit="days",
                unit_count=1,
                epoch=EPOCH,
                exclude=True,
            )
        ],
    )
    assert "ghost" not in names


def test_snapshot_age_requires_repository() -> None:
    ctx = SelectContext(client=_Client(_snaps()), target="snapshot")
    with pytest.raises(ValueError, match="repository"):
        apply_predicates(
            ctx,
            ["snap-old"],
            [
                AgeFilter(
                    source="creation_date",
                    direction="older",
                    unit="days",
                    unit_count=1,
                    epoch=EPOCH,
                )
            ],
        )


def test_snapshot_age_name_source_skips_snapshot_get() -> None:
    boom = MagicMock()
    boom.snapshot.get.side_effect = AssertionError("snapshot.get must not be called")
    ctx = SelectContext(client=boom, target="snapshot", repository="repo")
    names = apply_predicates(
        ctx,
        ["snap-2017.04.01", "snap-2017.04.06"],
        [
            AgeFilter(
                source="name",
                timestring="%Y.%m.%d",
                direction="older",
                unit="days",
                unit_count=3,
                epoch=int(datetime(2017, 4, 7, 15, tzinfo=UTC).timestamp()),
            )
        ],
    )
    assert names == ["snap-2017.04.01"]
    boom.snapshot.get.assert_not_called()


def test_index_creation_date_skips_snapshot_get() -> None:
    boom = MagicMock()
    boom.snapshot.get.side_effect = AssertionError("snapshot.get must not be called")
    boom.cat.indices.return_value = [
        {
            "index": "logs-1",
            "status": "open",
            "creation.date": str(OLD_MS),
            "pri.store.size": "1",
            "store.size": "1",
        },
        {
            "index": "logs-2",
            "status": "open",
            "creation.date": str(NEW_MS),
            "pri.store.size": "1",
            "store.size": "1",
        },
    ]
    ctx = SelectContext(client=boom, target="index")
    names = apply_predicates(
        ctx,
        ["logs-1", "logs-2"],
        [
            AgeFilter(
                source="creation_date",
                direction="older",
                unit="days",
                unit_count=1,
                epoch=EPOCH,
            )
        ],
    )
    assert names == ["logs-1"]
    boom.snapshot.get.assert_not_called()
