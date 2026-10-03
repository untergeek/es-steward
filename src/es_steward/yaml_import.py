"""One-way Curator 8 actions YAML → Steward selectors/predicates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import yaml
from es_mgmt.select import AliasFilter, PatternFilter

from es_steward.select import (
    AgeFilter,
    AllocatedFilter,
    ClosedFilter,
    CountFilter,
    EmptyFilter,
    ForcemergedFilter,
    IlmFilter,
    NoneFilter,
    OpenedFilter,
    PeriodFilter,
    ShardsFilter,
    SizeFilter,
    SpaceFilter,
    StateFilter,
)


@dataclass(frozen=True)
class ImportedAction:
    """One Curator action block mapped to Steward filters.

    Top-level ``filters`` (delete/close/…) land on ``filters``. Alias-style
    ``add.filters`` / ``remove.filters`` land on ``add`` / ``remove`` and are
    never folded into ``filters``. Alias ``options.name`` / ``extra_settings``
    land on ``name`` / ``extra_settings``.
    """

    action: str
    filters: list[Any]
    cli: list[str] | None
    add: list[Any] | None = None
    remove: list[Any] | None = None
    name: str | None = None
    extra_settings: dict[str, Any] | None = None


def load_actions(path: str | Path) -> list[ImportedAction]:
    """Read a Curator 8 actions file and return Steward filter lists.

    Args:
        path: Filesystem path to a Curator ``actions:`` YAML file.

    Returns:
        Imported actions in file order.

    Raises:
        ValueError: If the YAML is not a Curator actions file or a filter
            cannot be expressed as a Steward selector/predicate.
        OSError: If ``path`` cannot be read.
    """
    return parse_actions(Path(path).read_text(encoding="utf-8"))


def parse_actions(text: str) -> list[ImportedAction]:
    """Parse Curator 8 actions YAML text into Steward filters.

    Args:
        text: YAML document with an ``actions`` mapping.

    Returns:
        Imported actions in key order.

    Raises:
        ValueError: If the document or a filter is unsupported.
    """
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise TypeError("expected a Curator actions YAML mapping")
    actions = loaded.get("actions")
    if actions is None:
        raise ValueError("expected a Curator actions YAML mapping")
    if not isinstance(actions, dict):
        raise TypeError("expected a Curator actions YAML mapping")
    out: list[ImportedAction] = []
    for key in _action_keys(actions):
        block = actions[key]
        if not isinstance(block, dict):
            raise TypeError(f"action {key!r} is not a mapping")
        action = str(block.get("action") or "")
        if not action:
            raise ValueError(f"action {key!r} is missing 'action'")
        filters = _convert_list(block.get("filters"), key)
        add = _nested_filters(block, "add", key)
        remove = _nested_filters(block, "remove", key)
        name, extra_settings = _alias_options(block, action, key)
        out.append(
            ImportedAction(
                action=action,
                filters=filters,
                cli=_cli(filters),
                add=add,
                remove=remove,
                name=name,
                extra_settings=extra_settings,
            )
        )
    return out


def _action_keys(actions: dict[Any, Any]) -> list[Any]:
    def sort_key(k: Any) -> tuple[int, int | str]:
        try:
            return (0, int(k))
        except (TypeError, ValueError):
            return (1, str(k))

    return sorted(actions, key=sort_key)


def _convert_list(raw: Any, action_key: Any) -> list[Any]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError("filters must be a list")
    return [_convert(f, action_key) for f in raw]


def _nested_filters(block: dict[str, Any], nest: str, action_key: Any) -> list[Any] | None:
    nested = block.get(nest)
    if nested is None:
        return None
    if not isinstance(nested, dict):
        raise TypeError(f"{nest} must be a mapping")
    return _convert_list(nested.get("filters"), action_key)


def _alias_options(
    block: dict[str, Any], action: str, key: Any
) -> tuple[str | None, dict[str, Any] | None]:
    raw = block.get("options")
    if raw is None:
        name, extra = None, None
    elif not isinstance(raw, dict):
        raise TypeError("options must be a mapping")
    else:
        name = str(raw["name"]) if _present(raw, "name") else None
        extra_raw = raw.get("extra_settings")
        if extra_raw is None or extra_raw == "":
            extra = None
        elif not isinstance(extra_raw, dict):
            raise TypeError("extra_settings must be a mapping")
        else:
            extra = extra_raw
    if action == "alias" and not name:
        raise ValueError(f"action {key!r}: alias requires options.name")
    return name, extra


def _present(data: dict[str, Any], key: str) -> bool:
    val = data.get(key)
    return val is not None and val != ""


# Curator 8 defaults when the YAML key is missing or blank.
_CURATOR_EXCLUDE_DEFAULT: dict[str, bool] = {
    "opened": True,
    "closed": True,
    "count": True,
    "allocated": True,
    "forcemerged": True,
    "ilm": True,
    "empty": True,
    "kibana": True,
}


def _exclude(data: dict[str, Any], filtertype: str) -> dict[str, Any]:
    if _present(data, "exclude"):
        return {"exclude": bool(data["exclude"])}
    if filtertype in _CURATOR_EXCLUDE_DEFAULT:
        return {"exclude": _CURATOR_EXCLUDE_DEFAULT[filtertype]}
    return {}


def _unsupported(reason: str) -> NoReturn:
    raise ValueError(reason)


def _convert(raw: Any, action_key: Any) -> Any:
    if not isinstance(raw, dict) or not raw.get("filtertype"):
        raise ValueError(f"action {action_key!r} has a filter without filtertype")
    kind = str(raw["filtertype"])
    if kind not in _FILTERS:
        _unsupported(f"unsupported filtertype: {kind}")
    return _FILTERS[kind](raw)


def _pattern(data: dict[str, Any]) -> PatternFilter:
    kind = data.get("kind")
    if kind == "timestring":
        _unsupported("pattern kind timestring is not supported; use age or period")
    if kind not in ("prefix", "suffix", "regex"):
        _unsupported(f"unsupported pattern kind: {kind}")
    if not _present(data, "value"):
        raise ValueError("pattern filter requires value")
    return PatternFilter(pattern_kind=kind, value=str(data["value"]), **_exclude(data, "pattern"))


def _alias(data: dict[str, Any]) -> AliasFilter:
    aliases = data.get("aliases")
    if isinstance(aliases, str) and aliases:
        names = [aliases]
    elif isinstance(aliases, list) and aliases:
        names = [str(a) for a in aliases]
    else:
        raise ValueError("alias filter requires aliases")
    return AliasFilter(aliases=names, **_exclude(data, "alias"))


def _age(data: dict[str, Any]) -> AgeFilter:
    if data.get("source") == "field_stats":
        _unsupported("age source field_stats is not supported")
    if _present(data, "unit_count_pattern"):
        _unsupported("age unit_count_pattern is not supported")
    kw: dict[str, Any] = {**_exclude(data, "age")}
    for key in ("source", "direction", "unit", "timestring"):
        if _present(data, key):
            kw[key] = data[key]
    if _present(data, "unit_count"):
        kw["unit_count"] = int(data["unit_count"])
    if _present(data, "epoch"):
        kw["epoch"] = int(data["epoch"])
    if not _present(data, "source"):
        kw["source"] = "name"
    if kw.get("source") == "name" and not _present(data, "timestring"):
        kw["timestring"] = "%Y.%m.%d"
    return AgeFilter(**kw)


def _period(data: dict[str, Any]) -> PeriodFilter:
    if data.get("source") == "field_stats":
        _unsupported("period source field_stats is not supported")
    if data.get("intersect"):
        _unsupported("period intersect is not supported")
    kw: dict[str, Any] = {**_exclude(data, "period")}
    for key in (
        "period_type",
        "source",
        "unit",
        "timestring",
        "date_from",
        "date_to",
        "date_from_format",
        "date_to_format",
        "week_starts_on",
    ):
        if _present(data, key):
            kw[key] = data[key]
    for key in ("range_from", "range_to", "epoch"):
        if _present(data, key):
            kw[key] = int(data[key])
    if not _present(data, "source"):
        kw["source"] = "name"
    if kw.get("source") == "name" and not _present(data, "timestring"):
        kw["timestring"] = "%Y.%m.%d"
    return PeriodFilter(**kw)


def _space(data: dict[str, Any]) -> SpaceFilter:
    if not _present(data, "disk_space"):
        raise ValueError("space filter requires disk_space")
    kw: dict[str, Any] = {"disk_space": float(data["disk_space"]), **_exclude(data, "space")}
    if _present(data, "reverse"):
        kw["reverse"] = bool(data["reverse"])
    if _present(data, "use_age"):
        kw["use_age"] = bool(data["use_age"])
    for key in ("source", "timestring", "threshold_behavior"):
        if _present(data, key):
            kw[key] = data[key]
    return SpaceFilter(**kw)


def _size(data: dict[str, Any]) -> SizeFilter:
    if not _present(data, "size_threshold"):
        raise ValueError("size filter requires size_threshold")
    kw: dict[str, Any] = {
        "size_threshold_gb": float(data["size_threshold"]),
        **_exclude(data, "size"),
    }
    for key in ("threshold_behavior", "size_behavior"):
        if _present(data, key):
            kw[key] = data[key]
    return SizeFilter(**kw)


def _count(data: dict[str, Any]) -> CountFilter:
    if data.get("use_age"):
        _unsupported("count use_age is not supported")
    if _present(data, "pattern"):
        _unsupported("count pattern groups are not supported")
    if not _present(data, "count"):
        raise ValueError("count filter requires count")
    kw: dict[str, Any] = {"count": int(data["count"]), **_exclude(data, "count")}
    if _present(data, "reverse"):
        kw["reverse"] = bool(data["reverse"])
    return CountFilter(**kw)


def _shards(data: dict[str, Any]) -> ShardsFilter:
    if not _present(data, "number_of_shards"):
        raise ValueError("shards filter requires number_of_shards")
    kw: dict[str, Any] = {
        "number_of_shards": int(data["number_of_shards"]),
        **_exclude(data, "shards"),
    }
    if _present(data, "shard_filter_behavior"):
        kw["shard_filter_behavior"] = data["shard_filter_behavior"]
    return ShardsFilter(**kw)


def _allocated(data: dict[str, Any]) -> AllocatedFilter:
    if not _present(data, "key") or not _present(data, "value"):
        raise ValueError("allocated filter requires key and value")
    kw: dict[str, Any] = {
        "key": str(data["key"]),
        "value": str(data["value"]),
        **_exclude(data, "allocated"),
    }
    if _present(data, "allocation_type"):
        kw["allocation_type"] = data["allocation_type"]
    return AllocatedFilter(**kw)


def _forcemerged(data: dict[str, Any]) -> ForcemergedFilter:
    if not _present(data, "max_num_segments"):
        raise ValueError("forcemerged filter requires max_num_segments")
    return ForcemergedFilter(
        max_num_segments=int(data["max_num_segments"]), **_exclude(data, "forcemerged")
    )


def _snapshot_state(data: dict[str, Any]) -> StateFilter:
    if not _present(data, "state"):
        raise ValueError("state filter requires state")
    return StateFilter(state=str(data["state"]).upper(), **_exclude(data, "state"))


def _kibana(data: dict[str, Any]) -> PatternFilter:
    return PatternFilter(
        pattern_kind="prefix", value=".kibana", **_exclude(data, "kibana")
    )


def _flag(cls: type, data: dict[str, Any], filtertype: str) -> Any:
    return cls(**_exclude(data, filtertype))


_FILTERS = {
    "pattern": _pattern,
    "alias": _alias,
    "age": _age,
    "period": _period,
    "space": _space,
    "size": _size,
    "count": _count,
    "shards": _shards,
    "allocated": _allocated,
    "forcemerged": _forcemerged,
    "empty": lambda d: _flag(EmptyFilter, d, "empty"),
    "opened": lambda d: _flag(OpenedFilter, d, "opened"),
    "closed": lambda d: _flag(ClosedFilter, d, "closed"),
    "ilm": lambda d: _flag(IlmFilter, d, "ilm"),
    "none": lambda d: NoneFilter(),
    "kibana": _kibana,
    "state": _snapshot_state,
}


def _cli(filters: list[Any]) -> list[str] | None:
    if not filters:
        return None
    first = filters[0]
    if (
        not isinstance(first, PatternFilter)
        or first.pattern_kind != "prefix"
        or first.exclude
    ):
        return None
    flags = ["show", "--prefix", first.value]
    rest = filters[1:]
    if not rest:
        return flags
    if len(rest) == 1 and isinstance(rest[0], SizeFilter):
        size = rest[0]
        if (
            size.threshold_behavior == "greater_than"
            and size.size_behavior == "primary"
            and not size.exclude
        ):
            return [*flags, "--size-gt", str(size.size_threshold_gb)]
    return None


def to_json(actions: list[ImportedAction]) -> list[dict[str, Any]]:
    """Serialize imported actions (filter ``model_dump`` + optional CLI flags)."""
    return [
        {
            "action": a.action,
            "filters": [f.model_dump() for f in a.filters],
            "cli": a.cli,
            "add": None if a.add is None else [f.model_dump() for f in a.add],
            "remove": None if a.remove is None else [f.model_dump() for f in a.remove],
            "name": a.name,
            "extra_settings": a.extra_settings,
        }
        for a in actions
    ]
