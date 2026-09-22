"""Show and journal screens, and Rich subcommand removal."""

from __future__ import annotations

import asyncio
from typing import Any

from click.testing import CliRunner
from textual.widgets import Label, ListView

from es_steward.cli import main
from es_steward.tui_app.app import StewardApp
from es_steward.tui_app.journal import JournalScreen
from es_steward.tui_app.show import ShowScreen

_FILTERS = [{"kind": "pattern", "pattern_kind": "prefix", "value": "logs-"}]


class FakeClient:
    """Injected MCP protocol stand-in. Records calls; never spawns."""

    def __init__(self, names: list[str] | None = None) -> None:
        self.names = names if names is not None else ["logs-1", "logs-2"]
        self.scratch_get_calls: list[str] = []
        self.preview_calls: list[tuple[list[dict[str, Any]], int, str]] = []
        self.journal_calls: list[int] = []

    def filter_scratch_get(self, filter_id: str) -> dict[str, Any]:
        self.scratch_get_calls.append(filter_id)
        return {"filter_id": filter_id, "target": "index", "filters": _FILTERS}

    def filter_preview(
        self, filters: list[dict[str, Any]], limit: int, target: str = "index"
    ) -> dict[str, Any]:
        self.preview_calls.append((filters, limit, target))
        return {
            "names": list(self.names),
            "total": len(self.names),
            "truncated": False,
            "limit": limit,
        }

    def filter_scratch_save(
        self, filters: list[dict[str, Any]], target: str = "index"
    ) -> dict[str, Any]:
        del filters, target
        return {"filter_id": "11111111-1111-4111-8111-111111111111"}

    def journal(self, limit: int = 20) -> list[dict[str, Any]]:
        self.journal_calls.append(limit)
        return [
            {"workbook_id": "wb-1", "status": "COMPLETED", "timestamp": "t1"},
            {"workbook_id": "wb-2", "status": "CANCELLED", "timestamp": "t2"},
        ]


def _texts(view: ListView) -> list[str]:
    return [str(item.query_one(Label).render()) for item in view.children]


def test_show_uses_parked_filter() -> None:
    """acceptance A5: Show reads app.filter_id then previews; no /actions/*."""
    client = FakeClient()
    fid = "11111111-1111-4111-8111-111111111111"

    async def _go() -> None:
        app = StewardApp(client=client)
        app.filter_id = fid
        async with app.run_test() as pilot:
            screen = ShowScreen(client)
            app.push_screen(screen)
            await pilot.pause(0.3)
            assert _texts(screen.query_one("#show-matches", ListView)) == [
                "logs-1",
                "logs-2",
            ]
            assert fid in str(screen.query_one("#show-filter", Label).render())
            assert "total=2" in str(screen.query_one("#show-status").render())

    asyncio.run(_go())
    assert client.scratch_get_calls == [fid]
    assert client.preview_calls == [(_FILTERS, 50, "index")]


def test_journal_screen_rows() -> None:
    """acceptance A6: journal screen lists workbook rows."""
    client = FakeClient()

    async def _go() -> None:
        app = StewardApp(client=client)
        async with app.run_test() as pilot:
            screen = JournalScreen(client)
            app.push_screen(screen)
            await pilot.pause(0.3)
            texts = _texts(screen.query_one("#journal-rows", ListView))
            assert "wb-1 COMPLETED" in texts
            assert "wb-2 CANCELLED" in texts

    asyncio.run(_go())
    assert client.journal_calls == [20]


def test_cli_tui_rich_subcommands_gone() -> None:
    """acceptance A6: tui is a leaf command; Rich subcommands removed."""
    runner = CliRunner()
    help_result = runner.invoke(main, ["tui", "--help"])
    assert help_result.exit_code == 0, help_result.output
    for gone in ("show", "promote", "redact", "journal"):
        assert f"  {gone}" not in help_result.output
    for gone in ("show", "promote", "redact", "journal"):
        result = runner.invoke(main, ["tui", gone])
        assert result.exit_code != 0, gone
