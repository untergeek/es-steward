"""Tests for Curator 8 YAML → Steward filter import."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from es_tools.select import AliasFilter, PatternFilter
from pydantic import ValidationError

from es_steward.cli import main
from es_steward.select import (
    AgeFilter,
    AllocatedFilter,
    ClosedFilter,
    CountFilter,
    EmptyFilter,
    ForcemergedFilter,
    OpenedFilter,
    PeriodFilter,
    ShardsFilter,
    SizeFilter,
    SpaceFilter,
    StateFilter,
)
from es_steward.yaml_import import parse_actions, to_json

_DELETE = """
actions:
  1:
    action: delete_indices
    options:
      disable_action: True
    filters:
    - filtertype: pattern
      kind: prefix
      value: logstash-
      exclude:
    - filtertype: age
      source: name
      direction: older
      timestring: '%Y.%m.%d'
      unit: days
      unit_count: 45
      exclude:
"""


def test_delete_indices_emits_prefix_and_age() -> None:
    actions = parse_actions(_DELETE)
    assert len(actions) == 1
    assert actions[0].action == "delete_indices"
    assert actions[0].cli is None
    prefix, age = actions[0].filters
    assert isinstance(prefix, PatternFilter)
    assert prefix.pattern_kind == "prefix"
    assert prefix.value == "logstash-"
    assert prefix.exclude is False
    assert isinstance(age, AgeFilter)
    assert age.source == "name"
    assert age.direction == "older"
    assert age.timestring == "%Y.%m.%d"
    assert age.unit == "days"
    assert age.unit_count == 45


def test_prefix_only_emits_show_cli() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: pattern
      kind: prefix
      value: logs-
"""
    )
    assert actions[0].cli == ["show", "--prefix", "logs-"]


def test_prefix_and_size_emits_size_gt() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: pattern
      kind: prefix
      value: logs-
    - filtertype: size
      size_threshold: 50
"""
    )
    assert actions[0].cli == ["show", "--prefix", "logs-", "--size-gt", "50.0"]
    assert isinstance(actions[0].filters[1], SizeFilter)
    assert actions[0].filters[1].size_threshold_gb == 50.0


def test_empty_omitted_exclude_uses_steward_default() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: pattern
      kind: prefix
      value: logs-
    - filtertype: empty
"""
    )
    assert isinstance(actions[0].filters[1], EmptyFilter)
    assert actions[0].filters[1].exclude is True


def test_alias_string_becomes_list() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: alias
      aliases: last_week
"""
    )
    assert isinstance(actions[0].filters[0], AliasFilter)
    assert actions[0].filters[0].aliases == ["last_week"]


def test_kibana_is_prefix_exclude() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: kibana
"""
    )
    kib = actions[0].filters[0]
    assert isinstance(kib, PatternFilter)
    assert kib.value == ".kibana"
    assert kib.exclude is True


def test_field_stats_raises() -> None:
    with pytest.raises(ValueError, match="field_stats"):
        parse_actions(
            """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: age
      source: field_stats
      direction: older
      unit: days
      unit_count: 1
      field: '@timestamp'
"""
        )


def test_timestring_pattern_raises() -> None:
    with pytest.raises(ValueError, match="timestring"):
        parse_actions(
            """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: pattern
      kind: timestring
      value: '%Y.%m.%d'
"""
        )


def test_missing_actions_raises() -> None:
    with pytest.raises(ValueError, match="actions"):
        parse_actions("foo: 1\n")


def test_cli_import_yaml_prints_json(tmp_path: Path) -> None:
    path = tmp_path / "actions.yml"
    path.write_text(_DELETE, encoding="utf-8")
    result = CliRunner().invoke(main, ["import-yaml", str(path)])
    assert result.exit_code == 0, result.output
    payload = to_json(parse_actions(_DELETE))
    assert '"action": "delete_indices"' in result.output
    assert payload[0]["filters"][0]["kind"] == "pattern"
    assert payload[0]["filters"][1]["kind"] == "age"
    assert payload[0]["add"] is None
    assert payload[0]["remove"] is None


def test_alias_add_and_remove_are_kept_separate() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: alias
    options:
      name: last_week
    add:
      filters:
      - filtertype: pattern
        kind: prefix
        value: logstash-
      - filtertype: age
        source: name
        direction: older
        timestring: '%Y.%m.%d'
        unit: days
        unit_count: 7
    remove:
      filters:
      - filtertype: pattern
        kind: prefix
        value: logstash-
      - filtertype: age
        source: name
        direction: older
        timestring: '%Y.%m.%d'
        unit: days
        unit_count: 14
"""
    )
    imported = actions[0]
    assert imported.action == "alias"
    assert imported.filters == []
    assert imported.cli is None
    assert imported.add is not None and imported.remove is not None
    assert isinstance(imported.add[0], PatternFilter)
    assert isinstance(imported.add[1], AgeFilter)
    assert imported.add[1].unit_count == 7
    assert isinstance(imported.remove[0], PatternFilter)
    assert isinstance(imported.remove[1], AgeFilter)
    assert imported.remove[1].unit_count == 14
    payload = to_json(actions)[0]
    assert payload["add"] is not None and payload["remove"] is not None
    assert payload["add"][1]["unit_count"] == 7
    assert payload["remove"][1]["unit_count"] == 14


def test_space_shards_allocated_forcemerged_period() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: space
      disk_space: 100
      reverse: False
      use_age: True
      source: creation_date
    - filtertype: shards
      number_of_shards: 5
      shard_filter_behavior: greater_than_or_equal
    - filtertype: allocated
      key: tag
      value: hot
      allocation_type: require
    - filtertype: forcemerged
      max_num_segments: 2
    - filtertype: period
      source: name
      timestring: '%Y.%m.%d'
      unit: days
      range_from: -1
      range_to: -1
"""
    )
    space, shards, allocated, merged, period = actions[0].filters
    assert isinstance(space, SpaceFilter)
    assert space.disk_space == 100
    assert space.reverse is False
    assert space.use_age is True
    assert space.source == "creation_date"
    assert isinstance(shards, ShardsFilter)
    assert shards.number_of_shards == 5
    assert shards.shard_filter_behavior == "greater_than_or_equal"
    assert isinstance(allocated, AllocatedFilter)
    assert allocated.key == "tag"
    assert allocated.value == "hot"
    assert allocated.allocation_type == "require"
    assert isinstance(merged, ForcemergedFilter)
    assert merged.max_num_segments == 2
    assert isinstance(period, PeriodFilter)
    assert period.source == "name"
    assert period.timestring == "%Y.%m.%d"
    assert period.range_from == -1
    assert period.range_to == -1
    assert period.unit == "days"


def test_opened_omitted_exclude_is_curator_true() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: opened
"""
    )
    assert isinstance(actions[0].filters[0], OpenedFilter)
    assert actions[0].filters[0].exclude is True


def test_closed_blank_exclude_is_curator_true() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: closed
      exclude:
"""
    )
    assert isinstance(actions[0].filters[0], ClosedFilter)
    assert actions[0].filters[0].exclude is True


def test_count_omitted_exclude_is_curator_true() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: count
      count: 2
"""
    )
    assert isinstance(actions[0].filters[0], CountFilter)
    assert actions[0].filters[0].exclude is True
    assert actions[0].filters[0].count == 2


def test_age_omitted_source_is_name_when_timestring_present() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: age
      direction: younger
      timestring: '%Y.%m.%d'
      unit: days
      unit_count: 14
"""
    )
    age = actions[0].filters[0]
    assert isinstance(age, AgeFilter)
    assert age.source == "name"
    assert age.timestring == "%Y.%m.%d"


def test_age_omitted_source_defaults_curator_timestring() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: age
      direction: older
      unit: days
      unit_count: 14
"""
    )
    age = actions[0].filters[0]
    assert isinstance(age, AgeFilter)
    assert age.source == "name"
    assert age.timestring == "%Y.%m.%d"
    assert age.unit_count == 14


def test_count_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_actions(
            """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: count
      count: -3
"""
        )


def test_state_filter_imports() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_snapshots
    filters:
    - filtertype: state
      state: SUCCESS
"""
    )
    st = actions[0].filters[0]
    assert isinstance(st, StateFilter)
    assert st.state == "SUCCESS"
    assert st.exclude is False


def test_alias_options_name_is_kept() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: alias
    options:
      name: last_week
    add:
      filters:
      - filtertype: pattern
        kind: prefix
        value: logstash-
"""
    )
    assert actions[0].name == "last_week"
    assert actions[0].extra_settings is None
    payload = to_json(actions)[0]
    assert payload["name"] == "last_week"
    assert payload["extra_settings"] is None


def test_alias_extra_settings_kept() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: alias
    options:
      name: last_week
      extra_settings:
        is_write_index: true
    add:
      filters:
      - filtertype: pattern
        kind: prefix
        value: logstash-
"""
    )
    assert actions[0].extra_settings == {"is_write_index": True}


def test_alias_missing_name_raises() -> None:
    with pytest.raises(ValueError, match="name"):
        parse_actions(
            """
actions:
  1:
    action: alias
    add:
      filters:
      - filtertype: pattern
        kind: prefix
        value: logstash-
"""
        )


def test_alias_blank_name_raises() -> None:
    with pytest.raises(ValueError, match="name"):
        parse_actions(
            """
actions:
  1:
    action: alias
    options:
      name: ""
    add:
      filters:
      - filtertype: pattern
        kind: prefix
        value: logstash-
"""
        )


def test_alias_options_not_mapping_raises() -> None:
    with pytest.raises(TypeError, match="options"):
        parse_actions(
            """
actions:
  1:
    action: alias
    options: last_week
    add:
      filters:
      - filtertype: pattern
        kind: prefix
        value: logstash-
"""
        )


def test_delete_without_options_name_is_none() -> None:
    actions = parse_actions(
        """
actions:
  1:
    action: delete_indices
    filters:
    - filtertype: pattern
      kind: prefix
      value: logstash-
"""
    )
    assert actions[0].name is None
    assert actions[0].extra_settings is None
