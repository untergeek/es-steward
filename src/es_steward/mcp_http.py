"""HTTP client for Steward MCP tools."""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError


def steward_api() -> httpx.Client:
    """Return an httpx client for the Steward HTTP API.

    Reads ``STEWARD_API_URL`` and ``STEWARD_API_TOKEN``. Trailing slashes are
    stripped from the URL. Sets ``X-Steward-Token`` and a 60s timeout. Sends
    no auth header.

    Returns:
        Configured ``httpx.Client``.

    Raises:
        ToolError: If either env var is missing. The message contains
            ``STEWARD_API_URL`` and ``STEWARD_API_TOKEN``.
    """
    url = os.environ.get("STEWARD_API_URL") or ""
    token = os.environ.get("STEWARD_API_TOKEN") or ""
    if not url or not token:
        raise ToolError("STEWARD_API_URL and STEWARD_API_TOKEN are required")
    return httpx.Client(
        base_url=url.rstrip("/"),
        headers={"X-Steward-Token": token},
        timeout=60.0,
    )


def request_json(method: str, path: str, **kwargs: Any) -> Any:
    """Send a request to the Steward API and return JSON.

    Args:
        method: HTTP method.
        path: Path under the API base URL.
        **kwargs: Passed to ``httpx.Client.request``.

    Returns:
        Parsed JSON body.

    Raises:
        ToolError: Missing env, or HTTP status ≥400 (message is response text).
    """
    with steward_api() as client:
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise ToolError(response.text)
        return response.json()
