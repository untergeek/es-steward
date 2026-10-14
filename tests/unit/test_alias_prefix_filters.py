"""acceptance #2 #3 #6: shared alias prefix filters for CLI and API."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner
from es_mgmt.select import PatternFilter
from fastapi.testclient import TestClient

from es_steward import services
from es_steward.api import create_app
from es_steward.cli import main
from es_steward.services import alias_prefix_filters


def _pairs(filters: list) -> list[tuple[str, str]]:
    return [(item.pattern_kind, item.value) for item in filters]


def test_alias_prefix_filters_builds_add_remove_lists() -> None:
    """acceptance #2: one builder matches the former duplicate blocks."""
    add, remove = alias_prefix_filters("logs-", "old-")
    assert _pairs(add) == [("prefix", "logs-")]
    assert _pairs(remove) == [("prefix", "old-")]
    assert isinstance(add[0], PatternFilter)
    assert isinstance(remove[0], PatternFilter)

    add, remove = alias_prefix_filters("logs-", None)
    assert _pairs(add) == [("prefix", "logs-")]
    assert remove == []

    add, remove = alias_prefix_filters(None, "old-")
    assert add == []
    assert _pairs(remove) == [("prefix", "old-")]

    # falsy prefixes stay empty, same as the old `if prefix else []` blocks
    add, remove = alias_prefix_filters("", "")
    assert add == [] and remove == []


def test_cli_and_api_pass_identical_filters_to_run_alias() -> None:
    """acceptance #2 #3: record calls outside fakes, assert after run."""
    sentinel_add = [PatternFilter(pattern_kind="prefix", value="sentinel-add")]
    sentinel_remove = [PatternFilter(pattern_kind="prefix", value="sentinel-remove")]
    builder_calls: list[tuple[str | None, str | None]] = []
    recorded: list[tuple] = []

    def fake_builder(
        add_prefix: str | None, remove_prefix: str | None
    ) -> tuple[list, list]:
        builder_calls.append((add_prefix, remove_prefix))
        return sentinel_add, sentinel_remove

    def fake_run_alias(*args: object, **kwargs: object) -> tuple[str, int]:
        del kwargs
        recorded.append(args)
        return ("COMPLETED", 1)

    with (
        patch("es_steward.cli.alias_prefix_filters", fake_builder),
        patch("es_steward.api.app.alias_prefix_filters", fake_builder),
        patch("es_steward.cli.run_alias", fake_run_alias),
        patch("es_steward.api.app.run_alias", fake_run_alias),
    ):
        cli = CliRunner().invoke(
            main,
            [
                "alias",
                "--name",
                "last_week",
                "--add-prefix",
                "logs-",
                "--remove-prefix",
                "old-",
                "--dry-run",
            ],
        )
        api = TestClient(create_app(token="secret")).post(
            "/actions/alias",
            headers={"X-Steward-Token": "secret"},
            json={
                "name": "last_week",
                "add_prefix": "logs-",
                "remove_prefix": "old-",
                "dry_run": True,
            },
        )

    assert cli.exit_code == 0, cli.output
    assert api.status_code == 200
    assert builder_calls == [("logs-", "old-"), ("logs-", "old-")]
    assert len(recorded) == 2
    cli_args, api_args = recorded
    # acceptance #3: run_alias argument values stay the same shape at both sites
    assert cli_args[0] is None and api_args[0] is None
    assert cli_args[1] == api_args[1] == "last_week"
    assert cli_args[2] is sentinel_add and api_args[2] is sentinel_add
    assert cli_args[3] is sentinel_remove and api_args[3] is sentinel_remove
    assert cli_args[4] is True and api_args[4] is True
    assert cli_args[5] is None and api_args[5] is None


def test_services_docstring_names_cli_and_api_only() -> None:
    """acceptance #6: module docstring names only CLI and API."""
    doc = services.__doc__ or ""
    assert "used by CLI, TUI, API, and MCP" not in doc
    assert "CLI" in doc and "API" in doc
    assert "TUI" not in doc and "MCP" not in doc
