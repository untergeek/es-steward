"""run_cold2frozen and cold2frozen CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from es_steward.cli import main
from es_steward.services import run_cold2frozen


def test_run_cold2frozen_empty_prefix_raises() -> None:
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="unbounded"),
    ):
        run_cold2frozen(config=None, prefix="", dry_run=True)
    action_run.assert_not_called()


def test_cli_cold2frozen_no_delete_after() -> None:
    with patch("es_steward.cli.run_cold2frozen", return_value=("COMPLETED", 1)) as run:
        result = CliRunner().invoke(
            main,
            [
                "cold2frozen",
                "--prefix",
                "logs-",
                "--no-delete-after",
                "--no-transfer-aliases",
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output
    assert run.call_args.kwargs["delete_after"] is False
    assert run.call_args.kwargs["transfer_aliases"] is False
