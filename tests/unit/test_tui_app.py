"""Textual StewardApp boot and MCP transport tests."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from mcp.client.stdio import StdioServerParameters
from textual.widgets import Footer, Header, Static

from es_steward.cli import main
from es_steward.tui_app.app import StewardApp
from es_steward.tui_app.mcp import mcp_client_target


def test_app_boots() -> None:
    """acceptance A1: Header/Footer/Static#hello; q quits."""

    async def _go() -> None:
        app = StewardApp()
        async with app.run_test() as pilot:
            assert len(app.query(Header)) == 1
            assert len(app.query(Footer)) == 1
            hello = app.query_one("#hello", Static)
            assert hello.id == "hello"
            assert app._exit is False
            await pilot.press("q")
            assert app._exit is True

    asyncio.run(_go())


def test_cli_tui_no_subcommand_starts_app() -> None:
    """acceptance A2: es-steward tui with no subcommand runs StewardApp."""
    with patch.object(StewardApp, "run") as run:
        result = CliRunner().invoke(main, ["tui"])
    assert result.exit_code == 0, result.output
    run.assert_called_once_with()


def test_mcp_client_stdio_or_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """acceptance A7: stdio parameters or HTTP URL; no subprocess."""
    monkeypatch.delenv("STEWARD_MCP_URL", raising=False)
    stdio = mcp_client_target()
    assert isinstance(stdio, StdioServerParameters)
    assert stdio.command == "es-steward-mcp"
    assert mcp_client_target(url="http://mcp.example/mcp") == "http://mcp.example/mcp"
    monkeypatch.setenv("STEWARD_MCP_URL", "http://from-env/mcp")
    assert mcp_client_target() == "http://from-env/mcp"
