"""Textual application shell."""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static

from es_steward.tui_app.journal import JournalScreen
from es_steward.tui_app.show import ShowScreen
from es_steward.tui_app.workshop import FilterClient, WorkshopScreen


class StewardApp(App[None]):
    """Steward Textual app (Header, hello, Footer)."""

    BINDINGS: ClassVar[list[Binding]] = [Binding("q", "quit", "Quit")]
    SCREENS: ClassVar[dict[str, Any]] = {
        "workshop": WorkshopScreen,
        "show": ShowScreen,
        "journal": JournalScreen,
    }

    def __init__(self, client: FilterClient | None = None) -> None:
        super().__init__()
        self.client = client
        self.filter_id: str | None = None

    def compose(self) -> ComposeResult:
        """Compose Header, hello Static, Footer."""
        yield Header()
        yield Static("hello", id="hello")
        yield Footer()
