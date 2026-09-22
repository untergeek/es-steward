"""Tests for the package CLI surface."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from es_steward import JOURNAL
from es_steward.cli import cli_mutate, main
from es_steward.services import NoIndicesError
from tests.unit.conftest import FakeRun


def test_journal_name() -> None:
    """Tracking index is es-steward-journal, not es-checkpoint."""
    assert JOURNAL == "es-steward-journal"


def test_cli_help() -> None:
    """Console script group exposes --help."""
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "es-steward" in result.output.lower() or "Steward" in result.output


def test_cli_promote_help_is_dry_run_capable() -> None:
    result = CliRunner().invoke(main, ["promote", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output
    assert "--prefix" in result.output


def test_cli_redact_help_requires_query_and_execute_flag() -> None:
    result = CliRunner().invoke(main, ["redact", "--help"])
    assert result.exit_code == 0
    assert "--query" in result.output
    assert "--field" in result.output
    assert "--execute" in result.output
    assert "hot" in result.output.lower() or "update_by_query" in result.output


def test_cli_tui_help() -> None:
    result = CliRunner().invoke(main, ["tui", "--help"])
    assert result.exit_code == 0
    assert "Interactive Steward TUI" in result.output


def test_cli_import_yaml_help_mentions_curator_defaults() -> None:
    result = CliRunner().invoke(main, ["import-yaml", "--help"])
    assert result.exit_code == 0
    assert "Curator" in result.output
    assert "exclude" in result.output.lower()


def test_cli_alias_help() -> None:
    result = CliRunner().invoke(main, ["alias", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output
    assert "--add-prefix" in result.output
    assert "--remove-prefix" in result.output
    assert "--dry-run" in result.output
    assert "--extra-settings" in result.output


def test_cli_delete_help() -> None:
    result = CliRunner().invoke(main, ["delete", "--help"])
    assert result.exit_code == 0
    assert "--prefix" in result.output
    assert "--dry-run" in result.output


def test_cli_close_help() -> None:
    result = CliRunner().invoke(main, ["close", "--help"])
    assert result.exit_code == 0
    assert "--prefix" in result.output
    assert "--dry-run" in result.output


def test_cli_open_help() -> None:
    result = CliRunner().invoke(main, ["open", "--help"])
    assert result.exit_code == 0
    assert "--prefix" in result.output
    assert "--dry-run" in result.output


def test_cli_delete_snapshots_help() -> None:
    result = CliRunner().invoke(main, ["delete-snapshots", "--help"])
    assert result.exit_code == 0
    assert "--repository" in result.output
    assert "--prefix" in result.output
    assert "--dry-run" in result.output


def test_cli_snapshot_help() -> None:
    result = CliRunner().invoke(main, ["snapshot", "--help"])
    assert result.exit_code == 0
    assert "--repository" in result.output
    assert "--snapshot" in result.output
    assert "--prefix" in result.output
    assert "--dry-run" in result.output


def test_cli_restore_help() -> None:
    result = CliRunner().invoke(main, ["restore", "--help"])
    assert result.exit_code == 0
    assert "--repository" in result.output
    assert "--snapshot" in result.output
    assert "--dry-run" in result.output
    assert "--prefix" not in result.output


def test_cli_forcemerge_help() -> None:
    result = CliRunner().invoke(main, ["forcemerge", "--help"])
    assert result.exit_code == 0
    assert "--prefix" in result.output
    assert "--max-num-segments" in result.output
    assert "--dry-run" in result.output


def test_cli_allocation_help() -> None:
    result = CliRunner().invoke(main, ["allocation", "--help"])
    assert result.exit_code == 0
    assert "--prefix" in result.output
    assert "--key" in result.output
    assert "--value" in result.output
    assert "--allocation-type" in result.output
    assert "--dry-run" in result.output


def test_cli_replicas_help() -> None:
    result = CliRunner().invoke(main, ["replicas", "--help"])
    assert result.exit_code == 0
    assert "--prefix" in result.output
    assert "--count" in result.output
    assert "--dry-run" in result.output


def test_cli_shrink_help() -> None:
    result = CliRunner().invoke(main, ["shrink", "--help"])
    assert result.exit_code == 0
    assert "--prefix" in result.output
    assert "--shrink-node" in result.output
    assert "--delete-after" in result.output
    assert "--dry-run" in result.output


def test_cli_rollover_help() -> None:
    result = CliRunner().invoke(main, ["rollover", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output
    assert "--conditions" in result.output
    assert "--dry-run" in result.output
    assert "--prefix" not in result.output


def test_cli_reindex_help() -> None:
    result = CliRunner().invoke(main, ["reindex", "--help"])
    assert result.exit_code == 0
    assert "--prefix" in result.output
    assert "--dest" in result.output
    assert "--dry-run" in result.output


def test_cli_index_settings_help() -> None:
    result = CliRunner().invoke(main, ["index-settings", "--help"])
    assert result.exit_code == 0
    assert "--prefix" in result.output
    assert "--settings" in result.output
    assert "--dry-run" in result.output


def test_cli_cluster_routing_help() -> None:
    result = CliRunner().invoke(main, ["cluster-routing", "--help"])
    assert result.exit_code == 0
    assert "--routing-type" in result.output
    assert "--value" in result.output
    assert "--dry-run" in result.output
    assert "--prefix" not in result.output
    assert "--setting" not in result.output


def test_cli_cold2frozen_help() -> None:
    result = CliRunner().invoke(main, ["cold2frozen", "--help"])
    assert result.exit_code == 0
    assert "--prefix" in result.output
    assert "--delete-after" in result.output
    assert "--transfer-aliases" in result.output
    assert "--dry-run" in result.output


def test_cli_create_index_help() -> None:
    result = CliRunner().invoke(main, ["create-index", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output
    assert "--ignore-existing" in result.output
    assert "--dry-run" in result.output
    assert "--prefix" not in result.output


def test_cli_redact_rejects_bad_json() -> None:
    result = CliRunner().invoke(
        main,
        ["redact", "--prefix", "logs-", "--query", "{", "--field", "ssn"],
    )
    assert result.exit_code != 0
    assert "invalid --query JSON" in result.output


def test_cli_redact_execute_persists_and_is_not_dry_run() -> None:

    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=["logs-1"]) as resolve,
        patch("es_steward.services.ActionRun", FakeRun),
    ):
        result = CliRunner().invoke(
            main,
            [
                "redact",
                "--prefix",
                "logs-",
                "--query",
                '{"term":{"ssn":"1"}}',
                "--field",
                "ssn",
                "--execute",
            ],
        )
    assert result.exit_code == 0, result.output
    assert FakeRun.last.persist is True
    assert FakeRun.last.dry_run is False
    filters = resolve.call_args.kwargs["filters"]
    kinds = [getattr(f, "kind", None) for f in filters]
    assert "opened" in kinds


def test_cli_mutate_no_indices_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    """acceptance C: cli_mutate echoes empty on stderr and exits 1."""

    def boom() -> object:
        raise NoIndicesError("ignored")

    with pytest.raises(SystemExit) as exc:
        cli_mutate(boom)
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.err == "no indices\n"
    assert captured.out == ""
