"""Service-layer persist/dry_run contract (no live ES)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from es_steward.services import run_redact, run_show
from tests.unit.conftest import FakeRun


def test_run_show_returns_resolved_names() -> None:
    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=["logs-1", "logs-2"]),
    ):
        names = run_show(config=None, prefix="logs-", size_gt=None)
    assert names == ["logs-1", "logs-2"]


def test_run_redact_default_is_dry_run_no_persist() -> None:

    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=["logs-1"]),
        patch("es_steward.services.ActionRun", FakeRun),
    ):
        status, count, dry_run = run_redact(
            config=None,
            prefix="logs-",
            query={"term": {"ssn": "1"}},
            fields=["ssn"],
            message="X",
            execute=False,
        )
    assert status == "COMPLETED"
    assert count == 1
    assert dry_run is True
    assert FakeRun.last.persist is False
    assert FakeRun.last.dry_run is True


def test_run_redact_execute_persists() -> None:

    with (
        patch("es_steward.services.get_client", return_value=MagicMock()),
        patch("es_steward.services.resolve", return_value=["logs-1"]),
        patch("es_steward.services.ActionRun", FakeRun),
    ):
        status, count, dry_run = run_redact(
            config=None,
            prefix="logs-",
            query={"term": {"ssn": "1"}},
            fields=["ssn"],
            message="X",
            execute=True,
        )
    assert dry_run is False
    assert FakeRun.last.persist is True
    assert FakeRun.last.dry_run is False
    assert count == 1
    assert status == "COMPLETED"


def test_journal_recent_parses_hits() -> None:
    client = MagicMock()
    client.search.return_value = {
        "hits": {
            "hits": [
                {"_source": {"workbook_id": "w1", "status": "COMPLETED"}},
            ]
        }
    }
    with patch("es_steward.services.get_client", return_value=client):
        from es_steward.services import journal_recent

        rows = journal_recent(None, limit=5)
    assert rows[0]["workbook_id"] == "w1"
    assert client.search.call_args.kwargs["size"] == 5


def test_journal_recent_newest_first() -> None:
    client = MagicMock()
    client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "workbook_id": "old",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                    }
                },
                {
                    "_source": {
                        "workbook_id": "new",
                        "timestamp": "2026-09-05T12:00:00.000001+00:00",
                    }
                },
            ]
        }
    }
    with patch("es_steward.services.get_client", return_value=client):
        from es_steward.services import journal_recent

        rows = journal_recent(None, limit=2)
    assert [r["workbook_id"] for r in rows] == ["new", "old"]
    sort = client.search.call_args.kwargs["sort"]
    assert sort[0]["@timestamp"]["order"] == "desc"
    assert sort[0]["@timestamp"]["unmapped_type"] == "date"


def test_journal_recent_prefers_at_timestamp() -> None:
    client = MagicMock()
    client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "workbook_id": "stale_ts",
                        "timestamp": "2026-09-05T23:00:00+00:00",
                        "@timestamp": "2026-01-01T00:00:00+00:00",
                    }
                },
                {
                    "_source": {
                        "workbook_id": "fresh_at",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "@timestamp": "2026-09-05T23:00:00+00:00",
                    }
                },
            ]
        }
    }
    with patch("es_steward.services.get_client", return_value=client):
        from es_steward.services import journal_recent

        rows = journal_recent(None, limit=2)
    assert [r["workbook_id"] for r in rows] == ["fresh_at", "stale_ts"]
