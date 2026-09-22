"""Tests for snapshot state predicate and SnapshotIndicesFilter wiring."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

import pytest
from es_tools.select import PatternFilter, SelectContext, SnapshotIndicesFilter

from es_steward.select import StateFilter, resolve
from es_steward.select.predicates import apply_predicates


class _Snapshot:
    def __init__(self, snapshots: list[dict[str, Any]]) -> None:
        self.snapshots = snapshots

    def get(self, repository: str | None = None, snapshot: str | None = None, **kwargs: object) -> dict:
        del repository, kwargs
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


def test_snapshot_indices_import_and_selects_index_names() -> None:
    client = _Client(
        [{"snapshot": "snap-1", "state": "SUCCESS", "indices": ["logs-1", "logs-2"]}]
    )
    ctx = SelectContext(
        client=client, target="index", repository="repo", snapshot="snap-1"
    )
    assert resolve(ctx, [SnapshotIndicesFilter()]) == ["logs-1", "logs-2"]


def test_state_keeps_matching_snapshots() -> None:
    client = _Client(
        [
            {"snapshot": "snap-ok", "state": "SUCCESS"},
            {"snapshot": "snap-bad", "state": "FAILED"},
        ]
    )
    ctx = SelectContext(client=client, target="index", repository="repo")
    names = apply_predicates(
        ctx, ["snap-ok", "snap-bad"], [StateFilter(state="SUCCESS")]
    )
    assert names == ["snap-ok"]


def test_state_exclude_drops_matching() -> None:
    client = _Client(
        [
            {"snapshot": "snap-ok", "state": "SUCCESS"},
            {"snapshot": "snap-bad", "state": "FAILED"},
        ]
    )
    ctx = SelectContext(client=client, target="index", repository="repo")
    names = apply_predicates(
        ctx, ["snap-ok", "snap-bad"], [StateFilter(state="SUCCESS", exclude=True)]
    )
    assert names == ["snap-bad"]


def test_state_requires_repository() -> None:
    ctx = SelectContext(client=object(), target="index")
    with pytest.raises(ValueError, match="repository"):
        apply_predicates(ctx, ["snap-ok"], [StateFilter(state="SUCCESS")])


def test_state_cannot_be_first() -> None:
    ctx = SelectContext(client=object(), target="index", repository="repo")
    with pytest.raises(ValueError, match="selector"):
        resolve(ctx, [StateFilter(state="SUCCESS")])


def test_state_accepts_incompatible() -> None:
    assert StateFilter(state="INCOMPATIBLE").state == "INCOMPATIBLE"


def test_state_unknown_name_always_dropped() -> None:
    client = _Client([{"snapshot": "snap-ok", "state": "SUCCESS"}])
    ctx = SelectContext(client=client, target="index", repository="repo")
    names = apply_predicates(
        ctx,
        ["snap-ok", "snap-missing"],
        [StateFilter(state="FAILED", exclude=True)],
    )
    assert names == ["snap-ok"]


def test_resolve_pattern_then_state_on_snapshots() -> None:
    client = _Client(
        [
            {"snapshot": "snap-ok", "state": "SUCCESS"},
            {"snapshot": "snap-bad", "state": "FAILED"},
            {"snapshot": "other-1", "state": "SUCCESS"},
        ]
    )
    ctx = SelectContext(client=client, target="snapshot", repository="repo")
    names = resolve(
        ctx,
        [
            PatternFilter(pattern_kind="prefix", value="snap-"),
            StateFilter(state="SUCCESS"),
        ],
    )
    assert names == ["snap-ok"]
