"""MCP tools wrapping Steward HTTP API (dry-run default on mutations)."""

from __future__ import annotations

from typing import Any

from es_steward.mcp_http import request_json


def _post(path: str, **body: Any) -> dict[str, Any]:
    return request_json("POST", path, json=body)


def steward_filter_preview(
    filters: list[dict[str, Any]],
    limit: int = 10,
    target: str = "index",
) -> dict[str, Any]:
    """POST ``/select/preview`` and return the JSON body.

    Args:
        filters: Filter chain (first item a selector).
        limit: Top-N names (10, 25, or 50).
        target: ``index`` or ``snapshot``.

    Returns:
        Preview JSON (``names``, ``total``, ``truncated``, ``limit``).
    """
    return _post("/select/preview", filters=filters, limit=limit, target=target)


def steward_filter_scratch_save(
    filters: list[dict[str, Any]],
    target: str = "index",
    repository: str | None = None,
) -> dict[str, Any]:
    """POST ``/select/scratch`` and return the JSON body.

    Args:
        filters: Filter chain to park.
        target: ``index`` or ``snapshot``.
        repository: Required when ``target`` is ``snapshot``.

    Returns:
        JSON including ``filter_id``.
    """
    body: dict[str, Any] = {"filters": filters, "target": target}
    if repository is not None:
        body["repository"] = repository
    return request_json("POST", "/select/scratch", json=body)


def steward_filter_scratch_get(filter_id: str) -> dict[str, Any]:
    """GET ``/select/scratch/{filter_id}``.

    Args:
        filter_id: Scratch document id.

    Returns:
        JSON including ``filters``.
    """
    return request_json("GET", f"/select/scratch/{filter_id}")


def steward_journal(limit: int = 20) -> list[dict[str, Any]]:
    """GET ``/journal/workbooks``.

    Args:
        limit: Max rows.

    Returns:
        Workbook source dicts.
    """
    return request_json("GET", "/journal/workbooks", params={"limit": limit})


def steward_show(prefix: str, size_gt: float | None = None) -> list[str]:
    """POST ``/select/preview`` for a prefix (and optional size) filter.

    Args:
        prefix: Index name prefix.
        size_gt: Optional size predicate in GiB.

    Returns:
        ``names`` from the preview body.
    """
    filters: list[dict[str, Any]] = [
        {"kind": "pattern", "pattern_kind": "prefix", "value": prefix}
    ]
    if size_gt is not None:
        filters.append({"kind": "size", "size_threshold_gb": size_gt})
    body = _post("/select/preview", filters=filters, limit=50, target="index")
    return list(body["names"])


def steward_promote(
    prefix: str, size_gt: float | None = None, dry_run: bool = True
) -> dict[str, Any]:
    """POST ``/actions/promote``.

    Args:
        prefix: Index name prefix.
        size_gt: Optional size predicate in GiB.
        dry_run: If True, do not call ES mutations.

    Returns:
        Action JSON.
    """
    return _post("/actions/promote", prefix=prefix, size_gt=size_gt, dry_run=dry_run)


def steward_redact(
    prefix: str,
    query: dict[str, Any],
    fields: list[str],
    message: str = "REDACTED",
    execute: bool = False,
) -> dict[str, Any]:
    """POST ``/actions/redact``.

    Args:
        prefix: Index name prefix.
        query: Query DSL object.
        fields: Fields to overwrite.
        message: Replacement value.
        execute: If False, dry-run (persist=False).

    Returns:
        Action JSON.
    """
    return _post(
        "/actions/redact",
        prefix=prefix,
        query=query,
        fields=fields,
        message=message,
        execute=execute,
    )


def steward_delete(prefix: str, dry_run: bool = True) -> dict[str, Any]:
    """POST ``/actions/delete``.

    Args:
        prefix: Index name prefix.
        dry_run: If True, do not call ES mutations.

    Returns:
        Action JSON ``status``, ``count``, ``dry_run``.
    """
    return _post("/actions/delete", prefix=prefix, dry_run=dry_run)


def steward_close(prefix: str, dry_run: bool = True) -> dict[str, Any]:
    """POST ``/actions/close``."""
    return _post("/actions/close", prefix=prefix, dry_run=dry_run)


def steward_open(prefix: str, dry_run: bool = True) -> dict[str, Any]:
    """POST ``/actions/open``."""
    return _post("/actions/open", prefix=prefix, dry_run=dry_run)


def steward_delete_snapshots(
    repository: str, prefix: str, dry_run: bool = True
) -> dict[str, Any]:
    """POST ``/actions/delete-snapshots``."""
    return _post(
        "/actions/delete-snapshots",
        repository=repository,
        prefix=prefix,
        dry_run=dry_run,
    )


def steward_snapshot(
    repository: str, snapshot: str, prefix: str, dry_run: bool = True
) -> dict[str, Any]:
    """POST ``/actions/snapshot``."""
    return _post(
        "/actions/snapshot",
        repository=repository,
        snapshot=snapshot,
        prefix=prefix,
        dry_run=dry_run,
    )


def steward_restore(
    repository: str, snapshot: str, dry_run: bool = True
) -> dict[str, Any]:
    """POST ``/actions/restore``."""
    return _post(
        "/actions/restore", repository=repository, snapshot=snapshot, dry_run=dry_run
    )


def steward_forcemerge(
    prefix: str, max_num_segments: int, dry_run: bool = True
) -> dict[str, Any]:
    """POST ``/actions/forcemerge``."""
    return _post(
        "/actions/forcemerge",
        prefix=prefix,
        max_num_segments=max_num_segments,
        dry_run=dry_run,
    )


def steward_allocation(
    prefix: str,
    key: str,
    value: str | None = None,
    allocation_type: str = "require",
    dry_run: bool = True,
) -> dict[str, Any]:
    """POST ``/actions/allocation``."""
    return _post(
        "/actions/allocation",
        prefix=prefix,
        key=key,
        value=value,
        allocation_type=allocation_type,
        dry_run=dry_run,
    )


def steward_replicas(prefix: str, count: int, dry_run: bool = True) -> dict[str, Any]:
    """POST ``/actions/replicas``."""
    return _post("/actions/replicas", prefix=prefix, count=count, dry_run=dry_run)


def steward_shrink(
    prefix: str,
    shrink_node: str,
    dry_run: bool = True,
    delete_after: bool = True,
) -> dict[str, Any]:
    """POST ``/actions/shrink``."""
    return _post(
        "/actions/shrink",
        prefix=prefix,
        shrink_node=shrink_node,
        dry_run=dry_run,
        delete_after=delete_after,
    )


def steward_reindex(prefix: str, dest: str, dry_run: bool = True) -> dict[str, Any]:
    """POST ``/actions/reindex``."""
    return _post("/actions/reindex", prefix=prefix, dest=dest, dry_run=dry_run)


def steward_index_settings(
    prefix: str, settings: dict[str, Any], dry_run: bool = True
) -> dict[str, Any]:
    """POST ``/actions/index-settings``."""
    return _post(
        "/actions/index-settings", prefix=prefix, settings=settings, dry_run=dry_run
    )


def steward_cluster_routing(
    routing_type: str, value: str, dry_run: bool = True
) -> dict[str, Any]:
    """POST ``/actions/cluster-routing``."""
    return _post(
        "/actions/cluster-routing",
        routing_type=routing_type,
        value=value,
        dry_run=dry_run,
    )


def steward_cold2frozen(
    prefix: str,
    dry_run: bool = True,
    delete_after: bool = True,
    transfer_aliases: bool = True,
) -> dict[str, Any]:
    """POST ``/actions/cold2frozen``."""
    return _post(
        "/actions/cold2frozen",
        prefix=prefix,
        dry_run=dry_run,
        delete_after=delete_after,
        transfer_aliases=transfer_aliases,
    )


def steward_create_index(
    name: str, dry_run: bool = True, ignore_existing: bool = False
) -> dict[str, Any]:
    """POST ``/actions/create-index``."""
    return _post(
        "/actions/create-index",
        name=name,
        dry_run=dry_run,
        ignore_existing=ignore_existing,
    )


def steward_alias(
    name: str,
    add_prefix: str | None = None,
    remove_prefix: str | None = None,
    dry_run: bool = True,
    extra_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST ``/actions/alias``."""
    return _post(
        "/actions/alias",
        name=name,
        add_prefix=add_prefix,
        remove_prefix=remove_prefix,
        dry_run=dry_run,
        extra_settings=extra_settings,
    )


def steward_rollover(
    name: str, conditions: dict[str, Any], dry_run: bool = True
) -> dict[str, Any]:
    """POST ``/actions/rollover``."""
    return _post("/actions/rollover", name=name, conditions=conditions, dry_run=dry_run)


TOOLS = (
    steward_filter_preview,
    steward_filter_scratch_save,
    steward_filter_scratch_get,
    steward_journal,
    steward_show,
    steward_promote,
    steward_redact,
    steward_delete,
    steward_close,
    steward_open,
    steward_delete_snapshots,
    steward_snapshot,
    steward_restore,
    steward_forcemerge,
    steward_allocation,
    steward_replicas,
    steward_shrink,
    steward_reindex,
    steward_index_settings,
    steward_cluster_routing,
    steward_cold2frozen,
    steward_create_index,
    steward_alias,
    steward_rollover,
)


def main() -> None:
    """Start the MCP stdio server."""
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer("es-steward")
    for fn in TOOLS:
        mcp.tool()(fn)
    mcp.run()


if __name__ == "__main__":
    main()
