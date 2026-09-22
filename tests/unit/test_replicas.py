"""run_replicas and replicas CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from es_steward.cli import main
from es_steward.services import run_replicas


def test_run_replicas_negative_count_raises() -> None:
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=["logs-1"]),
        pytest.raises(ValueError, match="count"),
    ):
        run_replicas(config=None, prefix="logs-", count=-1, dry_run=True)


def test_cli_replicas_missing_count() -> None:
    result = CliRunner().invoke(main, ["replicas", "--prefix", "logs-"])
    assert result.exit_code != 0
