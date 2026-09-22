"""run_cluster_routing and cluster-routing CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from es_steward.cli import main
from es_steward.services import run_cluster_routing


def test_run_cluster_routing_invalid_combo_raises() -> None:
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="value"),
    ):
        run_cluster_routing(
            config=None,
            routing_type="allocation",
            value="replicas",
            dry_run=True,
        )
    action_run.assert_not_called()


def test_cli_cluster_routing_invalid_value_error() -> None:
    result = CliRunner().invoke(
        main,
        ["cluster-routing", "--routing-type", "allocation", "--value", "replicas"],
    )
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert 'Invalid "value"' in result.output
