"""run_shrink and shrink CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from es_steward.cli import main
from es_steward.services import run_shrink


def test_run_shrink_empty_node_raises() -> None:
    with (
        patch("es_steward.services.get_client") as get_client,
        patch("es_steward.services.resolve") as resolve,
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="shrink_node"),
    ):
        run_shrink(config=None, prefix="logs-", shrink_node="", dry_run=True)
    get_client.assert_not_called()
    resolve.assert_not_called()
    action_run.assert_not_called()


def test_cli_shrink_missing_node() -> None:
    result = CliRunner().invoke(main, ["shrink", "--prefix", "logs-"])
    assert result.exit_code != 0


def test_cli_shrink_no_delete_after() -> None:
    with patch("es_steward.cli.run_shrink", return_value=("COMPLETED", 1)) as run:
        result = CliRunner().invoke(
            main,
            [
                "shrink",
                "--prefix",
                "logs-",
                "--shrink-node",
                "es-data-1",
                "--no-delete-after",
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["delete_after"] is False
