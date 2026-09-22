"""Shared Steward operations used by CLI, TUI, API, and MCP."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from es_tools.checkpoint.action_run import ActionRun
from es_tools.checkpoint.event_bus import EventBus
from es_tools.client.cli import get_client
from es_tools.cluster import SetClusterRouting
from es_tools.index import (
    CloseIndices,
    Cold2FrozenIndices,
    CreateIndices,
    DeleteIndices,
    ForceMerge,
    OpenIndices,
    PromoteIlm,
    PutIndexSettings,
    ReindexIndices,
    RolloverIndices,
    SetAllocation,
    SetReplicas,
    ShrinkIndices,
    UpdateAliases,
)
from es_tools.redact import RedactFields
from es_tools.select import PatternFilter, SelectContext
from es_tools.snapshot import CreateSnapshot, DeleteSnapshots, RestoreSnapshot

from es_steward import JOURNAL
from es_steward.select import IlmFilter, OpenedFilter, SizeFilter, resolve


class NoIndicesError(Exception):
    """Selection resolved to an empty name list."""


def get_steward_client(config: str | None = None) -> Any:
    """Build an Elasticsearch client from optional YAML.

    Args:
        config: Path to client YAML, or None for env/defaults.

    Returns:
        Elasticsearch client.
    """
    return get_client(configfile=config)


def _filters(prefix: str, size_gt: float | None, *, keep_managed: bool) -> list:
    filters: list = [PatternFilter(pattern_kind="prefix", value=prefix)]
    if size_gt is not None:
        filters.append(SizeFilter(size_threshold_gb=size_gt))
    if keep_managed:
        filters.append(IlmFilter(exclude=False))
    return filters


def _context(client: Any) -> SelectContext:
    return SelectContext(client=client, target="index", protect=frozenset({JOURNAL}))


def run_show(
    config: str | None,
    prefix: str,
    size_gt: float | None,
) -> list[str]:
    """Resolve index names (prefix + optional size). Unmanaged-only.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        size_gt: Keep primary size greater than this GiB, or None.

    Returns:
        Resolved index names.
    """
    client = get_steward_client(config)
    return resolve(ctx=_context(client), filters=_filters(prefix, size_gt, keep_managed=False))


def run_promote(
    config: str | None,
    prefix: str,
    size_gt: float | None,
    dry_run: bool,
) -> tuple[str, int]:
    """Advance matching ILM-managed indices one phase.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        size_gt: Optional size predicate (GiB).
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        NoIndicesError: Nothing matched.
    """
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, size_gt, keep_managed=True))
    if not names:
        raise NoIndicesError("no indices")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        PromoteIlm(), names
    )
    return wb.status, len(names)


def run_delete(
    config: str | None,
    prefix: str,
    dry_run: bool,
) -> tuple[str, int]:
    """Delete matching indices.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        NoIndicesError: Nothing matched.
    """
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, None, keep_managed=False))
    if not names:
        raise NoIndicesError("no indices")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        DeleteIndices(), names
    )
    return wb.status, len(names)


def run_close(
    config: str | None,
    prefix: str,
    dry_run: bool,
) -> tuple[str, int]:
    """Close matching indices.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        NoIndicesError: Nothing matched.
    """
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, None, keep_managed=False))
    if not names:
        raise NoIndicesError("no indices")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        CloseIndices(), names
    )
    return wb.status, len(names)


def run_open(
    config: str | None,
    prefix: str,
    dry_run: bool,
) -> tuple[str, int]:
    """Open matching indices.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        NoIndicesError: Nothing matched.
    """
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, None, keep_managed=False))
    if not names:
        raise NoIndicesError("no indices")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        OpenIndices(), names
    )
    return wb.status, len(names)


def run_forcemerge(
    config: str | None,
    prefix: str,
    max_num_segments: int,
    dry_run: bool,
) -> tuple[str, int]:
    """Forcemerge matching indices.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        max_num_segments: Target segment count per shard.
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        NoIndicesError: Nothing matched.
        ValueError: Invalid ``max_num_segments`` (if the ctor raises).
    """
    action = ForceMerge(max_num_segments)
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, None, keep_managed=False))
    if not names:
        raise NoIndicesError("no indices")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        action, names
    )
    return wb.status, len(names)


def run_allocation(
    config: str | None,
    prefix: str,
    key: str,
    dry_run: bool,
    value: str | None = None,
    allocation_type: str = "require",
) -> tuple[str, int]:
    """Set allocation filters on matching indices.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        key: Allocation attribute key.
        dry_run: If True, do not call ES mutations. persist is always True.
        value: Allocation attribute value.
        allocation_type: ``require``, ``include``, or ``exclude``.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        NoIndicesError: Nothing matched.
        ValueError: Invalid key or allocation_type.
    """
    action = SetAllocation(key, value=value, allocation_type=allocation_type)
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, None, keep_managed=False))
    if not names:
        raise NoIndicesError("no indices")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        action, names
    )
    return wb.status, len(names)


def run_replicas(
    config: str | None,
    prefix: str,
    count: int,
    dry_run: bool,
) -> tuple[str, int]:
    """Set replica count on matching indices.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        count: Replica count (``>= 0``).
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        NoIndicesError: Nothing matched.
        ValueError: ``count`` is not an int ``>= 0``.
    """
    action = SetReplicas(count)
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, None, keep_managed=False))
    if not names:
        raise NoIndicesError("no indices")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        action, names
    )
    return wb.status, len(names)


def run_shrink(
    config: str | None,
    prefix: str,
    shrink_node: str,
    dry_run: bool,
    delete_after: bool = True,
) -> tuple[str, int]:
    """Shrink matching indices onto one node.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        shrink_node: Node name that will hold every shard before shrink.
        dry_run: If True, do not call ES mutations. persist is always True.
        delete_after: Delete the source index after shrink (library default).

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        NoIndicesError: Nothing matched.
        ValueError: Empty ``shrink_node``.
    """
    action = ShrinkIndices(shrink_node, delete_after=delete_after)
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, None, keep_managed=False))
    if not names:
        raise NoIndicesError("no indices")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        action, names
    )
    return wb.status, len(names)


def _rollover_raw(results: list[Any]) -> dict[str, Any] | None:
    """First ExecuteResult snapshot whose raw has rolled_over, else None."""
    for row in results:
        if not isinstance(row, dict):
            continue
        raw = row.get("raw")
        if isinstance(raw, dict) and "rolled_over" in raw:
            return raw
    return None


def run_rollover(
    config: str | None,
    name: str,
    conditions: dict[str, Any],
    dry_run: bool,
) -> tuple[str, int, dict[str, Any] | None]:
    """Rollover one alias if conditions are met.

    Args:
        config: Client YAML path.
        name: Alias name.
        conditions: Rollover conditions mapping (may be empty).
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count, rollover_raw)``. ``rollover_raw`` is
        the first result ``raw`` mapping that contains ``rolled_over``, or
        ``None`` (dry-run / empty results).

    Raises:
        ValueError: Empty alias name, or ``conditions`` is not a dict.
    """
    if not name:
        raise ValueError("name is required")
    if not isinstance(conditions, dict):
        raise ValueError("conditions must be a mapping")  # noqa: TRY004
    client = get_steward_client(config)
    names = [name]
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        RolloverIndices(conditions), names
    )
    return wb.status, len(names), _rollover_raw(list(getattr(wb, "results", []) or []))


def run_reindex(
    config: str | None,
    prefix: str,
    dest: str,
    dry_run: bool,
) -> tuple[str, int]:
    """Reindex matching sources into dest.

    Args:
        config: Client YAML path.
        prefix: Source index name prefix.
        dest: Destination index name.
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        NoIndicesError: Nothing matched.
        ValueError: Empty dest, or dest is in the resolved source set.
    """
    if not dest:
        raise ValueError("dest must be a non-empty string")
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, None, keep_managed=False))
    if not names:
        raise NoIndicesError("no indices")
    if dest in names:
        raise ValueError("dest must not be in the source set")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        ReindexIndices(dest), names
    )
    return wb.status, len(names)


def run_index_settings(
    config: str | None,
    prefix: str,
    settings: dict[str, Any],
    dry_run: bool,
) -> tuple[str, int]:
    """Put index settings on matching indices.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        settings: Settings body.
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        NoIndicesError: Nothing matched.
        ValueError: ``settings`` is not a mapping, or is empty.
    """
    if not isinstance(settings, dict):
        raise ValueError("settings must be a mapping")  # noqa: TRY004
    if not settings:
        raise ValueError("settings must be a non-empty dict")
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, None, keep_managed=False))
    if not names:
        raise NoIndicesError("no indices")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        PutIndexSettings(settings), names
    )
    return wb.status, len(names)


def run_cluster_routing(
    config: str | None,
    routing_type: str,
    value: str,
    dry_run: bool,
) -> tuple[str, int]:
    """Set transient cluster routing enable.

    Args:
        config: Client YAML path.
        routing_type: ``allocation`` or ``rebalance``.
        value: Type-specific enable value.
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)`` (count is 1).

    Raises:
        ValueError: Invalid routing_type or value.
    """
    action = SetClusterRouting(routing_type, "enable", value)
    client = get_steward_client(config)
    names = ["cluster"]
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        action, names
    )
    return wb.status, len(names)


def run_cold2frozen(
    config: str | None,
    prefix: str,
    dry_run: bool,
    delete_after: bool = True,
    transfer_aliases: bool = True,
) -> tuple[str, int]:
    """Mount matching cold indices as frozen partial mounts.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        dry_run: If True, do not call ES mutations. persist is always True.
        delete_after: Delete the source index after mount (library default).
        transfer_aliases: Move aliases from source to the mount.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        NoIndicesError: Nothing matched.
    """
    action = Cold2FrozenIndices(
        delete_after=delete_after, transfer_aliases=transfer_aliases
    )
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, None, keep_managed=False))
    if not names:
        raise NoIndicesError("no indices")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        action, names
    )
    return wb.status, len(names)


def run_create_index(
    config: str | None,
    name: str,
    dry_run: bool,
    ignore_existing: bool = False,
) -> tuple[str, int]:
    """Create one index.

    Args:
        config: Client YAML path.
        name: Index name to create.
        dry_run: If True, do not call ES mutations. persist is always True.
        ignore_existing: If True, treat already-exists as success.

    Returns:
        ``(workbook.status, name_count)`` (count is 1).

    Raises:
        ValueError: Empty name.
    """
    if not name:
        raise ValueError("name is required")
    client = get_steward_client(config)
    names = [name]
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        CreateIndices(ignore_existing=ignore_existing), names
    )
    return wb.status, len(names)


def run_delete_snapshots(
    config: str | None,
    repository: str,
    prefix: str,
    dry_run: bool,
) -> tuple[str, int]:
    """Delete matching snapshots.

    Args:
        config: Client YAML path.
        repository: Snapshot repository.
        prefix: Snapshot name prefix.
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        ValueError: Empty repository.
        NoIndicesError: Nothing matched.
    """
    if not repository:
        raise ValueError("repository is required")
    client = get_steward_client(config)
    ctx = SelectContext(
        client=client,
        target="snapshot",
        repository=repository,
        protect=frozenset({JOURNAL}),
    )
    names = resolve(ctx=ctx, filters=[PatternFilter(pattern_kind="prefix", value=prefix)])
    if not names:
        raise NoIndicesError("no snapshots")
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        DeleteSnapshots(repository), names
    )
    return wb.status, len(names)


def run_snapshot(
    config: str | None,
    repository: str,
    snapshot: str,
    prefix: str,
    dry_run: bool,
) -> tuple[str, int]:
    """Create one snapshot of matching indices.

    Args:
        config: Client YAML path.
        repository: Snapshot repository.
        snapshot: Snapshot name (literal).
        prefix: Index name prefix.
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)``.

    Raises:
        ValueError: Empty repository or snapshot.
        NoIndicesError: Nothing matched.
    """
    if not repository or not snapshot:
        raise ValueError("repository and snapshot are required")
    client = get_steward_client(config)
    names = resolve(ctx=_context(client), filters=_filters(prefix, None, keep_managed=False))
    if not names:
        raise NoIndicesError("no indices")
    action = CreateSnapshot(repository, snapshot)
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        action, names
    )
    return wb.status, len(names)


def run_restore(
    config: str | None,
    repository: str,
    snapshot: str,
    dry_run: bool,
) -> tuple[str, int]:
    """Restore one snapshot (all indices).

    Args:
        config: Client YAML path.
        repository: Snapshot repository.
        snapshot: Snapshot name (literal).
        dry_run: If True, do not call ES mutations. persist is always True.

    Returns:
        ``(workbook.status, name_count)`` where count is 1 (the ``*`` unit).

    Raises:
        ValueError: Empty repository or snapshot.
    """
    if not repository or not snapshot:
        raise ValueError("repository and snapshot are required")
    client = get_steward_client(config)
    names = ["*"]
    action = RestoreSnapshot(repository, snapshot)
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        action, names
    )
    return wb.status, len(names)


def run_alias(
    config: str | None,
    alias: str,
    add_filters: list,
    remove_filters: list,
    dry_run: bool,
    extra_settings: dict[str, Any] | None = None,
) -> tuple[str, int]:
    """Add and/or remove resolved indices on one alias.

    Args:
        config: Client YAML path.
        alias: Literal alias name.
        add_filters: Selectors/predicates for indices to add (may be empty).
        remove_filters: Selectors/predicates for indices to remove (may be empty).
        dry_run: If True, do not call ES mutations. persist is always True.
        extra_settings: Merged into each add action only.

    Returns:
        ``(workbook.status, name_count)`` where ``name_count`` is
        ``len(add) + len(remove)`` after resolve.

    Raises:
        ValueError: Empty alias, or both filter lists empty before resolve.
        NoIndicesError: Both sides resolve to no names.
    """
    if not alias:
        raise ValueError("alias must be a non-empty string")
    add_filters = list(add_filters or [])
    remove_filters = list(remove_filters or [])
    if not add_filters and not remove_filters:
        raise ValueError("add and remove cannot both be empty")
    client = get_steward_client(config)
    ctx = _context(client)
    add_names = resolve(ctx=ctx, filters=add_filters) if add_filters else []
    remove_names = resolve(ctx=ctx, filters=remove_filters) if remove_filters else []
    if not add_names and not remove_names:
        raise NoIndicesError("no indices")
    action = UpdateAliases(
        alias,
        add=add_names,
        remove=remove_names,
        extra_settings=extra_settings or {},
    )
    wb = ActionRun(client, EventBus(), JOURNAL, persist=True, dry_run=dry_run).run(
        action, action.names
    )
    return wb.status, len(add_names) + len(remove_names)


def run_redact(
    config: str | None,
    prefix: str,
    query: dict[str, Any],
    fields: list[str],
    message: str,
    execute: bool,
) -> tuple[str, int, bool]:
    """Overwrite matching fields on open indices.

    Args:
        config: Client YAML path.
        prefix: Index name prefix.
        query: Query DSL.
        fields: Dotted field names.
        message: Replacement value.
        execute: If True, mutate and journal. Default path is dry-run.

    Returns:
        ``(workbook.status, name_count, dry_run)``.

    Raises:
        NoIndicesError: Nothing matched.
        ValueError: Empty query.
    """
    if not query:
        raise ValueError("query must be a non-empty mapping")
    client = get_steward_client(config)
    names = resolve(
        ctx=_context(client),
        filters=[PatternFilter(pattern_kind="prefix", value=prefix), OpenedFilter()],
    )
    if not names:
        raise NoIndicesError("no indices")
    dry_run = not execute
    wb = ActionRun(
        client, EventBus(), JOURNAL, persist=execute, dry_run=dry_run
    ).run(RedactFields(query=query, fields=list(fields), message=message), names)
    return wb.status, len(names), dry_run


def _timestamp_sort_key(row: dict[str, Any]) -> datetime:
    """Parse a journal row timestamp for newest-first ordering.

    Args:
        row: Journal ``_source`` document.

    Returns:
        Timezone-aware datetime. Unparseable values sort as oldest.
    """
    raw = row.get("@timestamp", row.get("timestamp"))
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            dt = datetime.min.replace(tzinfo=UTC)
    else:
        dt = datetime.min.replace(tzinfo=UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def journal_recent(config: str | None, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent workbook documents from the tracking index.

    Args:
        config: Client YAML path.
        limit: Max rows (newest first).

    Returns:
        Source dicts with at least ``workbook_id`` / ``status`` / ``timestamp``
        when present, ordered newest first. Prefers ``@timestamp`` (date-mapped
        by ``es_tools.checkpoint``) then ``timestamp``. Re-sorts the returned
        page in Python so mixed fractional-second strings cannot invert order.
    """
    client = get_steward_client(config)
    raw = client.search(
        index=JOURNAL,
        query={"exists": {"field": "workbook_id"}},
        size=limit,
        sort=[{"@timestamp": {"order": "desc", "unmapped_type": "date"}}],
    )
    body: Any = raw if isinstance(raw, dict) else getattr(raw, "body", raw)
    if not isinstance(body, dict):
        return []
    hits = (body.get("hits") or {}).get("hits") or []
    rows: list[dict[str, Any]] = []
    for hit in hits:
        if isinstance(hit, dict) and isinstance(hit.get("_source"), dict):
            rows.append(hit["_source"])
    rows.sort(key=_timestamp_sort_key, reverse=True)
    return rows
