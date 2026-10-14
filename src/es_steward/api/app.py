"""FastAPI app factory for Steward."""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable
from typing import Any, Literal, Self, TypeVar
from uuid import uuid4

from elastic_transport import ApiError, TransportError
from es_mgmt.select import PatternFilter, SelectContext
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from es_steward import JOURNAL
from es_steward.select import SizeFilter, resolve
from es_steward.services import (
    NoIndicesError,
    alias_prefix_filters,
    get_steward_client,
    journal_recent,
    run_alias,
    run_allocation,
    run_close,
    run_cluster_routing,
    run_cold2frozen,
    run_create_index,
    run_delete,
    run_delete_snapshots,
    run_forcemerge,
    run_index_settings,
    run_open,
    run_promote,
    run_redact,
    run_reindex,
    run_replicas,
    run_restore,
    run_rollover,
    run_shrink,
    run_snapshot,
)


class PromoteRequest(BaseModel):
    """POST /actions/promote body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    prefix: str
    size_gt: float | None = None
    dry_run: bool = False


class PrefixDryRun(BaseModel):
    """POST /actions/delete, /close, and /open body.

    Client YAML is process-level only.
    """

    model_config = ConfigDict(extra="forbid")

    prefix: str
    dry_run: bool = False


class FilterPreviewRequest(BaseModel):
    """POST /select/preview body."""

    model_config = ConfigDict(extra="forbid")

    filters: list[dict[str, Any]] = Field(min_length=1)
    limit: Literal[10, 25, 50]
    target: Literal["index", "snapshot"]
    repository: str | None = None

    @model_validator(mode="after")
    def _snapshot_needs_repository(self) -> Self:
        if self.target == "snapshot" and not self.repository:
            raise ValueError("repository is required when target is snapshot")
        return self


class FilterPreviewResponse(BaseModel):
    """Truncated name list from ``resolve``."""

    names: list[str]
    total: int
    truncated: bool
    limit: int


class ScratchFilterRequest(BaseModel):
    """POST /select/scratch body."""

    model_config = ConfigDict(extra="forbid")

    filters: list[dict[str, Any]] = Field(min_length=1)
    target: Literal["index", "snapshot"]
    repository: str | None = None

    @model_validator(mode="after")
    def _snapshot_needs_repository(self) -> Self:
        if self.target == "snapshot" and not self.repository:
            raise ValueError("repository is required when target is snapshot")
        return self


class DeleteSnapshotsRequest(BaseModel):
    """POST /actions/delete-snapshots body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    repository: str
    prefix: str
    dry_run: bool = False


class SnapshotRequest(BaseModel):
    """POST /actions/snapshot body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    repository: str
    snapshot: str
    prefix: str
    dry_run: bool = False


class RestoreRequest(BaseModel):
    """POST /actions/restore body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    repository: str
    snapshot: str
    dry_run: bool = False


class ForceMergeRequest(BaseModel):
    """POST /actions/forcemerge body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    prefix: str
    max_num_segments: int = Field(ge=1)
    dry_run: bool = False


class AllocationRequest(BaseModel):
    """POST /actions/allocation body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    prefix: str
    key: str
    value: str | None = None
    allocation_type: Literal["require", "include", "exclude"] = "require"
    dry_run: bool = False


class ReplicasRequest(BaseModel):
    """POST /actions/replicas body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    prefix: str
    count: int = Field(ge=0)
    dry_run: bool = False


class ShrinkRequest(BaseModel):
    """POST /actions/shrink body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    prefix: str
    shrink_node: str = Field(min_length=1)
    dry_run: bool = False
    delete_after: bool = True


class RolloverRequest(BaseModel):
    """POST /actions/rollover body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    name: str
    conditions: dict[str, Any]
    dry_run: bool = False


class ReindexRequest(BaseModel):
    """POST /actions/reindex body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    prefix: str
    dest: str
    dry_run: bool = False


class IndexSettingsRequest(BaseModel):
    """POST /actions/index-settings body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    prefix: str
    settings: dict[str, Any] = Field(min_length=1)
    dry_run: bool = False


class ClusterRoutingRequest(BaseModel):
    """POST /actions/cluster-routing body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    routing_type: Literal["allocation", "rebalance"]
    value: str
    dry_run: bool = False


class Cold2FrozenRequest(BaseModel):
    """POST /actions/cold2frozen body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    prefix: str
    dry_run: bool = False
    delete_after: bool = True
    transfer_aliases: bool = True


class CreateIndexRequest(BaseModel):
    """POST /actions/create-index body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    name: str
    dry_run: bool = False
    ignore_existing: bool = False


class RedactRequest(BaseModel):
    """POST /actions/redact body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    prefix: str
    query: dict[str, Any]
    fields: list[str]
    message: str = "REDACTED"
    execute: bool = False


class AliasRequest(BaseModel):
    """POST /actions/alias body. Client YAML is process-level only."""

    model_config = ConfigDict(extra="forbid")

    name: str
    add_prefix: str | None = None
    remove_prefix: str | None = None
    dry_run: bool = False
    extra_settings: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _need_prefix(self) -> AliasRequest:
        if not self.add_prefix and not self.remove_prefix:
            raise ValueError("add_prefix or remove_prefix is required")
        return self


class ActionResponse(BaseModel):
    """Mutation result."""

    status: str
    count: int
    dry_run: bool = False


class RolloverResponse(ActionResponse):
    """Rollover mutation result. ``rolled_over`` omitted when unknown."""

    rolled_over: bool | None = None
    new_index: str | None = None


def _unavailable(_exc: BaseException) -> HTTPException:
    """Map an Elasticsearch transport failure to HTTP 503."""
    return HTTPException(status_code=503, detail="elasticsearch unavailable")


T = TypeVar("T")


def _run_action(call: Callable[[], T], *, missing: str = "no indices") -> T:
    """Map service failures to HTTP errors."""
    try:
        return call()
    except NoIndicesError as exc:
        raise HTTPException(status_code=404, detail=missing) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ApiError as exc:
        code = int(
            getattr(exc, "status_code", None)
            or getattr(getattr(exc, "meta", None), "status", None)
            or 400
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    except TransportError as exc:
        raise _unavailable(exc) from exc


def _pair(result: tuple[str, int], dry_run: bool) -> tuple[str, int, bool]:
    status, count = result
    return status, count, dry_run


def _filters_from_preview(raw: list[dict[str, Any]]) -> list[Any]:
    """Build selector/predicate objects from preview JSON.

    Args:
        raw: Filter dicts from the request body.

    Returns:
        Objects ``resolve`` can inspect via ``kind``.
    """
    built: list[Any] = []
    for item in raw:
        kind = item.get("kind")
        if kind == "pattern":
            built.append(
                PatternFilter(pattern_kind=item["pattern_kind"], value=item["value"])
            )
        elif kind == "size":
            built.append(SizeFilter(size_threshold_gb=item["size_threshold_gb"]))
        else:
            raise ValueError("unknown filter kind")
    return built


def create_app(*, token: str | None = None, config: str | None = None) -> FastAPI:
    """Build the Steward API.

    Args:
        token: Shared secret for ``X-Steward-Token``. Defaults to
            ``STEWARD_API_TOKEN``. Empty token rejects authenticated routes.
        config: Process-level client YAML path. Request bodies cannot override
            this (no per-request ``config`` field).

    Returns:
        FastAPI application.
    """
    expected = token if token is not None else os.environ.get("STEWARD_API_TOKEN", "")
    app = FastAPI(title="es-steward")

    def require_token(x_steward_token: str | None = Header(default=None)) -> None:
        if not expected:
            raise HTTPException(status_code=401, detail="invalid token")
        provided = x_steward_token if x_steward_token is not None else ""
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="invalid token")

    @app.get("/")
    def health() -> dict[str, Any]:
        return {"ok": True, "journal": JOURNAL}

    @app.get("/journal/workbooks")
    def workbooks(
        limit: int = 20,
        _: None = Depends(require_token),
    ) -> list[dict[str, Any]]:
        try:
            return journal_recent(config, limit=limit)
        except TransportError as exc:
            raise _unavailable(exc) from exc

    @app.post("/select/preview", response_model=FilterPreviewResponse)
    def preview_filters(
        body: FilterPreviewRequest,
        _: None = Depends(require_token),
    ) -> FilterPreviewResponse:
        def _go() -> list[str]:
            filters = _filters_from_preview(body.filters)
            client = get_steward_client(config)
            ctx = SelectContext(
                client=client,
                target=body.target,
                repository=body.repository,
                protect=frozenset({JOURNAL}),
            )
            return resolve(ctx, filters)

        names = _run_action(_go)
        total = len(names)
        sliced = names[: body.limit]
        return FilterPreviewResponse(
            names=sliced,
            total=total,
            truncated=total > body.limit,
            limit=body.limit,
        )

    @app.post("/select/scratch", status_code=201)
    def create_scratch(
        body: ScratchFilterRequest,
        _: None = Depends(require_token),
    ) -> dict[str, str]:
        filter_id = str(uuid4())
        source: dict[str, Any] = {
            "filter_id": filter_id,
            "target": body.target,
            "filters": body.filters,
        }
        if body.repository:
            source["repository"] = body.repository

        def _go() -> None:
            client = get_steward_client(config)
            client.index(index=JOURNAL, id=filter_id, document=source)

        _run_action(_go)
        return {"filter_id": filter_id}

    @app.get("/select/scratch/{filter_id}")
    def read_scratch(
        filter_id: str,
        _: None = Depends(require_token),
    ) -> dict[str, Any]:
        def _go() -> dict[str, Any]:
            client = get_steward_client(config)
            raw = client.get(index=JOURNAL, id=filter_id)
            body = raw if isinstance(raw, dict) else getattr(raw, "body", raw)
            if not isinstance(body, dict):
                raise HTTPException(status_code=404, detail="not found")
            src = body.get("_source")
            if not isinstance(src, dict):
                raise HTTPException(status_code=404, detail="not found")
            return src

        src = _run_action(_go)
        if "filter_id" not in src:
            raise HTTPException(status_code=404, detail="not found")
        return {
            "filter_id": src["filter_id"],
            "target": src["target"],
            "filters": src["filters"],
        }

    def _alias_run(body: AliasRequest) -> tuple[str, int, bool]:
        add_filters, remove_filters = alias_prefix_filters(
            body.add_prefix, body.remove_prefix
        )
        status, count = run_alias(
            config,
            body.name,
            add_filters,
            remove_filters,
            body.dry_run,
            body.extra_settings,
        )
        return status, count, body.dry_run

    routes: list[
        tuple[
            str,
            type[BaseModel],
            Callable[[Any], tuple[str, int, bool]],
            str,
            str,
        ]
    ] = [
        (
            "/actions/promote",
            PromoteRequest,
            lambda b: _pair(
                run_promote(config, b.prefix, b.size_gt, b.dry_run), b.dry_run
            ),
            "promote_action",
            "no indices",
        ),
        (
            "/actions/delete",
            PrefixDryRun,
            lambda b: _pair(run_delete(config, b.prefix, b.dry_run), b.dry_run),
            "delete_action",
            "no indices",
        ),
        (
            "/actions/close",
            PrefixDryRun,
            lambda b: _pair(run_close(config, b.prefix, b.dry_run), b.dry_run),
            "close_action",
            "no indices",
        ),
        (
            "/actions/open",
            PrefixDryRun,
            lambda b: _pair(run_open(config, b.prefix, b.dry_run), b.dry_run),
            "open_action",
            "no indices",
        ),
        (
            "/actions/delete-snapshots",
            DeleteSnapshotsRequest,
            lambda b: _pair(
                run_delete_snapshots(config, b.repository, b.prefix, b.dry_run),
                b.dry_run,
            ),
            "delete_snapshots_action",
            "no snapshots",
        ),
        (
            "/actions/snapshot",
            SnapshotRequest,
            lambda b: _pair(
                run_snapshot(
                    config, b.repository, b.snapshot, b.prefix, b.dry_run
                ),
                b.dry_run,
            ),
            "snapshot_action",
            "no indices",
        ),
        (
            "/actions/restore",
            RestoreRequest,
            lambda b: _pair(
                run_restore(config, b.repository, b.snapshot, b.dry_run),
                b.dry_run,
            ),
            "restore_action",
            "no indices",
        ),
        (
            "/actions/forcemerge",
            ForceMergeRequest,
            lambda b: _pair(
                run_forcemerge(config, b.prefix, b.max_num_segments, b.dry_run),
                b.dry_run,
            ),
            "forcemerge_action",
            "no indices",
        ),
        (
            "/actions/allocation",
            AllocationRequest,
            lambda b: _pair(
                run_allocation(
                    config,
                    b.prefix,
                    b.key,
                    b.dry_run,
                    b.value,
                    b.allocation_type,
                ),
                b.dry_run,
            ),
            "allocation_action",
            "no indices",
        ),
        (
            "/actions/replicas",
            ReplicasRequest,
            lambda b: _pair(
                run_replicas(config, b.prefix, b.count, b.dry_run), b.dry_run
            ),
            "replicas_action",
            "no indices",
        ),
        (
            "/actions/shrink",
            ShrinkRequest,
            lambda b: _pair(
                run_shrink(
                    config,
                    b.prefix,
                    b.shrink_node,
                    b.dry_run,
                    delete_after=b.delete_after,
                ),
                b.dry_run,
            ),
            "shrink_action",
            "no indices",
        ),
        (
            "/actions/reindex",
            ReindexRequest,
            lambda b: _pair(
                run_reindex(config, b.prefix, b.dest, b.dry_run), b.dry_run
            ),
            "reindex_action",
            "no indices",
        ),
        (
            "/actions/index-settings",
            IndexSettingsRequest,
            lambda b: _pair(
                run_index_settings(config, b.prefix, b.settings, b.dry_run),
                b.dry_run,
            ),
            "index_settings_action",
            "no indices",
        ),
        (
            "/actions/cluster-routing",
            ClusterRoutingRequest,
            lambda b: _pair(
                run_cluster_routing(config, b.routing_type, b.value, b.dry_run),
                b.dry_run,
            ),
            "cluster_routing_action",
            "no indices",
        ),
        (
            "/actions/cold2frozen",
            Cold2FrozenRequest,
            lambda b: _pair(
                run_cold2frozen(
                    config,
                    b.prefix,
                    b.dry_run,
                    delete_after=b.delete_after,
                    transfer_aliases=b.transfer_aliases,
                ),
                b.dry_run,
            ),
            "cold2frozen_action",
            "no indices",
        ),
        (
            "/actions/create-index",
            CreateIndexRequest,
            lambda b: _pair(
                run_create_index(config, b.name, b.dry_run, b.ignore_existing),
                b.dry_run,
            ),
            "create_index_action",
            "no indices",
        ),
        (
            "/actions/redact",
            RedactRequest,
            lambda b: run_redact(
                config, b.prefix, b.query, b.fields, b.message, b.execute
            ),
            "redact_action",
            "no indices",
        ),
        (
            "/actions/alias",
            AliasRequest,
            _alias_run,
            "alias_action",
            "no indices",
        ),
    ]

    def _register(
        path: str,
        model: type[BaseModel],
        runner: Callable[[Any], tuple[str, int, bool]],
        name: str,
        missing: str,
    ) -> None:
        def endpoint(
            body: BaseModel,
            _: None = Depends(require_token),
        ) -> ActionResponse:
            status, count, dry_run = _run_action(
                lambda: runner(body), missing=missing
            )
            return ActionResponse(status=status, count=count, dry_run=dry_run)

        endpoint.__name__ = name
        # Load-bearing: FastAPI reads the body model from __annotations__ at registration; reuse/wrap of one function object would drop per-route validation.
        endpoint.__annotations__ = {
            "body": model,
            "_": None,
            "return": ActionResponse,
        }
        app.post(path, response_model=ActionResponse)(endpoint)

    assert len(routes) == 18
    for path, model, runner, name, missing in routes:
        _register(path, model, runner, name, missing)

    @app.post(
        "/actions/rollover",
        response_model=RolloverResponse,
        response_model_exclude_none=True,
    )
    def rollover_action(
        body: RolloverRequest,
        _: None = Depends(require_token),
    ) -> RolloverResponse:
        status, count, raw = _run_action(
            lambda: run_rollover(config, body.name, body.conditions, body.dry_run)
        )
        extra: dict[str, Any] = {}
        if raw is not None:
            extra["rolled_over"] = bool(raw["rolled_over"])
            if "new_index" in raw:
                extra["new_index"] = raw["new_index"]
        return RolloverResponse(
            status=status, count=count, dry_run=body.dry_run, **extra
        )

    return app


app = create_app()
