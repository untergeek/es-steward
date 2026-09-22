"""run_create_index and create-index CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from es_steward.cli import main
from es_steward.services import run_create_index


def _api_error(status: int = 400, msg: str = "bad request") -> object:
    from elasticsearch9 import BadRequestError

    meta = MagicMock()
    meta.status = status
    return BadRequestError(msg, meta, {})


def test_run_create_index_empty_name_never_hits_es() -> None:
    with (
        patch("es_steward.services.get_client") as get_client,
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="name"),
    ):
        run_create_index(config=None, name="", dry_run=True)
    get_client.assert_not_called()
    action_run.assert_not_called()


def test_cli_create_index_ignore_existing() -> None:
    with patch("es_steward.cli.run_create_index", return_value=("COMPLETED", 1)) as run:
        result = CliRunner().invoke(
            main,
            [
                "create-index",
                "--name",
                "logs-000001",
                "--ignore-existing",
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output
    assert run.call_args.args[3] is True


def test_cli_create_index_empty_name_error() -> None:
    result = CliRunner().invoke(main, ["create-index", "--name", ""])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "name is required" in result.output


def test_cli_create_index_apierror_error() -> None:
    with patch("es_steward.cli.run_create_index", side_effect=_api_error()):
        result = CliRunner().invoke(main, ["create-index", "--name", "My Index"])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "bad request" in result.output.lower()
