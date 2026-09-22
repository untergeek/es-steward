"""run_reindex and reindex CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from es_steward.cli import main
from es_steward.services import run_reindex


def test_run_reindex_empty_dest_never_hits_es() -> None:
    with (
        patch("es_steward.services.get_client") as get_client,
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="dest"),
    ):
        run_reindex(config=None, prefix="logs-", dest="", dry_run=True)
    get_client.assert_not_called()
    action_run.assert_not_called()


def test_run_reindex_dest_in_source_set_raises() -> None:
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=["logs-2026"]),
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="source set"),
    ):
        run_reindex(config=None, prefix="logs-", dest="logs-2026", dry_run=True)
    action_run.assert_not_called()


def test_cli_reindex_missing_dest() -> None:
    result = CliRunner().invoke(main, ["reindex", "--prefix", "logs-"])
    assert result.exit_code != 0
