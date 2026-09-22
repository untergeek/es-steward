"""MCP client construction for the Textual app."""

from __future__ import annotations

import os

from mcp.client.stdio import StdioServerParameters


def mcp_client_target(*, url: str | None = None) -> StdioServerParameters | str:
    """Return stdio parameters or an HTTP MCP URL.

    Screens depend on an injected client protocol, not this transport.

    Args:
        url: Streamable HTTP MCP URL. If omitted, ``STEWARD_MCP_URL`` is
            used when set; otherwise stdio ``es-steward-mcp``.

    Returns:
        ``StdioServerParameters`` for stdio, or a URL string for HTTP.
    """
    chosen = url if url is not None else (os.environ.get("STEWARD_MCP_URL") or "")
    if chosen:
        return chosen
    return StdioServerParameters(command="es-steward-mcp")
