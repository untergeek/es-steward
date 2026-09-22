"""MCP tool dispatch tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from es_steward import mcp_server
from es_steward.mcp_server import (
    TOOLS,
    steward_alias,
    steward_allocation,
    steward_close,
    steward_cluster_routing,
    steward_cold2frozen,
    steward_create_index,
    steward_delete,
    steward_delete_snapshots,
    steward_forcemerge,
    steward_index_settings,
    steward_journal,
    steward_open,
    steward_promote,
    steward_redact,
    steward_reindex,
    steward_replicas,
    steward_restore,
    steward_rollover,
    steward_show,
    steward_shrink,
    steward_snapshot,
)

_ACTION_OK = {"status": "COMPLETED", "count": 1, "dry_run": True}

# acceptance A9: remaining POST /actions/* tools
_ACTION_CASES = [
    (steward_close, "/actions/close", {"prefix": "logs-"}),
    (steward_open, "/actions/open", {"prefix": "logs-"}),
    (
        steward_delete_snapshots,
        "/actions/delete-snapshots",
        {"repository": "repo", "prefix": "snap-"},
    ),
    (
        steward_snapshot,
        "/actions/snapshot",
        {"repository": "repo", "snapshot": "s1", "prefix": "logs-"},
    ),
    (
        steward_restore,
        "/actions/restore",
        {"repository": "repo", "snapshot": "s1"},
    ),
    (
        steward_forcemerge,
        "/actions/forcemerge",
        {"prefix": "logs-", "max_num_segments": 1},
    ),
    (
        steward_allocation,
        "/actions/allocation",
        {"prefix": "logs-", "key": "box"},
    ),
    (
        steward_replicas,
        "/actions/replicas",
        {"prefix": "logs-", "count": 1},
    ),
    (
        steward_shrink,
        "/actions/shrink",
        {"prefix": "logs-", "shrink_node": "n1"},
    ),
    (
        steward_reindex,
        "/actions/reindex",
        {"prefix": "logs-", "dest": "dest"},
    ),
    (
        steward_index_settings,
        "/actions/index-settings",
        {"prefix": "logs-", "settings": {"number_of_replicas": 0}},
    ),
    (
        steward_cluster_routing,
        "/actions/cluster-routing",
        {"routing_type": "allocation", "value": "none"},
    ),
    (steward_cold2frozen, "/actions/cold2frozen", {"prefix": "logs-"}),
    (steward_create_index, "/actions/create-index", {"name": "idx"}),
    (steward_alias, "/actions/alias", {"name": "alias", "add_prefix": "logs-"}),
    (
        steward_rollover,
        "/actions/rollover",
        {"name": "alias", "conditions": {"max_age": "1d"}},
    ),
]


def _http(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    monkeypatch.setenv("STEWARD_API_URL", "http://steward.test")
    monkeypatch.setenv("STEWARD_API_TOKEN", "secret")

    def factory() -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://steward.test",
            headers={"X-Steward-Token": "secret"},
            timeout=60.0,
        )

    monkeypatch.setattr("es_steward.mcp_http.steward_api", factory)


def test_steward_show(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200, json={"names": ["a"], "total": 1, "truncated": False, "limit": 50}
        )

    _http(monkeypatch, handler)
    assert steward_show("logs-") == ["a"]


def test_steward_journal(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=[{"workbook_id": "w"}])

    _http(monkeypatch, handler)
    assert steward_journal(limit=5)[0]["workbook_id"] == "w"


def test_steward_promote_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """acceptance A6: POST /actions/promote."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_ACTION_OK)

    _http(monkeypatch, handler)
    out = steward_promote("logs-")
    assert out == _ACTION_OK
    req = seen[0]
    assert req.method == "POST"
    assert req.url.path == "/actions/promote"
    payload = json.loads(req.read())
    assert payload["prefix"] == "logs-"
    assert payload["dry_run"] is True


def test_no_promote_dry_run_tool() -> None:
    """acceptance A6: no steward_promote_dry_run."""
    assert not hasattr(mcp_server, "steward_promote_dry_run")
    assert "steward_promote_dry_run" not in {fn.__name__ for fn in TOOLS}


def test_steward_redact_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """acceptance A7: POST /actions/redact."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_ACTION_OK)

    _http(monkeypatch, handler)
    out = steward_redact("logs-", {"term": {"a": 1}}, ["ssn"])
    assert out == _ACTION_OK
    payload = json.loads(seen[0].read())
    assert seen[0].url.path == "/actions/redact"
    assert payload["execute"] is False
    assert payload["prefix"] == "logs-"
    assert payload["query"] == {"term": {"a": 1}}
    assert payload["fields"] == ["ssn"]


def test_steward_delete_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """acceptance A8: POST /actions/delete."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_ACTION_OK)

    _http(monkeypatch, handler)
    out = steward_delete("logs-")
    assert out == _ACTION_OK
    payload = json.loads(seen[0].read())
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/actions/delete"
    assert payload == {"prefix": "logs-", "dry_run": True}


@pytest.mark.parametrize("tool,path,kwargs", _ACTION_CASES, ids=lambda x: getattr(x, "__name__", str(x)))
def test_mcp_action_tools_http(
    monkeypatch: pytest.MonkeyPatch,
    tool: Callable[..., dict[str, object]],
    path: str,
    kwargs: dict[str, object],
) -> None:
    """acceptance A9: remaining actions POST matching /actions/*."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["json"] = json.loads(request.read())
        return httpx.Response(200, json=_ACTION_OK)

    _http(monkeypatch, handler)
    out = tool(**kwargs)
    assert out == _ACTION_OK
    assert captured["method"] == "POST"
    assert captured["path"] == path
    body = captured["json"]
    assert isinstance(body, dict)
    assert set(kwargs) <= set(body)
    assert body["dry_run"] is True


def test_mcp_tool_names() -> None:
    """acceptance A10: exactly 24 tools."""
    mcp = MCPServer("es-steward")
    for fn in TOOLS:
        mcp.tool()(fn)
    names = [t.name for t in mcp._tool_manager.list_tools()]
    expected = [
        "steward_filter_preview",
        "steward_filter_scratch_save",
        "steward_filter_scratch_get",
        "steward_journal",
        "steward_show",
        "steward_promote",
        "steward_redact",
        "steward_delete",
        "steward_close",
        "steward_open",
        "steward_delete_snapshots",
        "steward_snapshot",
        "steward_restore",
        "steward_forcemerge",
        "steward_allocation",
        "steward_replicas",
        "steward_shrink",
        "steward_reindex",
        "steward_index_settings",
        "steward_cluster_routing",
        "steward_cold2frozen",
        "steward_create_index",
        "steward_alias",
        "steward_rollover",
    ]
    assert names == expected
    assert len(names) == 24


def test_mcp_server_has_no_run_imports() -> None:
    """acceptance A11: no run_* / journal_recent / NoIndicesError."""
    src = Path(mcp_server.__file__).read_text(encoding="utf-8")
    for banned in (
        "run_show",
        "run_promote",
        "run_redact",
        "journal_recent",
        "NoIndicesError",
    ):
        assert banned not in src
        assert banned not in mcp_server.__dict__


def test_show_no_indices_is_tool_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(400, text="no indices")

    _http(monkeypatch, handler)
    with pytest.raises(ToolError, match="no indices"):
        steward_show("logs-")


def test_journal_connection_error_is_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, text="down")

    _http(monkeypatch, handler)
    with pytest.raises(ToolError):
        steward_journal()


def test_show_connection_error_is_tool_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(503, text="down")

    _http(monkeypatch, handler)
    with pytest.raises(ToolError):
        steward_show("logs-")
