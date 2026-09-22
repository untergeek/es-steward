"""HTTP client helper for Steward MCP tools."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from es_steward.mcp_http import steward_api
from es_steward.mcp_server import (
    steward_filter_preview,
    steward_filter_scratch_get,
    steward_filter_scratch_save,
    steward_journal,
    steward_show,
)

_FILTERS = [{"kind": "pattern", "pattern_kind": "prefix", "value": "logs-"}]
_PREVIEW = {
    "names": ["logs-1", "logs-2"],
    "total": 2,
    "truncated": False,
    "limit": 10,
}


def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STEWARD_API_URL", "http://steward.test")
    monkeypatch.setenv("STEWARD_API_TOKEN", "secret")


def _transport(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    _env(monkeypatch)

    def factory() -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://steward.test",
            headers={"X-Steward-Token": "secret"},
            timeout=60.0,
        )

    monkeypatch.setattr("es_steward.mcp_http.steward_api", factory)


def test_steward_api_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """acceptance A1: X-Steward-Token, 60s timeout, no Authorization."""
    monkeypatch.setenv("STEWARD_API_URL", "http://example.com/")
    monkeypatch.setenv("STEWARD_API_TOKEN", "secret")
    client = steward_api()
    try:
        assert str(client.base_url).rstrip("/") == "http://example.com"
        assert client.headers["X-Steward-Token"] == "secret"
        assert "Authorization" not in client.headers
        assert client.timeout.read == 60.0
    finally:
        client.close()


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"STEWARD_API_URL": "http://example.com"},
        {"STEWARD_API_TOKEN": "secret"},
        {"STEWARD_API_URL": "", "STEWARD_API_TOKEN": "secret"},
    ],
    ids=["both_missing", "token_missing", "url_missing", "url_empty"],
)
def test_steward_api_missing_env(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
) -> None:
    """acceptance A1: missing env raises ToolError naming both vars."""
    monkeypatch.delenv("STEWARD_API_URL", raising=False)
    monkeypatch.delenv("STEWARD_API_TOKEN", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ToolError) as exc:
        steward_api()
    msg = str(exc.value)
    assert "STEWARD_API_URL" in msg
    assert "STEWARD_API_TOKEN" in msg


def test_steward_filter_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    """acceptance A2: POST /select/preview."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["json"] = json.loads(request.content)
        if request.method != "POST":
            return httpx.Response(405, text="method not allowed")
        if request.url.path != "/select/preview":
            return httpx.Response(404, text="not found")
        return httpx.Response(200, json=_PREVIEW)

    _transport(monkeypatch, handler)
    out = steward_filter_preview(_FILTERS, limit=10, target="index")
    assert out == _PREVIEW
    assert seen["method"] == "POST"
    assert seen["path"] == "/select/preview"
    assert seen["json"] == {"filters": _FILTERS, "limit": 10, "target": "index"}

    def bad(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(400, text="empty filters")

    _transport(monkeypatch, bad)
    with pytest.raises(ToolError, match="empty filters"):
        steward_filter_preview([])


def test_steward_filter_scratch_save(monkeypatch: pytest.MonkeyPatch) -> None:
    """acceptance A3: POST /select/scratch."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/select/scratch"
        body = json.loads(request.content)
        assert body["filters"] == _FILTERS
        assert body["target"] == "index"
        return httpx.Response(201, json={"filter_id": "11111111-1111-4111-8111-111111111111"})

    _transport(monkeypatch, handler)
    out = steward_filter_scratch_save(_FILTERS, target="index")
    assert out["filter_id"] == "11111111-1111-4111-8111-111111111111"


def test_steward_filter_scratch_get(monkeypatch: pytest.MonkeyPatch) -> None:
    """acceptance A3: GET /select/scratch/{id}."""
    fid = "11111111-1111-4111-8111-111111111111"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/select/scratch/{fid}"
        return httpx.Response(
            200, json={"filter_id": fid, "target": "index", "filters": _FILTERS}
        )

    _transport(monkeypatch, handler)
    out = steward_filter_scratch_get(fid)
    assert out["filters"] == _FILTERS


def test_steward_journal_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """acceptance A4: GET /journal/workbooks?limit=."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/journal/workbooks"
        assert request.url.params["limit"] == "5"
        return httpx.Response(200, json=[{"workbook_id": "w"}])

    _transport(monkeypatch, handler)
    rows = steward_journal(limit=5)
    assert rows[0]["workbook_id"] == "w"


def test_steward_show_posts_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    """acceptance A5: steward_show POSTs /select/preview, returns names."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["json"] = json.loads(request.content)
        assert request.method == "POST"
        assert request.url.path == "/select/preview"
        return httpx.Response(
            200,
            json={
                "names": ["logs-1"],
                "total": 1,
                "truncated": False,
                "limit": 50,
            },
        )

    _transport(monkeypatch, handler)
    names = steward_show("logs-", size_gt=1.5)
    assert names == ["logs-1"]
    body = seen["json"]
    assert isinstance(body, dict)
    assert body["target"] == "index"
    assert body["limit"] == 50
    filters = body["filters"]
    assert filters[0] == {
        "kind": "pattern",
        "pattern_kind": "prefix",
        "value": "logs-",
    }
    assert filters[1] == {"kind": "size", "size_threshold_gb": 1.5}
