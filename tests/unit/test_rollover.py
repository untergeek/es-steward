"""run_rollover and rollover CLI (no live ES)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from es_steward.cli import main
from es_steward.services import run_rollover
from tests.unit.conftest import FakeRun


def test_run_rollover_empty_name_never_hits_es() -> None:
    with (
        patch("es_steward.services.get_client") as get_client,
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="name"),
    ):
        run_rollover(config=None, name="", conditions={"max_age": "7d"}, dry_run=True)
    get_client.assert_not_called()
    action_run.assert_not_called()


def test_run_rollover_conditions_not_dict_raises() -> None:
    with (
        patch("es_steward.services.get_client") as get_client,
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="conditions"),
    ):
        run_rollover(config=None, name="logs-write", conditions=[], dry_run=True)  # type: ignore[arg-type]
    get_client.assert_not_called()
    action_run.assert_not_called()


def test_cli_rollover_bad_json_never_calls() -> None:
    with patch("es_steward.cli.run_rollover") as run:
        result = CliRunner().invoke(
            main,
            ["rollover", "--name", "logs-write", "--conditions", "{"],
        )
    assert result.exit_code != 0
    assert "invalid --conditions JSON" in result.output
    run.assert_not_called()


def test_cli_rollover_non_object_never_calls() -> None:
    with patch("es_steward.cli.run_rollover") as run:
        result = CliRunner().invoke(
            main,
            ["rollover", "--name", "logs-write", "--conditions", "[]"],
        )
    assert result.exit_code != 0
    assert "JSON object" in result.output
    run.assert_not_called()


def test_cli_rollover_prints_rolled_over_false() -> None:
    raw = {"rolled_over": False, "new_index": "logs-000002"}
    with patch("es_steward.cli.run_rollover", return_value=("COMPLETED", 1, raw)):
        result = CliRunner().invoke(
            main,
            [
                "rollover",
                "--name",
                "logs-write",
                "--conditions",
                '{"max_age":"7d"}',
            ],
        )
    assert result.exit_code == 0, result.output
    assert "COMPLETED 1 aliases rolled_over=false" in result.output
    assert "new_index=logs-000002" in result.output
    assert "definitely-not-an-op" not in result.output
    assert "step=" not in result.output


def test_cli_rollover_empty_raw_keeps_old_line() -> None:
    with patch("es_steward.cli.run_rollover", return_value=("COMPLETED", 1, None)):
        result = CliRunner().invoke(
            main,
            [
                "rollover",
                "--name",
                "logs-write",
                "--conditions",
                '{"max_age":"7d"}',
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "COMPLETED 1 aliases"
    assert "rolled_over" not in result.output


def test_run_rollover_reads_rolled_over_from_raw_not_step() -> None:
    """First raw with rolled_over wins; step strings are ignored."""

    class _ResultsRun(FakeRun):
        def run(
            self, action: object = None, names: object = None, **kwargs: object
        ) -> object:
            del action, names, kwargs
            return SimpleNamespace(
                status="COMPLETED",
                results=[
                    {
                        "ok": True,
                        "names": ["logs-write"],
                        "raw": None,
                        "task_id": None,
                        "error": None,
                        "step": "pre-1",
                    },
                    {
                        "ok": True,
                        "names": ["logs-write"],
                        "raw": {"rolled_over": False, "new_index": "logs-000002"},
                        "task_id": None,
                        "error": None,
                        "step": "definitely-not-an-op",
                    },
                ],
            )

    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.ActionRun", _ResultsRun),
    ):
        status, count, raw = run_rollover(
            config=None,
            name="logs-write",
            conditions={"max_age": "7d"},
            dry_run=False,
        )
    assert status == "COMPLETED"
    assert count == 1
    assert raw == {"rolled_over": False, "new_index": "logs-000002"}
