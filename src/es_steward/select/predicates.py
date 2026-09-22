"""Predicate functions: stats only for the current name list."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from es_tools.select import SelectContext
from es_tools.utils.chunk import chunk_names

from .dates import (
    absolute_range,
    fix_epoch,
    name_epoch,
    point_of_reference,
    relative_range,
)
from .models import (
    AgeFilter,
    AllocatedFilter,
    ClosedFilter,
    CountFilter,
    EmptyFilter,
    ForcemergedFilter,
    IlmFilter,
    NoneFilter,
    OpenedFilter,
    PeriodFilter,
    Predicate,
    ShardsFilter,
    SizeFilter,
    SpaceFilter,
    StateFilter,
)

_GIB = 1024**3
_CAT_H = "index,status,pri.store.size,store.size,docs.count,pri,rep,creation.date"
_SHARD_OPS: dict[str, Callable[[int, int], bool]] = {
    "greater_than": lambda n, t: n > t,
    "greater_than_or_equal": lambda n, t: n >= t,
    "less_than": lambda n, t: n < t,
    "less_than_or_equal": lambda n, t: n <= t,
    "equal": lambda n, t: n == t,
}


def apply_predicates(
    ctx: SelectContext, names: list[str], filters: list[Predicate]
) -> list[str]:
    """Narrow ``names`` with predicates. ``names`` must already be resolved."""
    current = list(names)
    for f in filters:
        handler = _HANDLERS.get(type(f))
        if handler is None:
            raise TypeError(f"unknown predicate: {getattr(f, 'kind', type(f))}")
        current = handler(ctx, current, f)
    return current


def _as_list(raw: Any) -> list[dict[str, Any]]:
    body = raw.body if hasattr(raw, "body") else raw
    if isinstance(body, list):
        return [r for r in body if isinstance(r, dict)]
    return []


def _as_dict(raw: Any) -> dict[str, Any]:
    body = raw.body if hasattr(raw, "body") else raw
    return body if isinstance(body, dict) else {}


def _cat_rows(client: Any, names: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in chunk_names(names):
        raw = client.cat.indices(
            index=",".join(chunk),
            h=_CAT_H,
            format="json",
            bytes="b",
        )
        rows.extend(_as_list(raw))
    return rows


def _by_name(client: Any, names: list[str]) -> dict[str, dict[str, Any]]:
    return {str(r.get("index")): r for r in _cat_rows(client, names)}


def _is_closed(row: dict[str, Any]) -> bool:
    return str(row.get("status") or "").lower().startswith("close")


def _open_names(names: list[str], by_name: dict[str, dict[str, Any]]) -> list[str]:
    return [n for n in names if not _is_closed(by_name.get(n) or {})]


def _parse_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _ages(
    ctx: SelectContext,
    names: list[str],
    source: str,
    timestring: str | None,
) -> dict[str, int]:
    if source == "name":
        if not timestring:
            raise ValueError("timestring is required when source='name'")
        out: dict[str, int] = {}
        for n in names:
            ep = name_epoch(n, timestring)
            if ep is not None:
                out[n] = ep
        return out
    if ctx.target == "snapshot":
        return _snapshot_start_epochs(ctx, names)
    by_name = _by_name(ctx.client, names)
    out = {}
    for n in names:
        raw = (by_name.get(n) or {}).get("creation.date")
        if raw in (None, ""):
            continue
        try:
            out[n] = fix_epoch(raw)
        except (TypeError, ValueError):
            continue
    return out


def _snapshot_start_epochs(ctx: SelectContext, names: list[str]) -> dict[str, int]:
    if not ctx.repository:
        raise ValueError("age filter requires SelectContext.repository")
    out: dict[str, int] = {}
    for chunk in chunk_names(names):
        body = _as_dict(
            ctx.client.snapshot.get(repository=ctx.repository, snapshot=",".join(chunk))
        )
        for snap in body.get("snapshots") or []:
            if not isinstance(snap, dict) or not snap.get("snapshot"):
                continue
            raw = snap.get("start_time_in_millis")
            if raw in (None, ""):
                continue
            try:
                out[str(snap["snapshot"])] = fix_epoch(raw)
            except (TypeError, ValueError):
                continue
    return out


def _none(ctx: SelectContext, names: list[str], f: NoneFilter) -> list[str]:
    del ctx, f
    return names


def _count(ctx: SelectContext, names: list[str], f: CountFilter) -> list[str]:
    del ctx
    ordered = list(reversed(names)) if f.reverse else names
    kept = set(ordered[: f.count])
    if f.exclude:
        return [n for n in names if n not in kept]
    return [n for n in names if n in kept]


def _size(ctx: SelectContext, names: list[str], f: SizeFilter) -> list[str]:
    client = ctx.client
    keep: list[str] = []
    field = "pri.store.size" if f.size_behavior == "primary" else "store.size"
    by_name = _by_name(client, names)
    for n in names:
        row = by_name.get(n) or {}
        if _is_closed(row):
            continue
        try:
            size_b = float(row.get(field) or 0)
        except (TypeError, ValueError):
            continue
        gb = size_b / _GIB
        hit = (
            gb > f.size_threshold_gb
            if f.threshold_behavior == "greater_than"
            else gb < f.size_threshold_gb
        )
        if hit ^ f.exclude:
            keep.append(n)
    return keep


def _ilm(ctx: SelectContext, names: list[str], f: IlmFilter) -> list[str]:
    client = ctx.client
    managed: set[str] = set()
    for chunk in chunk_names(names):
        body = _as_dict(client.ilm.explain_lifecycle(index=",".join(chunk)))
        for name, info in (body.get("indices") or {}).items():
            if isinstance(info, dict) and info.get("managed"):
                managed.add(str(name))
    if f.exclude:
        return [n for n in names if n not in managed]
    return [n for n in names if n in managed]


def _status(client: Any, names: list[str], *, want_open: bool, exclude: bool) -> list[str]:
    by_name = _by_name(client, names)
    keep: list[str] = []
    for n in names:
        status = str((by_name.get(n) or {}).get("status") or "").lower()
        is_open = status.startswith("open")
        hit = is_open if want_open else (not is_open)
        if hit ^ exclude:
            keep.append(n)
    return keep


def _opened(ctx: SelectContext, names: list[str], f: OpenedFilter) -> list[str]:
    return _status(ctx.client, names, want_open=True, exclude=f.exclude)


def _closed(ctx: SelectContext, names: list[str], f: ClosedFilter) -> list[str]:
    return _status(ctx.client, names, want_open=False, exclude=f.exclude)


def _age(ctx: SelectContext, names: list[str], f: AgeFilter) -> list[str]:
    ages = _ages(ctx, names, f.source, f.timestring)
    por = point_of_reference(f.unit, f.unit_count, f.epoch)
    keep: list[str] = []
    for n in names:
        age = ages.get(n)
        if age is None:
            continue
        hit = age < por if f.direction == "older" else age > por
        if hit ^ f.exclude:
            keep.append(n)
    return keep


def _period(ctx: SelectContext, names: list[str], f: PeriodFilter) -> list[str]:
    if f.period_type == "relative":
        start, end = relative_range(
            f.unit,
            f.range_from or 0,
            f.range_to or 0,
            epoch=f.epoch,
            week_starts_on=f.week_starts_on,
        )
    else:
        start, end = absolute_range(
            f.unit,
            f.date_from or "",
            f.date_to or "",
            f.date_from_format or "",
            f.date_to_format or "",
        )
    ages = _ages(ctx, names, f.source, f.timestring)
    keep: list[str] = []
    for n in names:
        age = ages.get(n)
        if age is None:
            continue
        hit = start <= age <= end
        if hit ^ f.exclude:
            keep.append(n)
    return keep


def _space(ctx: SelectContext, names: list[str], f: SpaceFilter) -> list[str]:
    client = ctx.client
    by_name = _by_name(client, names)
    working = _open_names(names, by_name)
    if f.use_age:
        ages = _ages(ctx, working, f.source, f.timestring)
        working = [n for n in working if n in ages]
        working = sorted(working, key=lambda n: (ages[n], n), reverse=True)
    else:
        working = sorted(working, reverse=f.reverse)
    limit = f.disk_space * _GIB
    disk_usage = 0.0
    hits: set[str] = set()
    for n in working:
        try:
            disk_usage += float((by_name.get(n) or {}).get("store.size") or 0)
        except (TypeError, ValueError):
            continue
        over = (
            disk_usage > limit
            if f.threshold_behavior == "greater_than"
            else disk_usage < limit
        )
        if over:
            hits.add(n)
    return [n for n in names if n in working and ((n in hits) ^ f.exclude)]


def _empty(ctx: SelectContext, names: list[str], f: EmptyFilter) -> list[str]:
    client = ctx.client
    by_name = _by_name(client, names)
    working = _open_names(names, by_name)
    keep: list[str] = []
    for n in working:
        docs = _parse_int((by_name.get(n) or {}).get("docs.count"))
        if docs is None:
            continue
        hit = docs == 0
        if hit ^ f.exclude:
            keep.append(n)
    return keep


def _shards(ctx: SelectContext, names: list[str], f: ShardsFilter) -> list[str]:
    client = ctx.client
    if f.shard_filter_behavior == "less_than" and f.number_of_shards == 1:
        raise ValueError(
            "number_of_shards cannot be 1 when shard_filter_behavior is less_than"
        )
    op = _SHARD_OPS[f.shard_filter_behavior]
    by_name = _by_name(client, names)
    keep: list[str] = []
    for n in names:
        nshards = _parse_int((by_name.get(n) or {}).get("pri"))
        if nshards is None:
            continue
        hit = op(nshards, f.number_of_shards)
        if hit ^ f.exclude:
            keep.append(n)
    return keep


def _allocated(ctx: SelectContext, names: list[str], f: AllocatedFilter) -> list[str]:
    client = ctx.client
    settings: dict[str, Any] = {}
    for chunk in chunk_names(names):
        settings.update(_as_dict(client.indices.get_settings(index=",".join(chunk))))
    keep: list[str] = []
    for n in names:
        body = settings.get(n) or {}
        if not isinstance(body, dict):
            body = {}
        idx = (body.get("settings") or {}).get("index") or {}
        try:
            actual = idx["routing"]["allocation"][f.allocation_type][f.key]
            hit = str(actual) == str(f.value)
        except (KeyError, TypeError):
            hit = False
        if hit ^ f.exclude:
            keep.append(n)
    return keep


def _segment_counts(client: Any, names: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunk_names(names):
        for row in _as_list(client.cat.segments(index=",".join(chunk), format="json")):
            name = str(row.get("index") or "")
            if name:
                counts[name] = counts.get(name, 0) + 1
    return counts


def _forcemerged(ctx: SelectContext, names: list[str], f: ForcemergedFilter) -> list[str]:
    client = ctx.client
    by_name = _by_name(client, names)
    working = _open_names(names, by_name)
    segs = _segment_counts(client, working)
    keep: list[str] = []
    for n in working:
        row = by_name.get(n) or {}
        shards = _parse_int(row.get("pri"))
        replicas = _parse_int(row.get("rep"))
        if shards is None or replicas is None:
            continue
        expected = (shards + shards * replicas) * f.max_num_segments
        hit = segs.get(n, 0) <= expected
        if hit ^ f.exclude:
            keep.append(n)
    return keep


def _state(ctx: SelectContext, names: list[str], f: StateFilter) -> list[str]:
    if not ctx.repository:
        raise ValueError("state filter requires SelectContext.repository")
    states: dict[str, str] = {}
    for chunk in chunk_names(names):
        body = _as_dict(
            ctx.client.snapshot.get(repository=ctx.repository, snapshot=",".join(chunk))
        )
        for snap in body.get("snapshots") or []:
            if isinstance(snap, dict) and snap.get("snapshot"):
                states[str(snap["snapshot"])] = str(snap.get("state") or "")
    keep: list[str] = []
    for n in names:
        if n not in states:
            continue
        hit = states[n] == f.state
        if hit ^ f.exclude:
            keep.append(n)
    return keep


_HANDLERS: dict[type, Callable[[SelectContext, list[str], Any], list[str]]] = {
    SizeFilter: _size,
    IlmFilter: _ilm,
    OpenedFilter: _opened,
    ClosedFilter: _closed,
    CountFilter: _count,
    NoneFilter: _none,
    AgeFilter: _age,
    PeriodFilter: _period,
    SpaceFilter: _space,
    EmptyFilter: _empty,
    ShardsFilter: _shards,
    AllocatedFilter: _allocated,
    ForcemergedFilter: _forcemerged,
    StateFilter: _state,
}
