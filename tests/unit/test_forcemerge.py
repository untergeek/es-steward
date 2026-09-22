"""run_forcemerge and forcemerge CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from es_steward.cli import main
from es_steward.services import run_forcemerge


def test_run_forcemerge_zero_segments_never_resolves() -> None:
    with (
        patch("es_steward.services.get_client") as get_client,
        patch("es_steward.services.resolve") as resolve,
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="max_num_segments"),
    ):
        run_forcemerge(config=None, prefix="logs-", max_num_segments=0, dry_run=True)
    get_client.assert_not_called()
    resolve.assert_not_called()
    action_run.assert_not_called()


def test_cli_forcemerge_zero_segments_never_calls() -> None:
    with patch("es_steward.cli.run_forcemerge") as run:
        result = CliRunner().invoke(
            main, ["forcemerge", "--prefix", "logs-", "--max-num-segments", "0"]
        )
    assert result.exit_code != 0
    run.assert_not_called()


def test_cli_forcemerge_missing_segments() -> None:
    result = CliRunner().invoke(main, ["forcemerge", "--prefix", "logs-"])
    assert result.exit_code != 0
