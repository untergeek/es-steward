"""acceptance B — parametrize repeated run_*/CLI dry-run and empty-selection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from es_tools.cluster import SetClusterRouting
from es_tools.index import (
    CloseIndices,
    Cold2FrozenIndices,
    CreateIndices,
    DeleteIndices,
    ForceMerge,
    OpenIndices,
    PutIndexSettings,
    ReindexIndices,
    RolloverIndices,
    SetAllocation,
    SetReplicas,
    ShrinkIndices,
)
from es_tools.snapshot import CreateSnapshot, DeleteSnapshots, RestoreSnapshot

from es_steward.cli import main
from es_steward.services import (
    NoIndicesError,
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
    run_reindex,
    run_replicas,
    run_restore,
    run_rollover,
    run_shrink,
    run_snapshot,
)
from tests.unit.conftest import FakeRun


@dataclass
class _RunDry:
    suffix: str
    fn: Callable[..., Any]
    kwargs: dict[str, Any]
    action_type: type | None = None
    names: object = None
    resolve_filter: str | None = None
    resolve_called: bool | None = True
    resolve_names: list[str] = field(default_factory=lambda: ["logs-1"])
    action_attrs: dict[str, Any] = field(default_factory=dict)
    empty_kwargs: bool = False
    ctx_target: str | None = None
    ctx_repository: str | None = None


_RUN_DRY: list[_RunDry] = [
    _RunDry(
        "promote",
        run_promote,
        {"config": None, "prefix": "logs-", "size_gt": None, "dry_run": True},
        resolve_called=None,
    ),
    _RunDry(
        "delete",
        run_delete,
        {"config": None, "prefix": "logs-", "dry_run": True},
        action_type=DeleteIndices,
        names=["logs-1"],
        resolve_filter="logs-",
    ),
    _RunDry(
        "close",
        run_close,
        {"config": None, "prefix": "logs-", "dry_run": True},
        action_type=CloseIndices,
        names=["logs-1"],
        resolve_filter="logs-",
        empty_kwargs=True,
    ),
    _RunDry(
        "open",
        run_open,
        {"config": None, "prefix": "logs-", "dry_run": True},
        action_type=OpenIndices,
        names=["logs-1"],
        resolve_filter="logs-",
        empty_kwargs=True,
    ),
    _RunDry(
        "delete-snapshots",
        run_delete_snapshots,
        {"config": None, "repository": "repo", "prefix": "snap-", "dry_run": True},
        action_type=DeleteSnapshots,
        names=["snap-1"],
        resolve_filter="snap-",
        resolve_names=["snap-1"],
        action_attrs={"repository": "repo"},
        empty_kwargs=True,
        ctx_target="snapshot",
        ctx_repository="repo",
    ),
    _RunDry(
        "snapshot",
        run_snapshot,
        {
            "config": None,
            "repository": "repo",
            "snapshot": "snap-1",
            "prefix": "logs-",
            "dry_run": True,
        },
        action_type=CreateSnapshot,
        names=["logs-1"],
        resolve_filter="logs-",
        action_attrs={"repository": "repo", "snapshot": "snap-1"},
        empty_kwargs=True,
        ctx_target="index",
    ),
    _RunDry(
        "restore",
        run_restore,
        {"config": None, "repository": "repo", "snapshot": "snap-1", "dry_run": True},
        action_type=RestoreSnapshot,
        names=["*"],
        resolve_called=False,
        action_attrs={"repository": "repo", "snapshot": "snap-1"},
        empty_kwargs=True,
    ),
    _RunDry(
        "forcemerge",
        run_forcemerge,
        {"config": None, "prefix": "logs-", "max_num_segments": 1, "dry_run": True},
        action_type=ForceMerge,
        names=["logs-1"],
        resolve_filter="logs-",
        action_attrs={"max_num_segments": 1},
        empty_kwargs=True,
    ),
    _RunDry(
        "allocation",
        run_allocation,
        {
            "config": None,
            "prefix": "logs-",
            "key": "tag",
            "dry_run": True,
            "value": "hot",
            "allocation_type": "require",
        },
        action_type=SetAllocation,
        names=["logs-1"],
        resolve_filter="logs-",
        action_attrs={"key": "tag", "value": "hot", "allocation_type": "require"},
        empty_kwargs=True,
    ),
    _RunDry(
        "replicas",
        run_replicas,
        {"config": None, "prefix": "logs-", "count": 0, "dry_run": True},
        action_type=SetReplicas,
        names=["logs-1"],
        resolve_filter="logs-",
        action_attrs={"count": 0},
        empty_kwargs=True,
    ),
    _RunDry(
        "shrink",
        run_shrink,
        {
            "config": None,
            "prefix": "logs-",
            "shrink_node": "es-data-1",
            "dry_run": True,
        },
        action_type=ShrinkIndices,
        names=["logs-1"],
        resolve_filter="logs-",
        action_attrs={
            "shrink_node": "es-data-1",
            "number_of_shards": 1,
            "shrink_suffix": "-shrink",
            "delete_after": True,
        },
        empty_kwargs=True,
    ),
    _RunDry(
        "rollover",
        run_rollover,
        {
            "config": None,
            "name": "logs-write",
            "conditions": {"max_age": "7d"},
            "dry_run": True,
        },
        action_type=RolloverIndices,
        names=["logs-write"],
        resolve_called=False,
        action_attrs={"conditions": {"max_age": "7d"}, "new_index": None},
        empty_kwargs=True,
    ),
    _RunDry(
        "reindex",
        run_reindex,
        {"config": None, "prefix": "logs-", "dest": "dest-idx", "dry_run": True},
        action_type=ReindexIndices,
        names=["logs-1"],
        resolve_filter="logs-",
        action_attrs={"dest": "dest-idx", "body_extra": {}},
        empty_kwargs=True,
    ),
    _RunDry(
        "index-settings",
        run_index_settings,
        {
            "config": None,
            "prefix": "logs-",
            "settings": {"number_of_replicas": 0},
            "dry_run": True,
        },
        action_type=PutIndexSettings,
        names=["logs-1"],
        resolve_filter="logs-",
        action_attrs={"settings": {"number_of_replicas": 0}},
        empty_kwargs=True,
    ),
    _RunDry(
        "cluster-routing",
        run_cluster_routing,
        {
            "config": None,
            "routing_type": "allocation",
            "value": "primaries",
            "dry_run": True,
        },
        action_type=SetClusterRouting,
        names=["cluster"],
        resolve_called=False,
        action_attrs={"settings": {"cluster.routing.allocation.enable": "primaries"}},
        empty_kwargs=True,
    ),
    _RunDry(
        "cold2frozen",
        run_cold2frozen,
        {"config": None, "prefix": "logs-", "dry_run": True},
        action_type=Cold2FrozenIndices,
        names=["logs-1"],
        resolve_filter="logs-",
        action_attrs={
            "renamed_prefix": "partial-",
            "delete_after": True,
            "transfer_aliases": True,
        },
        empty_kwargs=True,
    ),
    _RunDry(
        "create-index",
        run_create_index,
        {
            "config": None,
            "name": "logs-000001",
            "dry_run": True,
            "ignore_existing": True,
        },
        action_type=CreateIndices,
        names=["logs-000001"],
        resolve_called=False,
        action_attrs={"ignore_existing": True, "settings": None},
        empty_kwargs=True,
    ),
]

_RUN_EMPTY: list[tuple[str, Callable[..., Any], dict[str, Any]]] = [
    (
        "promote",
        run_promote,
        {"config": None, "prefix": "logs-", "size_gt": None, "dry_run": True},
    ),
    ("delete", run_delete, {"config": None, "prefix": "logs-", "dry_run": True}),
    ("close", run_close, {"config": None, "prefix": "logs-", "dry_run": True}),
    ("open", run_open, {"config": None, "prefix": "logs-", "dry_run": True}),
    (
        "snapshot",
        run_snapshot,
        {
            "config": None,
            "repository": "repo",
            "snapshot": "snap-1",
            "prefix": "logs-",
            "dry_run": True,
        },
    ),
    (
        "forcemerge",
        run_forcemerge,
        {"config": None, "prefix": "logs-", "max_num_segments": 1, "dry_run": True},
    ),
    (
        "allocation",
        run_allocation,
        {
            "config": None,
            "prefix": "logs-",
            "key": "tag",
            "dry_run": True,
            "value": "hot",
        },
    ),
    (
        "replicas",
        run_replicas,
        {"config": None, "prefix": "logs-", "count": 1, "dry_run": True},
    ),
    (
        "shrink",
        run_shrink,
        {
            "config": None,
            "prefix": "logs-",
            "shrink_node": "es-data-1",
            "dry_run": True,
        },
    ),
    (
        "reindex",
        run_reindex,
        {"config": None, "prefix": "logs-", "dest": "dest-idx", "dry_run": True},
    ),
    (
        "index-settings",
        run_index_settings,
        {
            "config": None,
            "prefix": "logs-",
            "settings": {"number_of_replicas": 0},
            "dry_run": True,
        },
    ),
    (
        "cold2frozen",
        run_cold2frozen,
        {"config": None, "prefix": "logs-", "dry_run": True},
    ),
]


@dataclass
class _CliDry:
    suffix: str
    argv: list[str]
    target: str
    ret: object
    needle: str
    arg_eq: dict[int, object] = field(default_factory=dict)
    forbid: str | None = None
    extra: Callable[[Any], None] | None = None


def _alias_cli_extra(args: Any) -> None:
    assert args[2][0].pattern_kind == "prefix"
    assert args[2][0].value == "logstash-"
    assert args[3] == []


_CLI_DRY: list[_CliDry] = [
    _CliDry(
        "delete",
        ["delete", "--prefix", "logs-", "--dry-run"],
        "es_steward.cli.run_delete",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "logs-", 2: True},
    ),
    _CliDry(
        "close",
        ["close", "--prefix", "logs-", "--dry-run"],
        "es_steward.cli.run_close",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "logs-", 2: True},
    ),
    _CliDry(
        "open",
        ["open", "--prefix", "logs-", "--dry-run"],
        "es_steward.cli.run_open",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "logs-", 2: True},
    ),
    _CliDry(
        "delete-snapshots",
        ["delete-snapshots", "--repository", "repo", "--prefix", "snap-", "--dry-run"],
        "es_steward.cli.run_delete_snapshots",
        ("COMPLETED", 1),
        "COMPLETED 1 snapshots",
        {1: "repo", 2: "snap-", 3: True},
    ),
    _CliDry(
        "snapshot",
        [
            "snapshot",
            "--repository",
            "repo",
            "--snapshot",
            "snap-1",
            "--prefix",
            "logs-",
            "--dry-run",
        ],
        "es_steward.cli.run_snapshot",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "repo", 2: "snap-1", 3: "logs-", 4: True},
    ),
    _CliDry(
        "restore",
        ["restore", "--repository", "repo", "--snapshot", "snap-1", "--dry-run"],
        "es_steward.cli.run_restore",
        ("COMPLETED", 1),
        "COMPLETED",
        {1: "repo", 2: "snap-1", 3: True},
        forbid="snapshots",
    ),
    _CliDry(
        "forcemerge",
        ["forcemerge", "--prefix", "logs-", "--max-num-segments", "1", "--dry-run"],
        "es_steward.cli.run_forcemerge",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "logs-", 2: 1, 3: True},
    ),
    _CliDry(
        "allocation",
        [
            "allocation",
            "--prefix",
            "logs-",
            "--key",
            "tag",
            "--value",
            "hot",
            "--dry-run",
        ],
        "es_steward.cli.run_allocation",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "logs-", 2: "tag", 3: True, 4: "hot", 5: "require"},
    ),
    _CliDry(
        "replicas",
        ["replicas", "--prefix", "logs-", "--count", "0", "--dry-run"],
        "es_steward.cli.run_replicas",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "logs-", 2: 0, 3: True},
    ),
    _CliDry(
        "shrink",
        ["shrink", "--prefix", "logs-", "--shrink-node", "es-data-1", "--dry-run"],
        "es_steward.cli.run_shrink",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "logs-", 2: "es-data-1", 3: True},
    ),
    _CliDry(
        "rollover",
        [
            "rollover",
            "--name",
            "logs-write",
            "--conditions",
            '{"max_age":"7d"}',
            "--dry-run",
        ],
        "es_steward.cli.run_rollover",
        ("COMPLETED", 1, None),
        "COMPLETED 1 aliases",
        {1: "logs-write", 2: {"max_age": "7d"}, 3: True},
    ),
    _CliDry(
        "reindex",
        ["reindex", "--prefix", "logs-", "--dest", "dest-idx", "--dry-run"],
        "es_steward.cli.run_reindex",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "logs-", 2: "dest-idx", 3: True},
    ),
    _CliDry(
        "index-settings",
        [
            "index-settings",
            "--prefix",
            "logs-",
            "--settings",
            '{"number_of_replicas":0}',
            "--dry-run",
        ],
        "es_steward.cli.run_index_settings",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "logs-", 2: {"number_of_replicas": 0}, 3: True},
    ),
    _CliDry(
        "cluster-routing",
        [
            "cluster-routing",
            "--routing-type",
            "allocation",
            "--value",
            "primaries",
            "--dry-run",
        ],
        "es_steward.cli.run_cluster_routing",
        ("COMPLETED", 1),
        "COMPLETED 1 cluster",
        {1: "allocation", 2: "primaries", 3: True},
    ),
    _CliDry(
        "cold2frozen",
        ["cold2frozen", "--prefix", "logs-", "--dry-run"],
        "es_steward.cli.run_cold2frozen",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "logs-", 2: True},
    ),
    _CliDry(
        "create-index",
        ["create-index", "--name", "logs-000001", "--dry-run"],
        "es_steward.cli.run_create_index",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "logs-000001", 2: True, 3: False},
    ),
    _CliDry(
        "alias",
        ["alias", "--name", "last_week", "--add-prefix", "logstash-", "--dry-run"],
        "es_steward.cli.run_alias",
        ("COMPLETED", 1),
        "COMPLETED 1 indices",
        {1: "last_week", 4: True},
        extra=_alias_cli_extra,
    ),
]

_CLI_EMPTY: list[tuple[str, list[str], str, str]] = [
    (
        "delete",
        ["delete", "--prefix", "logs-"],
        "es_steward.cli.run_delete",
        "no indices",
    ),
    ("close", ["close", "--prefix", "logs-"], "es_steward.cli.run_close", "no indices"),
    ("open", ["open", "--prefix", "logs-"], "es_steward.cli.run_open", "no indices"),
    (
        "delete-snapshots",
        ["delete-snapshots", "--repository", "repo", "--prefix", "snap-"],
        "es_steward.cli.run_delete_snapshots",
        "no snapshots",
    ),
    (
        "snapshot",
        [
            "snapshot",
            "--repository",
            "repo",
            "--snapshot",
            "snap-1",
            "--prefix",
            "logs-",
        ],
        "es_steward.cli.run_snapshot",
        "no indices",
    ),
    (
        "forcemerge",
        ["forcemerge", "--prefix", "logs-", "--max-num-segments", "1"],
        "es_steward.cli.run_forcemerge",
        "no indices",
    ),
    (
        "allocation",
        ["allocation", "--prefix", "logs-", "--key", "tag"],
        "es_steward.cli.run_allocation",
        "no indices",
    ),
    (
        "replicas",
        ["replicas", "--prefix", "logs-", "--count", "1"],
        "es_steward.cli.run_replicas",
        "no indices",
    ),
    (
        "shrink",
        ["shrink", "--prefix", "logs-", "--shrink-node", "es-data-1"],
        "es_steward.cli.run_shrink",
        "no indices",
    ),
    (
        "reindex",
        ["reindex", "--prefix", "logs-", "--dest", "dest-idx"],
        "es_steward.cli.run_reindex",
        "no indices",
    ),
    (
        "index-settings",
        [
            "index-settings",
            "--prefix",
            "logs-",
            "--settings",
            '{"number_of_replicas":0}',
        ],
        "es_steward.cli.run_index_settings",
        "no indices",
    ),
    (
        "cold2frozen",
        ["cold2frozen", "--prefix", "logs-"],
        "es_steward.cli.run_cold2frozen",
        "no indices",
    ),
    (
        "alias",
        ["alias", "--name", "last_week", "--add-prefix", "logstash-"],
        "es_steward.cli.run_alias",
        "no indices",
    ),
]


@pytest.mark.parametrize("case", _RUN_DRY, ids=[c.suffix for c in _RUN_DRY])
def test_run_action_dry_run_persist_true(case: _RunDry) -> None:
    """acceptance B: run_* dry-run persist=True."""
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()) as get_client,
        patch(
            "es_steward.services.resolve", return_value=case.resolve_names
        ) as resolve,
        patch("es_steward.services.ActionRun", FakeRun),
    ):
        result = case.fn(**case.kwargs)
    assert result[0] == "COMPLETED"
    assert result[1] == 1
    assert FakeRun.last is not None
    assert FakeRun.last.persist is True
    assert FakeRun.last.dry_run is True
    if case.action_type is not None:
        assert isinstance(FakeRun.last.action, case.action_type)
    if case.names is not None:
        assert FakeRun.last.names == case.names
    if case.empty_kwargs:
        assert FakeRun.last.kwargs == {}
    for attr, expected in case.action_attrs.items():
        assert getattr(FakeRun.last.action, attr) == expected
    if case.resolve_called is False:
        resolve.assert_not_called()
    elif case.resolve_called is True:
        resolve.assert_called()
        if case.resolve_filter is not None:
            assert resolve.call_args.kwargs["filters"][0].value == case.resolve_filter
        if case.ctx_target is not None:
            assert resolve.call_args.kwargs["ctx"].target == case.ctx_target
        if case.ctx_repository is not None:
            assert resolve.call_args.kwargs["ctx"].repository == case.ctx_repository
    if case.suffix == "rollover":
        assert result[2] is None
        get_client.assert_called()


@pytest.mark.parametrize("suffix,fn,kwargs", _RUN_EMPTY, ids=[c[0] for c in _RUN_EMPTY])
def test_run_action_no_selection_raises(
    suffix: str, fn: Callable[..., Any], kwargs: dict[str, Any]
) -> None:
    """acceptance B: run_* empty selection raises NoIndicesError."""
    del suffix
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=[]),
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(NoIndicesError),
    ):
        fn(**kwargs)
    action_run.assert_not_called()


@pytest.mark.parametrize("case", _CLI_DRY, ids=[c.suffix for c in _CLI_DRY])
def test_cli_action_dry_run(case: _CliDry) -> None:
    """acceptance B: CLI --dry-run."""
    with patch(case.target, return_value=case.ret) as run:
        result = CliRunner().invoke(main, case.argv)
    assert result.exit_code == 0, result.output
    assert case.needle in result.output
    if case.forbid is not None:
        assert case.forbid not in result.output
    args = run.call_args.args
    for idx, expected in case.arg_eq.items():
        assert args[idx] == expected
    if case.extra is not None:
        case.extra(args)


@pytest.mark.parametrize(
    "suffix,argv,target,msg",
    _CLI_EMPTY,
    ids=[c[0] for c in _CLI_EMPTY],
)
def test_cli_action_no_selection(
    suffix: str, argv: list[str], target: str, msg: str
) -> None:
    """acceptance B: CLI NoIndicesError."""
    del suffix
    with patch(target, side_effect=NoIndicesError(msg)):
        result = CliRunner().invoke(main, argv)
    assert result.exit_code == 1
    assert msg in result.output
