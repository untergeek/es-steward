"""run_snapshot and snapshot CLI (no live ES)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from es_steward.services import run_snapshot


def test_run_snapshot_empty_repository_raises() -> None:
    with (
        patch("es_steward.services.resolve") as resolve,
        pytest.raises(ValueError, match="repository"),
    ):
        run_snapshot(
            config=None,
            repository="",
            snapshot="snap-1",
            prefix="logs-",
            dry_run=True,
        )
    resolve.assert_not_called()


def test_run_snapshot_empty_snapshot_raises() -> None:
    with (
        patch("es_steward.services.resolve") as resolve,
        pytest.raises(ValueError, match="snapshot"),
    ):
        run_snapshot(
            config=None,
            repository="repo",
            snapshot="",
            prefix="logs-",
            dry_run=True,
        )
    resolve.assert_not_called()
