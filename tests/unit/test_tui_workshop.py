"""Filter workshop and park tests (fake MCP client)."""

from __future__ import annotations

import asyncio
from typing import Any

from textual.widgets import Label, ListView, Static

from es_steward.tui_app.app import StewardApp
from es_steward.tui_app.workshop import WorkshopScreen

_PREVIEW = {"names": ["logs-1", "logs-2"], "total": 2, "truncated": False, "limit": 10}


class FakeClient:
    """Injected MCP protocol stand-in. Records calls; never spawns."""

    def __init__(self) -> None:
        self.preview_calls: list[tuple[list[dict[str, Any]], int, str]] = []
        self.save_calls: list[tuple[list[dict[str, Any]], str]] = []

    def filter_preview(
        self, filters: list[dict[str, Any]], limit: int, target: str = "index"
    ) -> dict[str, Any]:
        self.preview_calls.append((filters, limit, target))
        return dict(_PREVIEW, limit=limit)

    def filter_scratch_save(
        self, filters: list[dict[str, Any]], target: str = "index"
    ) -> dict[str, Any]:
        self.save_calls.append((filters, target))
        return {"filter_id": "11111111-1111-4111-8111-111111111111"}


def test_workshop_lists_preview_matches() -> None:
    """acceptance A3: prefix input -> PatternFilter -> preview -> ListView."""
    client = FakeClient()

    async def _go() -> None:
        app = StewardApp(client=client)
        async with app.run_test() as pilot:
            workshop = WorkshopScreen(client)
            app.push_screen(workshop)
            await pilot.pause()
            workshop.query_one("#prefix").focus()
            await pilot.press(*"logs-")
            await pilot.pause(0.5)
            matches = workshop.query_one("#matches", ListView)
            names = [
                str(
                    getattr(
                        item.query_one(Label),
                        "_content_text",
                        item.query_one(Label).render(),
                    )
                )
                for item in matches.children
            ]
            assert names == ["logs-1", "logs-2"]
            status = workshop.query_one("#workshop-status", Static).render()
            assert "total=2" in str(status)
            assert "truncated=False" in str(status)

    asyncio.run(_go())
    assert client.preview_calls
    filters, limit, target = client.preview_calls[-1]
    assert filters == [{"kind": "pattern", "pattern_kind": "prefix", "value": "logs-"}]
    assert limit == 10
    assert target == "index"


def test_park_scratch_filter_id() -> None:
    """acceptance A4: Park sets app.filter_id and shows it."""
    client = FakeClient()

    async def _go() -> None:
        app = StewardApp(client=client)
        async with app.run_test() as pilot:
            workshop = WorkshopScreen(client)
            workshop.filters = [
                {"kind": "pattern", "pattern_kind": "prefix", "value": "logs-"}
            ]
            app.push_screen(workshop)
            await pilot.pause()
            await pilot.click("#park")
            await pilot.pause(0.3)
            assert app.filter_id == "11111111-1111-4111-8111-111111111111"
            label = workshop.query_one("#park-status", Label)
            assert "11111111-1111-4111-8111-111111111111" in str(label.render())

    asyncio.run(_go())
    assert client.save_calls == [
        ([{"kind": "pattern", "pattern_kind": "prefix", "value": "logs-"}], "index")
    ]
