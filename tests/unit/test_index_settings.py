"""run_index_settings and index-settings CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from es_steward.cli import main
from es_steward.services import run_index_settings


def test_run_index_settings_empty_settings_never_hits_es() -> None:
    with (
        patch("es_steward.services.get_client") as get_client,
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="settings"),
    ):
        run_index_settings(config=None, prefix="logs-", settings={}, dry_run=True)
    get_client.assert_not_called()
    action_run.assert_not_called()


def test_run_index_settings_not_dict_never_hits_es() -> None:
    with (
        patch("es_steward.services.get_client") as get_client,
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="settings"),
    ):
        run_index_settings(
            config=None,
            prefix="logs-",
            settings=[],
            dry_run=True,  # type: ignore[arg-type]
        )
    get_client.assert_not_called()
    action_run.assert_not_called()


def test_cli_index_settings_bad_json_never_calls() -> None:
    with patch("es_steward.cli.run_index_settings") as run:
        result = CliRunner().invoke(
            main,
            ["index-settings", "--prefix", "logs-", "--settings", "{"],
        )
    assert result.exit_code != 0
    assert "invalid --settings JSON" in result.output
    run.assert_not_called()


def test_cli_index_settings_non_object_never_calls() -> None:
    with patch("es_steward.cli.run_index_settings") as run:
        result = CliRunner().invoke(
            main,
            ["index-settings", "--prefix", "logs-", "--settings", "[]"],
        )
    assert result.exit_code != 0
    assert "JSON object" in result.output
    run.assert_not_called()


def test_cli_index_settings_empty_object_never_calls() -> None:
    with patch("es_steward.cli.run_index_settings") as run:
        result = CliRunner().invoke(
            main,
            ["index-settings", "--prefix", "logs-", "--settings", "{}"],
        )
    assert result.exit_code != 0
    assert "JSON object" in result.output
    run.assert_not_called()
