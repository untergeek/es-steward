"""run_restore and restore CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from es_steward.services import run_restore


def test_run_restore_empty_repository_raises() -> None:
    with (
        patch("es_steward.services.get_client") as get_client,
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="repository"),
    ):
        run_restore(config=None, repository="", snapshot="snap-1", dry_run=True)
    get_client.assert_not_called()
    action_run.assert_not_called()


def test_run_restore_empty_snapshot_raises() -> None:
    with (
        patch("es_steward.services.get_client") as get_client,
        patch("es_steward.services.ActionRun") as action_run,
        pytest.raises(ValueError, match="snapshot"),
    ):
        run_restore(config=None, repository="repo", snapshot="", dry_run=True)
    get_client.assert_not_called()
    action_run.assert_not_called()
