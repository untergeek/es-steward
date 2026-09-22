"""run_delete and delete CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from es_steward.cli import main
from es_steward.services import run_delete


def test_run_delete_empty_prefix_raises() -> None:
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="unbounded"),
    ):
        run_delete(config=None, prefix="", dry_run=True)
    action_run.assert_not_called()


def test_cli_delete_cancelled_exits_1() -> None:
    with patch("es_steward.cli.run_delete", return_value=("CANCELLED", 1)):
        result = CliRunner().invoke(main, ["delete", "--prefix", "logs-"])
    assert result.exit_code == 1
    assert "CANCELLED" in result.output


def test_cli_delete_completed_exits_0() -> None:
    with patch("es_steward.cli.run_delete", return_value=("COMPLETED", 1)):
        result = CliRunner().invoke(main, ["delete", "--prefix", "logs-"])
    assert result.exit_code == 0


def test_cli_delete_empty_prefix_error() -> None:
    with patch("es_steward.cli.run_delete", side_effect=ValueError("unbounded prefix")):
        result = CliRunner().invoke(main, ["delete", "--prefix", ""])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "unbounded prefix" in result.output


def test_cli_delete_es_down_error() -> None:
    from elastic_transport import ConnectionError as ESConnectionError

    with patch("es_steward.cli.run_delete", side_effect=ESConnectionError("down")):
        result = CliRunner().invoke(main, ["delete", "--prefix", "logs-"])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "elasticsearch unavailable" in result.output
