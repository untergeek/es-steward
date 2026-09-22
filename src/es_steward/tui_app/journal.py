"""Journal screen: recent workbook rows."""

from __future__ import annotations

from typing import Any, Protocol

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView


class JournalClient(Protocol):
    """Injected client protocol used by the journal screen."""

    def journal(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent workbook rows."""
        ...


class JournalScreen(Screen[None]):
    """List recent workbook rows from the injected client."""

    def __init__(self, client: JournalClient, limit: int = 20) -> None:
        super().__init__()
        self.client = client
        self.limit = limit

    def compose(self) -> ComposeResult:
        """Compose the rows list."""
        with Vertical():
            yield ListView(id="journal-rows")

    def on_mount(self) -> None:
        """Load rows."""
        self.run_worker(self._load, thread=True, exclusive=True)

    def _load(self) -> None:
        rows = self.client.journal(limit=self.limit)
        self.app.call_from_thread(self._apply_rows, rows)

    def _apply_rows(self, rows: list[dict[str, Any]]) -> None:
        view = self.query_one("#journal-rows", ListView)
        view.clear()
        for row in rows:
            status = row.get("status", "")
            workbook_id = row.get("workbook_id", "")
            view.append(ListItem(Label(f"{workbook_id} {status}")))
