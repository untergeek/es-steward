"""Resolve selectors (es_tools) then Steward predicates."""

from __future__ import annotations

from typing import Any

from es_tools.select import SelectContext, Selector, apply_filters

from es_steward import JOURNAL

from .models import Predicate
from .predicates import apply_predicates

_SELECTOR_KINDS = {"pattern", "alias", "query", "data_stream", "snapshot_indices"}


def resolve(ctx: SelectContext, filters: list[Any]) -> list[str]:
    """Run selectors then predicates. First filter must be a selector."""
    if not filters:
        raise ValueError("filters must be non-empty")
    if getattr(filters[0], "kind", None) not in _SELECTOR_KINDS:
        raise ValueError("first filter must be a selector")
    if not ctx.protect:
        ctx.protect = frozenset({JOURNAL})
    selectors: list[Selector] = []
    predicates: list[Predicate] = []
    saw_predicate = False
    for f in filters:
        kind = getattr(f, "kind", "")
        if kind in _SELECTOR_KINDS:
            if saw_predicate:
                raise ValueError("selectors cannot follow predicates")
            selectors.append(f)
        else:
            saw_predicate = True
            predicates.append(f)
    names = apply_filters(ctx, selectors)
    if predicates:
        names = apply_predicates(ctx, names, predicates)
    return names
