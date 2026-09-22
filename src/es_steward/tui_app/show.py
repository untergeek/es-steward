"""Show screen: lists names for the parked filter."""

from __future__ import annotations

from typing import Any, Protocol

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static

from es_steward.tui_app.workshop import FilterClient


class ShowClient(FilterClient, Protocol):
    """Injected client protocol used by the Show screen."""

    def filter_scratch_get(self, filter_id: str) -> dict[str, Any]:
        """Return the scratch filter body."""
        ...


class ShowScreen(Screen[None]):
    """Read-only names for ``app.filter_id`` via scratch + preview."""

    def __init__(self, client: ShowClient) -> None:
        super().__init__()
        self.client = client

    def compose(self) -> ComposeResult:
        """Compose the names list and status line."""
        with Vertical():
            yield ListView(id="show-matches")
            yield Static("", id="show-status")
            yield Label("", id="show-filter")

    def on_mount(self) -> None:
        """Load the parked filter and preview it."""
        self.run_worker(self._load, thread=True, exclusive=True)

    def _parked_id(self) -> str | None:
        return getattr(self.app, "filter_id", None)

    def _load(self) -> None:
        filter_id = self._parked_id()
        if not filter_id:
            self.app.call_from_thread(
                self.query_one("#show-status", Static).update, "no parked filter"
            )
            return
        body = self.client.filter_scratch_get(filter_id)
        filters = list(body.get("filters", []))
        preview = self.client.filter_preview(filters, 50, target="index")
        self.app.call_from_thread(self._apply_show, filter_id, preview)

    def _apply_show(self, filter_id: str, preview: dict[str, Any]) -> None:
        matches = self.query_one("#show-matches", ListView)
        matches.clear()
        for name in preview.get("names", []):
            matches.append(ListItem(Label(str(name))))
        self.query_one("#show-filter", Label).update(f"filter_id={filter_id}")
        self.query_one("#show-status", Static).update(
            f"total={preview.get('total', 0)}"
        )
