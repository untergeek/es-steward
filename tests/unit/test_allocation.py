"""run_allocation and allocation CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from es_steward.cli import main
from es_steward.services import run_allocation


def test_run_allocation_invalid_type_raises() -> None:
    with (
        patch("es_steward.services.get_client") as get_client,
        patch("es_steward.services.resolve") as resolve,
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="allocation_type"),
    ):
        run_allocation(
            config=None,
            prefix="logs-",
            key="tag",
            dry_run=True,
            value="hot",
            allocation_type="bogus",
        )
    get_client.assert_not_called()
    resolve.assert_not_called()
    action_run.assert_not_called()


def test_cli_allocation_missing_key() -> None:
    result = CliRunner().invoke(main, ["allocation", "--prefix", "logs-"])
    assert result.exit_code != 0
