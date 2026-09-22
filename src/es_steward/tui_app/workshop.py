"""Filter workshop screen (preview + park)."""

from __future__ import annotations

from typing import Any, Protocol

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, ListItem, ListView, Select, Static

LIMITS = (10, 25, 50)
DEBOUNCE_SECONDS = 0.2


class FilterClient(Protocol):
    """Injected MCP client protocol used by the workshop."""

    def filter_preview(
        self, filters: list[dict[str, Any]], limit: int, target: str = "index"
    ) -> dict[str, Any]:
        """Preview matches for filters."""
        ...

    def filter_scratch_save(
        self, filters: list[dict[str, Any]], target: str = "index"
    ) -> dict[str, Any]:
        """Persist filters and return ``{"filter_id": ...}``."""
        ...


def _prefix_filters(prefix: str) -> list[dict[str, Any]]:
    if not prefix:
        return []
    return [{"kind": "pattern", "pattern_kind": "prefix", "value": prefix}]


class WorkshopScreen(Screen[None]):
    """Prefix input, 10/25/50 limit, debounced preview, park control."""

    def __init__(self, client: FilterClient) -> None:
        super().__init__()
        self.client = client
        self.filters: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        """Compose the workshop controls."""
        with Vertical():
            yield Input(placeholder="Index prefix", id="prefix")
            yield Select(
                [(str(n), str(n)) for n in LIMITS],
                value=str(LIMITS[0]),
                allow_blank=False,
                id="limit",
            )
            yield Button("Park filter", id="park")
            yield ListView(id="matches")
            yield Static("total=0 truncated=False", id="workshop-status")
            yield Label("", id="park-status")

    def on_mount(self) -> None:
        """Run an initial preview."""
        self._schedule_preview()

    def _limit(self) -> int:
        value = self.query_one("#limit", Select).value
        return int(str(value))

    def _schedule_preview(self) -> None:
        self.set_timer(DEBOUNCE_SECONDS, self.run_preview)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Rebuild filters and re-preview after the debounce."""
        self.filters = _prefix_filters(event.value)
        self._schedule_preview()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Re-preview when the limit changes."""
        del event
        self._schedule_preview()

    def run_preview(self) -> None:
        """Preview the current filters via the injected client."""
        self.run_worker(self._preview, thread=True, exclusive=True)

    def _preview(self) -> None:
        body = self.client.filter_preview(self.filters, self._limit(), target="index")
        self.app.call_from_thread(self._show_preview, body)

    def _show_preview(self, body: dict[str, Any]) -> None:
        names = list(body.get("names", []))
        matches = self.query_one("#matches", ListView)
        matches.clear()
        for name in names:
            matches.append(ListItem(Label(str(name))))
        status = (
            f"total={body.get('total', 0)} truncated={body.get('truncated', False)}"
        )
        self.query_one("#workshop-status", Static).update(status)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Park the current filters and show the returned id."""
        if event.button.id != "park":
            return
        self.run_worker(self._park, thread=True, exclusive=True)

    def _park(self) -> None:
        body = self.client.filter_scratch_save(self.filters, target="index")
        filter_id = str(body["filter_id"])
        self.app.filter_id = filter_id
        self.app.call_from_thread(
            self.query_one("#park-status", Label).update, f"filter_id={filter_id}"
        )
