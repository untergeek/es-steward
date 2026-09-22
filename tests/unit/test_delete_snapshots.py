"""run_delete_snapshots and delete-snapshots CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from es_steward.services import NoIndicesError, run_delete_snapshots


def test_run_delete_snapshots_no_snapshots_raises() -> None:
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=[]),
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(NoIndicesError, match="no snapshots"),
    ):
        run_delete_snapshots(
            config=None, repository="repo", prefix="snap-", dry_run=True
        )
    action_run.assert_not_called()


def test_run_delete_snapshots_empty_repository_raises() -> None:
    with (
        patch("es_steward.services.resolve") as resolve,
        pytest.raises(ValueError, match="repository"),
    ):
        run_delete_snapshots(config=None, repository="", prefix="snap-", dry_run=True)
    resolve.assert_not_called()
