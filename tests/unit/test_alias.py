"""run_alias and alias CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from es_mgmt.select import PatternFilter

from es_steward.cli import main
from es_steward.services import NoIndicesError, run_alias
from tests.unit.conftest import FakeRun


def _prefix(value: str) -> list[PatternFilter]:
    return [PatternFilter(pattern_kind="prefix", value=value)]


def test_run_alias_add_only() -> None:
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=["logs-1"]) as resolve,
        patch("es_steward.services.ActionRun", FakeRun),
    ):
        status, count = run_alias(
            None, "last_week", _prefix("logstash-"), [], dry_run=True
        )
    assert status == "COMPLETED"
    assert count == 1
    assert resolve.call_count == 1
    action = FakeRun.last.action
    assert action.alias == "last_week"
    assert action.add == ["logs-1"]
    assert action.remove == []
    assert FakeRun.last.persist is True
    assert FakeRun.last.dry_run is True
    assert FakeRun.last.names == action.names


def test_run_alias_remove_only() -> None:
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=["old-1"]) as resolve,
        patch("es_steward.services.ActionRun", FakeRun),
    ):
        _status, count = run_alias(None, "last_week", [], _prefix("old-"), dry_run=True)
    assert count == 1
    assert resolve.call_count == 1
    action = FakeRun.last.action
    assert action.add == []
    assert action.remove == ["old-1"]


def test_run_alias_both_sides() -> None:

    def _res(*, ctx: object, filters: list) -> list[str]:
        del ctx
        val = filters[0].value
        return ["add-1"] if val == "add-" else ["rm-1"]

    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", side_effect=_res),
        patch("es_steward.services.ActionRun", FakeRun),
    ):
        _status, count = run_alias(
            None, "last_week", _prefix("add-"), _prefix("rm-"), dry_run=False
        )
    assert count == 2
    action = FakeRun.last.action
    assert action.add == ["add-1"]
    assert action.remove == ["rm-1"]
    assert FakeRun.last.dry_run is False


def test_run_alias_extra_settings() -> None:
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=["logs-1"]),
        patch("es_steward.services.ActionRun", FakeRun),
    ):
        run_alias(
            None,
            "last_week",
            _prefix("logstash-"),
            [],
            dry_run=True,
            extra_settings={"is_write_index": True},
        )
    assert FakeRun.last.action.extra_settings == {"is_write_index": True}


def test_run_alias_empty_name_raises() -> None:
    with pytest.raises(ValueError, match="alias"):
        run_alias(None, "", _prefix("logstash-"), [], dry_run=True)


def test_run_alias_both_filter_lists_empty_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        run_alias(None, "last_week", [], [], dry_run=True)


def test_run_alias_both_sides_resolve_empty() -> None:
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=[]),
        pytest.raises(NoIndicesError),
    ):
        run_alias(None, "last_week", _prefix("logstash-"), [], dry_run=True)


def test_cli_alias_needs_a_prefix() -> None:
    result = CliRunner().invoke(main, ["alias", "--name", "last_week"])
    assert result.exit_code != 0
    assert "prefix" in result.output.lower()


def test_cli_alias_extra_settings() -> None:
    with patch("es_steward.cli.run_alias", return_value=("COMPLETED", 1)) as run:
        result = CliRunner().invoke(
            main,
            [
                "alias",
                "--name",
                "last_week",
                "--add-prefix",
                "logstash-",
                "--extra-settings",
                '{"is_write_index": true}',
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output
    assert run.call_args.args[5] == {"is_write_index": True}


def test_cli_alias_omits_extra_settings() -> None:
    with patch("es_steward.cli.run_alias", return_value=("COMPLETED", 1)) as run:
        result = CliRunner().invoke(
            main,
            ["alias", "--name", "last_week", "--add-prefix", "logstash-", "--dry-run"],
        )
    assert result.exit_code == 0, result.output
    assert run.call_args.args[5] is None


def test_cli_alias_extra_settings_bad_json() -> None:
    with patch("es_steward.cli.run_alias") as run:
        result = CliRunner().invoke(
            main,
            [
                "alias",
                "--name",
                "last_week",
                "--add-prefix",
                "logstash-",
                "--extra-settings",
                "{",
            ],
        )
    assert result.exit_code != 0
    assert "invalid --extra-settings JSON" in result.output
    run.assert_not_called()


def test_cli_alias_extra_settings_not_object() -> None:
    with patch("es_steward.cli.run_alias") as run:
        result = CliRunner().invoke(
            main,
            [
                "alias",
                "--name",
                "last_week",
                "--add-prefix",
                "logstash-",
                "--extra-settings",
                "[]",
            ],
        )
    assert result.exit_code != 0
    assert "JSON object" in result.output
    run.assert_not_called()
