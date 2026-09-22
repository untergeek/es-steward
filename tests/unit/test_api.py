"""API tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from elastic_transport import ConnectionError as ESConnectionError
from fastapi.testclient import TestClient

from es_steward import JOURNAL
from es_steward.api import create_app
from es_steward.services import NoIndicesError


def _auth_client() -> TestClient:
    return TestClient(create_app(token="secret"))


def _hdr() -> dict[str, str]:
    return {"X-Steward-Token": "secret"}


def _api_error(status: int = 400, msg: str = "bad request") -> object:
    from elasticsearch9 import BadRequestError

    meta = MagicMock()
    meta.status = status
    return BadRequestError(msg, meta, {})


@dataclass
class _HttpAction:
    suffix: str
    run: str
    body: dict[str, Any]
    dry_run: dict[str, Any] | None = None
    extra: dict[str, Any] | None = None
    missing: dict[str, Any] | None = None
    not_found: str | None = None
    token: bool = False
    es_down: bool = False
    run_return: tuple[Any, ...] = ("COMPLETED", 1)
    dry_run_args: dict[int, Any] | None = None


# acceptance A — HEAD actions that already have the repeated HTTP matrix.
_ACTIONS: tuple[_HttpAction, ...] = (
    _HttpAction(
        suffix="promote",
        run="run_promote",
        body={"prefix": "logs-"},
        dry_run={"prefix": "logs-", "dry_run": True},
        extra={"prefix": "logs-", "bogus": 1},
        missing={"size_gt": 1},
        es_down=True,
        dry_run_args={3: True},
    ),
    _HttpAction(
        suffix="alias",
        run="run_alias",
        body={"name": "last_week", "add_prefix": "logstash-"},
        extra={"name": "last_week", "add_prefix": "logstash-", "bogus": 1},
        missing={"add_prefix": "logstash-"},
        not_found="no indices",
        token=True,
        es_down=True,
    ),
    _HttpAction(
        suffix="delete",
        run="run_delete",
        body={"prefix": "logs-"},
        dry_run={"prefix": "logs-", "dry_run": True},
        extra={"prefix": "logs-", "bogus": 1},
        missing={"dry_run": True},
        not_found="no indices",
        token=True,
        es_down=True,
        dry_run_args={1: "logs-", 2: True},
    ),
    _HttpAction(
        suffix="close",
        run="run_close",
        body={"prefix": "logs-"},
        dry_run={"prefix": "logs-", "dry_run": True},
        extra={"prefix": "logs-", "bogus": 1},
        missing={"dry_run": True},
        not_found="no indices",
        token=True,
        es_down=True,
        dry_run_args={1: "logs-", 2: True},
    ),
    _HttpAction(
        suffix="open",
        run="run_open",
        body={"prefix": "logs-"},
        dry_run={"prefix": "logs-", "dry_run": True},
        extra={"prefix": "logs-", "bogus": 1},
        missing={"dry_run": True},
        not_found="no indices",
        token=True,
        es_down=True,
        dry_run_args={1: "logs-", 2: True},
    ),
    _HttpAction(
        suffix="delete-snapshots",
        run="run_delete_snapshots",
        body={"repository": "repo", "prefix": "snap-"},
        dry_run={"repository": "repo", "prefix": "snap-", "dry_run": True},
        extra={"repository": "repo", "prefix": "snap-", "bogus": 1},
        missing={"prefix": "snap-"},
        not_found="no snapshots",
        token=True,
        es_down=True,
        dry_run_args={1: "repo", 2: "snap-", 3: True},
    ),
    _HttpAction(
        suffix="snapshot",
        run="run_snapshot",
        body={"repository": "repo", "snapshot": "snap-1", "prefix": "logs-"},
        dry_run={
            "repository": "repo",
            "snapshot": "snap-1",
            "prefix": "logs-",
            "dry_run": True,
        },
        extra={
            "repository": "repo",
            "snapshot": "snap-1",
            "prefix": "logs-",
            "bogus": 1,
        },
        missing={"repository": "repo", "prefix": "logs-"},
        not_found="no indices",
        token=True,
        es_down=True,
        dry_run_args={1: "repo", 2: "snap-1", 3: "logs-", 4: True},
    ),
    _HttpAction(
        suffix="restore",
        run="run_restore",
        body={"repository": "repo", "snapshot": "snap-1"},
        dry_run={"repository": "repo", "snapshot": "snap-1", "dry_run": True},
        extra={"repository": "repo", "snapshot": "snap-1", "bogus": 1},
        missing={"repository": "repo"},
        token=True,
        es_down=True,
        dry_run_args={1: "repo", 2: "snap-1", 3: True},
    ),
    _HttpAction(
        suffix="forcemerge",
        run="run_forcemerge",
        body={"prefix": "logs-", "max_num_segments": 1},
        dry_run={"prefix": "logs-", "max_num_segments": 1, "dry_run": True},
        extra={"prefix": "logs-", "max_num_segments": 1, "bogus": 1},
        missing={"prefix": "logs-"},
        not_found="no indices",
        token=True,
        es_down=True,
        dry_run_args={1: "logs-", 2: 1, 3: True},
    ),
    _HttpAction(
        suffix="allocation",
        run="run_allocation",
        body={"prefix": "logs-", "key": "tag"},
        dry_run={
            "prefix": "logs-",
            "key": "tag",
            "value": "hot",
            "dry_run": True,
        },
        extra={"prefix": "logs-", "key": "tag", "bogus": 1},
        missing={"prefix": "logs-"},
        not_found="no indices",
        token=True,
        es_down=True,
        dry_run_args={1: "logs-", 2: "tag", 3: True, 4: "hot", 5: "require"},
    ),
    _HttpAction(
        suffix="replicas",
        run="run_replicas",
        body={"prefix": "logs-", "count": 1},
        dry_run={"prefix": "logs-", "count": 0, "dry_run": True},
        extra={"prefix": "logs-", "count": 1, "bogus": 1},
        missing={"prefix": "logs-"},
        not_found="no indices",
        token=True,
        es_down=True,
        dry_run_args={1: "logs-", 2: 0, 3: True},
    ),
    _HttpAction(
        suffix="shrink",
        run="run_shrink",
        body={"prefix": "logs-", "shrink_node": "es-data-1"},
        dry_run={
            "prefix": "logs-",
            "shrink_node": "es-data-1",
            "dry_run": True,
        },
        extra={
            "prefix": "logs-",
            "shrink_node": "es-data-1",
            "number_of_shards": 1,
        },
        missing={"prefix": "logs-"},
        not_found="no indices",
        token=True,
        es_down=True,
        dry_run_args={1: "logs-", 2: "es-data-1", 3: True},
    ),
    _HttpAction(
        suffix="rollover",
        run="run_rollover",
        body={"name": "logs-write", "conditions": {"max_age": "7d"}},
        dry_run={
            "name": "logs-write",
            "conditions": {"max_age": "7d"},
            "dry_run": True,
        },
        token=True,
        es_down=True,
        run_return=("COMPLETED", 1, None),
        dry_run_args={1: "logs-write", 2: {"max_age": "7d"}, 3: True},
    ),
    _HttpAction(
        suffix="reindex",
        run="run_reindex",
        body={"prefix": "logs-", "dest": "dest-idx"},
        dry_run={"prefix": "logs-", "dest": "dest-idx", "dry_run": True},
        extra={"prefix": "logs-", "dest": "dest-idx", "body_extra": {}},
        missing={"prefix": "logs-"},
        not_found="no indices",
        token=True,
        es_down=True,
        dry_run_args={1: "logs-", 2: "dest-idx", 3: True},
    ),
    _HttpAction(
        suffix="index-settings",
        run="run_index_settings",
        body={"prefix": "logs-", "settings": {"number_of_replicas": 0}},
        dry_run={
            "prefix": "logs-",
            "settings": {"number_of_replicas": 0},
            "dry_run": True,
        },
        extra={
            "prefix": "logs-",
            "settings": {"number_of_replicas": 0},
            "bogus": 1,
        },
        not_found="no indices",
        token=True,
        es_down=True,
        dry_run_args={1: "logs-", 2: {"number_of_replicas": 0}, 3: True},
    ),
    _HttpAction(
        suffix="cluster-routing",
        run="run_cluster_routing",
        body={"routing_type": "allocation", "value": "primaries"},
        dry_run={
            "routing_type": "allocation",
            "value": "primaries",
            "dry_run": True,
        },
        token=True,
        es_down=True,
        dry_run_args={1: "allocation", 2: "primaries", 3: True},
    ),
    _HttpAction(
        suffix="cold2frozen",
        run="run_cold2frozen",
        body={"prefix": "logs-"},
        dry_run={"prefix": "logs-", "dry_run": True},
        extra={"prefix": "logs-", "bogus": 1},
        missing={"dry_run": True},
        not_found="no indices",
        token=True,
        es_down=True,
        dry_run_args={1: "logs-", 2: True},
    ),
    _HttpAction(
        suffix="create-index",
        run="run_create_index",
        body={"name": "logs-000001"},
        dry_run={"name": "logs-000001", "dry_run": True},
        token=True,
        es_down=True,
        dry_run_args={1: "logs-000001", 2: True, 3: False},
    ),
)


def _rows(field: str) -> list[_HttpAction]:
    return [a for a in _ACTIONS if getattr(a, field)]


# acceptance A — HEAD (action, category) matrix. A count-only check is not enough.
_CAT_FIELDS: tuple[tuple[str, str], ...] = (
    ("dry_run", "dry_run"),
    ("extra", "extra422"),
    ("missing", "missing422"),
    ("not_found", "404"),
    ("es_down", "503"),
    ("token", "401"),
)
_HEAD_MATRIX: frozenset[tuple[str, str]] = frozenset(
    (suffix, cat)
    for cat, suffixes in {
        "dry_run": (
            "promote",
            "delete",
            "close",
            "open",
            "delete-snapshots",
            "snapshot",
            "restore",
            "forcemerge",
            "allocation",
            "replicas",
            "shrink",
            "rollover",
            "reindex",
            "index-settings",
            "cluster-routing",
            "cold2frozen",
            "create-index",
        ),
        "extra422": (
            "promote",
            "alias",
            "delete",
            "close",
            "open",
            "delete-snapshots",
            "snapshot",
            "restore",
            "forcemerge",
            "allocation",
            "replicas",
            "shrink",
            "reindex",
            "index-settings",
            "cold2frozen",
        ),
        "missing422": (
            "promote",
            "alias",
            "delete",
            "close",
            "open",
            "delete-snapshots",
            "snapshot",
            "restore",
            "forcemerge",
            "allocation",
            "replicas",
            "shrink",
            "reindex",
            "cold2frozen",
        ),
        "404": (
            "alias",
            "delete",
            "close",
            "open",
            "delete-snapshots",
            "snapshot",
            "forcemerge",
            "allocation",
            "replicas",
            "shrink",
            "reindex",
            "index-settings",
            "cold2frozen",
        ),
        "503": (
            "promote",
            "alias",
            "delete",
            "close",
            "open",
            "delete-snapshots",
            "snapshot",
            "restore",
            "forcemerge",
            "allocation",
            "replicas",
            "shrink",
            "rollover",
            "reindex",
            "index-settings",
            "cluster-routing",
            "cold2frozen",
            "create-index",
        ),
        "401": (
            "alias",
            "delete",
            "close",
            "open",
            "delete-snapshots",
            "snapshot",
            "restore",
            "forcemerge",
            "allocation",
            "replicas",
            "shrink",
            "rollover",
            "reindex",
            "index-settings",
            "cluster-routing",
            "cold2frozen",
            "create-index",
        ),
    }.items()
    for suffix in suffixes
)


def _matrix() -> frozenset[tuple[str, str]]:
    return frozenset(
        (a.suffix, cat) for field, cat in _CAT_FIELDS for a in _rows(field)
    )


def test_api_action_matrix_membership() -> None:
    """acceptance A: dropping an action from the parametrize table must fail that action's cases."""
    assert _matrix() == _HEAD_MATRIX


def test_health() -> None:
    client = TestClient(create_app(token="secret"))
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.json()["journal"] == "es-steward-journal"


def test_journal_requires_token() -> None:
    client = TestClient(create_app(token="secret"))
    assert client.get("/journal/workbooks").status_code == 401
    with patch(
        "es_steward.api.app.journal_recent", return_value=[{"workbook_id": "w1"}]
    ):
        res = client.get("/journal/workbooks", headers={"X-Steward-Token": "secret"})
    assert res.status_code == 200
    assert res.json()[0]["workbook_id"] == "w1"


def test_redact_defaults_dry_run() -> None:
    client = TestClient(create_app(token="secret"))
    with patch(
        "es_steward.api.app.run_redact", return_value=("COMPLETED", 1, True)
    ) as run:
        res = client.post(
            "/actions/redact",
            headers={"X-Steward-Token": "secret"},
            json={"prefix": "logs-", "query": {"term": {"a": 1}}, "fields": ["ssn"]},
        )
    assert res.status_code == 200
    assert res.json()["dry_run"] is True
    assert run.call_args.args[5] is False


def test_redact_execute_true() -> None:
    client = TestClient(create_app(token="secret"))
    with patch(
        "es_steward.api.app.run_redact", return_value=("COMPLETED", 2, False)
    ) as run:
        res = client.post(
            "/actions/redact",
            headers={"X-Steward-Token": "secret"},
            json={
                "prefix": "logs-",
                "query": {"term": {"a": 1}},
                "fields": ["ssn"],
                "execute": True,
            },
        )
    assert res.status_code == 200
    assert res.json()["dry_run"] is False
    assert run.call_args.args[5] is True


def test_redact_invalid_query_type_422() -> None:
    res = _auth_client().post(
        "/actions/redact",
        headers=_hdr(),
        json={"prefix": "logs-", "query": [], "fields": ["ssn"]},
    )
    assert res.status_code == 422


def test_promote_rejects_per_request_config() -> None:
    res = _auth_client().post(
        "/actions/promote",
        headers=_hdr(),
        json={"prefix": "logs-", "config": "/tmp/other.yml"},
    )
    assert res.status_code == 422


def test_redact_es_down_503() -> None:
    with patch(
        "es_steward.api.app.run_redact", side_effect=ESConnectionError("down")
    ):
        res = _auth_client().post(
            "/actions/redact",
            headers=_hdr(),
            json={"prefix": "logs-", "query": {"term": {"a": 1}}, "fields": ["ssn"]},
        )
    assert res.status_code == 503


def test_journal_es_down_503() -> None:
    with patch(
        "es_steward.api.app.journal_recent", side_effect=ESConnectionError("down")
    ):
        res = _auth_client().get("/journal/workbooks", headers=_hdr())
    assert res.status_code == 503


def test_alias_dry_run() -> None:
    with patch("es_steward.api.app.run_alias", return_value=("COMPLETED", 1)) as run:
        res = _auth_client().post(
            "/actions/alias",
            headers=_hdr(),
            json={"name": "last_week", "add_prefix": "logstash-", "dry_run": True},
        )
    assert res.status_code == 200
    assert res.json() == {"status": "COMPLETED", "count": 1, "dry_run": True}
    assert run.call_args.args[1] == "last_week"
    assert run.call_args.args[4] is True
    assert run.call_args.args[2][0].value == "logstash-"
    assert run.call_args.args[3] == []


def test_alias_no_prefixes_422() -> None:
    res = _auth_client().post(
        "/actions/alias", headers=_hdr(), json={"name": "last_week"}
    )
    assert res.status_code == 422


def test_alias_extra_settings() -> None:
    with patch("es_steward.api.app.run_alias", return_value=("COMPLETED", 1)) as run:
        res = _auth_client().post(
            "/actions/alias",
            headers=_hdr(),
            json={
                "name": "last_week",
                "add_prefix": "logstash-",
                "extra_settings": {"is_write_index": True},
                "dry_run": True,
            },
        )
    assert res.status_code == 200
    assert run.call_args.args[5] == {"is_write_index": True}


def test_alias_extra_settings_list_422() -> None:
    res = _auth_client().post(
        "/actions/alias",
        headers=_hdr(),
        json={
            "name": "last_week",
            "add_prefix": "logstash-",
            "extra_settings": [],
        },
    )
    assert res.status_code == 422


@pytest.mark.parametrize("case", _rows("dry_run"), ids=lambda c: c.suffix)
def test_api_action_dry_run(case: _HttpAction) -> None:
    """acceptance A: dry_run 200."""
    with patch(
        f"es_steward.api.app.{case.run}", return_value=case.run_return
    ) as run:
        res = _auth_client().post(
            f"/actions/{case.suffix}", headers=_hdr(), json=case.dry_run
        )
    assert res.status_code == 200
    assert res.json() == {"status": "COMPLETED", "count": 1, "dry_run": True}
    if case.dry_run_args is not None:
        for idx, expected in case.dry_run_args.items():
            assert run.call_args.args[idx] == expected


@pytest.mark.parametrize("case", _rows("extra"), ids=lambda c: c.suffix)
def test_api_action_extra_field_422(case: _HttpAction) -> None:
    """acceptance A: extra field 422."""
    res = _auth_client().post(
        f"/actions/{case.suffix}", headers=_hdr(), json=case.extra
    )
    assert res.status_code == 422


@pytest.mark.parametrize("case", _rows("missing"), ids=lambda c: c.suffix)
def test_api_action_missing_required_422(case: _HttpAction) -> None:
    """acceptance A: missing required 422."""
    res = _auth_client().post(
        f"/actions/{case.suffix}", headers=_hdr(), json=case.missing
    )
    assert res.status_code == 422


@pytest.mark.parametrize("case", _rows("not_found"), ids=lambda c: c.suffix)
def test_api_action_no_indices_404(case: _HttpAction) -> None:
    """acceptance A: NoIndicesError 404 with HEAD detail string."""
    with patch(
        f"es_steward.api.app.{case.run}",
        side_effect=NoIndicesError(case.not_found),
    ):
        res = _auth_client().post(
            f"/actions/{case.suffix}", headers=_hdr(), json=case.body
        )
    assert res.status_code == 404
    assert res.json()["detail"] == case.not_found


@pytest.mark.parametrize("case", _rows("es_down"), ids=lambda c: c.suffix)
def test_api_action_es_down_503(case: _HttpAction) -> None:
    """acceptance A: TransportError 503."""
    payload = {**case.body, "dry_run": True}
    with patch(
        f"es_steward.api.app.{case.run}", side_effect=ESConnectionError("down")
    ):
        res = _auth_client().post(
            f"/actions/{case.suffix}", headers=_hdr(), json=payload
        )
    assert res.status_code == 503
    assert "unavailable" in str(res.json()["detail"]).lower()


@pytest.mark.parametrize("case", _rows("token"), ids=lambda c: c.suffix)
def test_api_action_requires_token(case: _HttpAction) -> None:
    """acceptance A: missing token 401."""
    res = TestClient(create_app(token="secret")).post(
        f"/actions/{case.suffix}", json=case.body
    )
    assert res.status_code == 401


def test_delete_snapshots_empty_repository_422() -> None:
    with patch(
        "es_steward.api.app.run_delete_snapshots",
        side_effect=ValueError("repository is required"),
    ):
        res = _auth_client().post(
            "/actions/delete-snapshots",
            headers=_hdr(),
            json={"repository": "", "prefix": "snap-"},
        )
    assert res.status_code == 422


def test_snapshot_empty_repository_422() -> None:
    with patch(
        "es_steward.api.app.run_snapshot",
        side_effect=ValueError("repository and snapshot are required"),
    ):
        res = _auth_client().post(
            "/actions/snapshot",
            headers=_hdr(),
            json={"repository": "", "snapshot": "snap-1", "prefix": "logs-"},
        )
    assert res.status_code == 422


def test_restore_prefix_field_422() -> None:
    res = _auth_client().post(
        "/actions/restore",
        headers=_hdr(),
        json={"repository": "repo", "snapshot": "snap-1", "prefix": "logs-"},
    )
    assert res.status_code == 422


def test_restore_empty_repository_422() -> None:
    with patch(
        "es_steward.api.app.run_restore",
        side_effect=ValueError("repository and snapshot are required"),
    ):
        res = _auth_client().post(
            "/actions/restore",
            headers=_hdr(),
            json={"repository": "", "snapshot": "snap-1"},
        )
    assert res.status_code == 422


def test_forcemerge_zero_segments_422() -> None:
    res = _auth_client().post(
        "/actions/forcemerge",
        headers=_hdr(),
        json={"prefix": "logs-", "max_num_segments": 0},
    )
    assert res.status_code == 422


def test_allocation_invalid_type_422() -> None:
    res = _auth_client().post(
        "/actions/allocation",
        headers=_hdr(),
        json={"prefix": "logs-", "key": "tag", "allocation_type": "bogus"},
    )
    assert res.status_code == 422


def test_replicas_negative_count_422() -> None:
    res = _auth_client().post(
        "/actions/replicas",
        headers=_hdr(),
        json={"prefix": "logs-", "count": -1},
    )
    assert res.status_code == 422


def test_shrink_empty_node_422() -> None:
    res = _auth_client().post(
        "/actions/shrink",
        headers=_hdr(),
        json={"prefix": "logs-", "shrink_node": ""},
    )
    assert res.status_code == 422


def test_rollover_json_includes_rolled_over() -> None:
    raw = {"rolled_over": False, "new_index": "logs-000002"}
    with patch(
        "es_steward.api.app.run_rollover",
        return_value=("COMPLETED", 1, raw),
    ):
        res = _auth_client().post(
            "/actions/rollover",
            headers=_hdr(),
            json={"name": "logs-write", "conditions": {"max_age": "7d"}},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "COMPLETED"
    assert body["rolled_over"] is False
    assert body["new_index"] == "logs-000002"
    assert "step" not in body


def test_rollover_conditions_list_422() -> None:
    res = _auth_client().post(
        "/actions/rollover",
        headers=_hdr(),
        json={"name": "logs-write", "conditions": []},
    )
    assert res.status_code == 422


def test_rollover_prefix_422() -> None:
    res = _auth_client().post(
        "/actions/rollover",
        headers=_hdr(),
        json={
            "name": "logs-write",
            "conditions": {"max_age": "7d"},
            "prefix": "logs-",
        },
    )
    assert res.status_code == 422


def test_index_settings_list_422() -> None:
    res = _auth_client().post(
        "/actions/index-settings",
        headers=_hdr(),
        json={"prefix": "logs-", "settings": []},
    )
    assert res.status_code == 422


def test_index_settings_empty_object_422() -> None:
    res = _auth_client().post(
        "/actions/index-settings",
        headers=_hdr(),
        json={"prefix": "logs-", "settings": {}},
    )
    assert res.status_code == 422


def test_cluster_routing_invalid_combo_422() -> None:
    with patch(
        "es_steward.api.app.run_cluster_routing",
        side_effect=ValueError("Invalid value"),
    ):
        res = _auth_client().post(
            "/actions/cluster-routing",
            headers=_hdr(),
            json={"routing_type": "allocation", "value": "replicas"},
        )
    assert res.status_code == 422


def test_cluster_routing_prefix_422() -> None:
    res = _auth_client().post(
        "/actions/cluster-routing",
        headers=_hdr(),
        json={
            "routing_type": "allocation",
            "value": "primaries",
            "prefix": "logs-",
        },
    )
    assert res.status_code == 422


def test_cluster_routing_setting_422() -> None:
    res = _auth_client().post(
        "/actions/cluster-routing",
        headers=_hdr(),
        json={
            "routing_type": "allocation",
            "value": "primaries",
            "setting": "enable",
        },
    )
    assert res.status_code == 422


def test_create_index_ignore_existing() -> None:
    with patch(
        "es_steward.api.app.run_create_index", return_value=("COMPLETED", 1)
    ) as run:
        res = _auth_client().post(
            "/actions/create-index",
            headers=_hdr(),
            json={"name": "logs-000001", "ignore_existing": True, "dry_run": True},
        )
    assert res.status_code == 200
    assert run.call_args.args[3] is True


def test_create_index_empty_name_422() -> None:
    with patch(
        "es_steward.api.app.run_create_index",
        side_effect=ValueError("name is required"),
    ):
        res = _auth_client().post(
            "/actions/create-index",
            headers=_hdr(),
            json={"name": ""},
        )
    assert res.status_code == 422


def test_create_index_prefix_422() -> None:
    res = _auth_client().post(
        "/actions/create-index",
        headers=_hdr(),
        json={"name": "logs-000001", "prefix": "logs-"},
    )
    assert res.status_code == 422


def test_delete_empty_prefix_422() -> None:
    with patch(
        "es_steward.api.app.run_delete", side_effect=ValueError("unbounded prefix")
    ):
        res = _auth_client().post(
            "/actions/delete", headers=_hdr(), json={"prefix": ""}
        )
    assert res.status_code == 422


def test_cold2frozen_empty_prefix_422() -> None:
    with patch(
        "es_steward.api.app.run_cold2frozen",
        side_effect=ValueError("unbounded prefix"),
    ):
        res = _auth_client().post(
            "/actions/cold2frozen", headers=_hdr(), json={"prefix": ""}
        )
    assert res.status_code == 422


def test_create_index_apierror_not_500() -> None:
    with patch("es_steward.api.app.run_create_index", side_effect=_api_error()):
        res = _auth_client().post(
            "/actions/create-index",
            headers=_hdr(),
            json={"name": "My Index"},
        )
    assert res.status_code == 400


def test_reindex_dest_in_source_422() -> None:
    with patch(
        "es_steward.api.app.run_reindex",
        side_effect=ValueError("dest must not be in the source set"),
    ):
        res = _auth_client().post(
            "/actions/reindex",
            headers=_hdr(),
            json={"prefix": "logs-", "dest": "logs-2026"},
        )
    assert res.status_code == 422


@pytest.mark.parametrize("suffix", ["delete", "close", "open"])
def test_prefix_dry_run_shared_schema(suffix: str) -> None:
    """acceptance D: delete/close/open accept {prefix, dry_run}; extra fields 422."""
    run = {"delete": "run_delete", "close": "run_close", "open": "run_open"}[suffix]
    with patch(f"es_steward.api.app.{run}", return_value=("COMPLETED", 1)):
        ok = _auth_client().post(
            f"/actions/{suffix}",
            headers=_hdr(),
            json={"prefix": "logs-", "dry_run": True},
        )
    assert ok.status_code == 200
    bad = _auth_client().post(
        f"/actions/{suffix}",
        headers=_hdr(),
        json={"prefix": "logs-", "dry_run": True, "bogus": 1},
    )
    assert bad.status_code == 422


def test_action_route_table_split() -> None:
    """acceptance A: OpenAPI has 18 ActionResponse POSTs; rollover is RolloverResponse."""
    spec = create_app(token="secret").openapi()
    action_names: list[str] = []
    rollover_name: str | None = None
    for path, item in spec["paths"].items():
        if not path.startswith("/actions/") or "post" not in item:
            continue
        schema = (
            item["post"]
            .get("responses", {})
            .get("200", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        ref = schema.get("$ref", "")
        name = ref.rsplit("/", 1)[-1] if ref else None
        if path == "/actions/rollover":
            rollover_name = name
        elif name == "ActionResponse":
            action_names.append(path)
    assert len(action_names) == 18
    assert rollover_name == "RolloverResponse"


def test_filter_preview_empty_filters_422() -> None:
    res = _auth_client().post(
        "/select/preview",
        headers=_hdr(),
        json={"filters": [], "limit": 10, "target": "index"},
    )
    assert res.status_code == 422


@pytest.mark.parametrize("limit", [10, 25, 50])
def test_filter_preview_truncates(limit: int) -> None:
    names = [f"logs-{i}" for i in range(40)]
    with (
        patch("es_steward.api.app.get_steward_client", return_value=MagicMock()),
        patch("es_steward.api.app.resolve", return_value=names),
    ):
        res = _auth_client().post(
            "/select/preview",
            headers=_hdr(),
            json={
                "filters": [
                    {"kind": "pattern", "pattern_kind": "prefix", "value": "logs-"}
                ],
                "limit": limit,
                "target": "index",
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["names"] == names[:limit]
    assert body["total"] == 40
    assert body["truncated"] is (40 > limit)
    assert body["limit"] == limit
    bad = _auth_client().post(
        "/select/preview",
        headers=_hdr(),
        json={
            "filters": [{"kind": "pattern", "pattern_kind": "prefix", "value": "logs-"}],
            "limit": 15,
            "target": "index",
        },
    )
    assert bad.status_code == 422


def test_filter_preview_first_filter_must_be_selector() -> None:
    with patch("es_steward.api.app.get_steward_client", return_value=MagicMock()):
        res = _auth_client().post(
            "/select/preview",
            headers=_hdr(),
            json={
                "filters": [{"kind": "size", "size_threshold_gb": 1}],
                "limit": 10,
                "target": "index",
            },
        )
    assert res.status_code == 422
    assert "first filter must be a selector" in str(res.json()["detail"])


def test_filter_preview_requires_token() -> None:
    res = _auth_client().post(
        "/select/preview",
        json={
            "filters": [{"kind": "pattern", "pattern_kind": "prefix", "value": "logs-"}],
            "limit": 10,
            "target": "index",
        },
    )
    assert res.status_code == 401


def test_filter_preview_snapshot_target() -> None:
    from pathlib import Path

    hits = [
        p
        for p in Path("src").rglob("*.py")
        if "SnapshotFilter" in p.read_text(encoding="utf-8")
    ]
    assert hits == []
    names = ["snap-1"]
    with (
        patch("es_steward.api.app.get_steward_client", return_value=MagicMock()),
        patch("es_steward.api.app.resolve", return_value=names) as resolve,
    ):
        res = _auth_client().post(
            "/select/preview",
            headers=_hdr(),
            json={
                "filters": [
                    {"kind": "pattern", "pattern_kind": "prefix", "value": "snap-"}
                ],
                "limit": 10,
                "target": "snapshot",
                "repository": "repo",
            },
        )
    assert res.status_code == 200
    assert res.json()["names"] == names
    assert resolve.call_args.args[0].target == "snapshot"
    assert resolve.call_args.args[0].repository == "repo"
    missing = _auth_client().post(
        "/select/preview",
        headers=_hdr(),
        json={
            "filters": [{"kind": "pattern", "pattern_kind": "prefix", "value": "snap-"}],
            "limit": 10,
            "target": "snapshot",
        },
    )
    assert missing.status_code == 422
    empty = _auth_client().post(
        "/select/preview",
        headers=_hdr(),
        json={
            "filters": [{"kind": "pattern", "pattern_kind": "prefix", "value": "snap-"}],
            "limit": 10,
            "target": "snapshot",
            "repository": "",
        },
    )
    assert empty.status_code == 422


class _FakeJournal:
    """Shared ES stand-in; keeps the index name so JOURNAL is assertable."""

    def __init__(self) -> None:
        self.docs: dict[tuple[str, str], dict[str, Any]] = {}
        self.index_calls: list[str] = []
        self.get_calls: list[str] = []

    def index(self, *, index: str, id: str, document: dict[str, Any]) -> dict[str, str]:
        self.index_calls.append(index)
        self.docs[(index, id)] = document
        return {"_id": id}

    def get(self, *, index: str, id: str) -> dict[str, Any]:
        self.get_calls.append(index)
        src = self.docs.get((index, id))
        if src is None:
            meta = MagicMock()
            meta.status = 404
            from elasticsearch9 import NotFoundError

            raise NotFoundError("not_found", meta, {})
        return {"found": True, "_id": id, "_source": src}

    def search(
        self, *, index: str, query: dict[str, Any], size: int, sort: object
    ) -> dict[str, Any]:
        del sort
        field = (query.get("exists") or {}).get("field")
        hits = [
            {"_id": doc_id, "_source": src}
            for (idx, doc_id), src in self.docs.items()
            if idx == index and field and field in src
        ]
        return {"hits": {"hits": hits[:size]}}


_SCRATCH_FILTERS = [{"kind": "pattern", "pattern_kind": "prefix", "value": "logs-"}]


def test_scratch_filter_roundtrip() -> None:
    fake = _FakeJournal()
    body = {"filters": _SCRATCH_FILTERS, "target": "index"}
    with patch("es_steward.api.app.get_steward_client", return_value=fake):
        first = TestClient(create_app(token="secret"))
        created = first.post("/select/scratch", headers=_hdr(), json=body)
        assert created.status_code == 201
        filter_id = created.json()["filter_id"]
        from uuid import UUID

        assert UUID(filter_id).version == 4
        assert fake.index_calls == [JOURNAL]
        stored = fake.docs[(JOURNAL, filter_id)]
        assert stored["filter_id"] == filter_id
        assert stored["target"] == "index"
        assert stored["filters"] == _SCRATCH_FILTERS
        assert "workbook_id" not in stored
        second = TestClient(create_app(token="secret"))
        got = second.get(f"/select/scratch/{filter_id}", headers=_hdr())
        assert got.status_code == 200
        assert got.json()["filters"] == _SCRATCH_FILTERS
        assert fake.get_calls == [JOURNAL]
        missing = second.get(
            "/select/scratch/00000000-0000-4000-8000-000000000000",
            headers=_hdr(),
        )
        assert missing.status_code == 404


def test_scratch_not_listed_as_workbook() -> None:
    fake = _FakeJournal()
    with (
        patch("es_steward.api.app.get_steward_client", return_value=fake),
        patch("es_steward.services.get_steward_client", return_value=fake),
    ):
        client = TestClient(create_app(token="secret"))
        created = client.post(
            "/select/scratch",
            headers=_hdr(),
            json={"filters": _SCRATCH_FILTERS, "target": "index"},
        )
        assert created.status_code == 201
        rows = client.get("/journal/workbooks", headers=_hdr())
    assert rows.status_code == 200
    assert rows.json() == []


def test_filter_preview_es_down_503() -> None:
    with patch(
        "es_steward.api.app.get_steward_client",
        side_effect=ESConnectionError("down"),
    ):
        res = _auth_client().post(
            "/select/preview",
            headers=_hdr(),
            json={
                "filters": _SCRATCH_FILTERS,
                "limit": 10,
                "target": "index",
            },
        )
    assert res.status_code == 503


def test_scratch_es_down_503() -> None:
    with patch(
        "es_steward.api.app.get_steward_client",
        side_effect=ESConnectionError("down"),
    ):
        posted = _auth_client().post(
            "/select/scratch",
            headers=_hdr(),
            json={"filters": _SCRATCH_FILTERS, "target": "index"},
        )
        gotten = _auth_client().get(
            "/select/scratch/00000000-0000-4000-8000-000000000000",
            headers=_hdr(),
        )
    assert posted.status_code == 503
    assert gotten.status_code == 503


def test_filter_preview_empty_filters_rejects_without_resolve() -> None:
    with patch("es_steward.api.app.resolve", return_value=["logs-1"]) as resolve:
        res = _auth_client().post(
            "/select/preview",
            headers=_hdr(),
            json={"filters": [], "limit": 10, "target": "index"},
        )
    assert res.status_code == 422
    resolve.assert_not_called()


def test_filter_preview_snapshot_repository_rejects_without_resolve() -> None:
    with patch("es_steward.api.app.resolve", return_value=["snap-1"]) as resolve:
        missing = _auth_client().post(
            "/select/preview",
            headers=_hdr(),
            json={
                "filters": _SCRATCH_FILTERS,
                "limit": 10,
                "target": "snapshot",
            },
        )
        empty = _auth_client().post(
            "/select/preview",
            headers=_hdr(),
            json={
                "filters": _SCRATCH_FILTERS,
                "limit": 10,
                "target": "snapshot",
                "repository": "",
            },
        )
    assert missing.status_code == 422
    assert empty.status_code == 422
    resolve.assert_not_called()


def test_filter_preview_unknown_key_422() -> None:
    res = _auth_client().post(
        "/select/preview",
        headers=_hdr(),
        json={
            "filters": _SCRATCH_FILTERS,
            "limit": 10,
            "target": "index",
            "bogus": 1,
        },
    )
    assert res.status_code == 422


def test_filter_preview_unknown_kind_422() -> None:
    res = _auth_client().post(
        "/select/preview",
        headers=_hdr(),
        json={
            "filters": [{"kind": "not_a_filter"}],
            "limit": 10,
            "target": "index",
        },
    )
    assert res.status_code == 422


def test_scratch_empty_filters_422() -> None:
    with patch("es_steward.api.app.resolve", return_value=["logs-1"]) as resolve:
        res = _auth_client().post(
            "/select/scratch",
            headers=_hdr(),
            json={"filters": [], "target": "index"},
        )
    assert res.status_code == 422
    resolve.assert_not_called()


def test_scratch_snapshot_repository_422() -> None:
    with patch("es_steward.api.app.resolve", return_value=["snap-1"]) as resolve:
        missing = _auth_client().post(
            "/select/scratch",
            headers=_hdr(),
            json={"filters": _SCRATCH_FILTERS, "target": "snapshot"},
        )
        empty = _auth_client().post(
            "/select/scratch",
            headers=_hdr(),
            json={
                "filters": _SCRATCH_FILTERS,
                "target": "snapshot",
                "repository": "",
            },
        )
    assert missing.status_code == 422
    assert empty.status_code == 422
    resolve.assert_not_called()


def test_scratch_not_process_global() -> None:
    fake_a = _FakeJournal()
    fake_b = _FakeJournal()
    with patch("es_steward.api.app.get_steward_client", return_value=fake_a):
        created = TestClient(create_app(token="secret")).post(
            "/select/scratch",
            headers=_hdr(),
            json={"filters": _SCRATCH_FILTERS, "target": "index"},
        )
    assert created.status_code == 201
    filter_id = created.json()["filter_id"]
    with patch("es_steward.api.app.get_steward_client", return_value=fake_b):
        got = TestClient(create_app(token="secret")).get(
            f"/select/scratch/{filter_id}",
            headers=_hdr(),
        )
    assert got.status_code == 404


def test_scratch_unknown_key_422() -> None:
    res = _auth_client().post(
        "/select/scratch",
        headers=_hdr(),
        json={"filters": _SCRATCH_FILTERS, "target": "index", "bogus": 1},
    )
    assert res.status_code == 422


def test_scratch_corrupt_source_404() -> None:
    fake = _FakeJournal()
    fake.docs[(JOURNAL, "bad-id")] = {"target": "index", "filters": _SCRATCH_FILTERS}
    with patch("es_steward.api.app.get_steward_client", return_value=fake):
        res = TestClient(create_app(token="secret")).get(
            "/select/scratch/bad-id",
            headers=_hdr(),
        )
    assert res.status_code == 404
