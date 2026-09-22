"""Steward predicates (size, ilm, opened, closed, count, none, plus FUT-2)."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator


class FilterBase(BaseModel):
    """Shared predicate fields."""

    exclude: bool = False


class SizeFilter(FilterBase):
    """Keep indices over/under a store-size threshold (GiB)."""

    kind: Literal["size"] = "size"
    size_threshold_gb: float
    threshold_behavior: Literal["greater_than", "less_than"] = "greater_than"
    size_behavior: Literal["primary", "total"] = "primary"


class IlmFilter(FilterBase):
    """ILM-managed predicate. Default exclude=True drops managed indices."""

    kind: Literal["ilm"] = "ilm"
    exclude: bool = True


class OpenedFilter(FilterBase):
    kind: Literal["opened"] = "opened"


class ClosedFilter(FilterBase):
    kind: Literal["closed"] = "closed"


class CountFilter(FilterBase):
    kind: Literal["count"] = "count"
    count: int = Field(ge=1)
    reverse: bool = True


class NoneFilter(FilterBase):
    kind: Literal["none"] = "none"


class AgeFilter(FilterBase):
    """Keep indices older/younger than ``unit_count`` ``unit``s."""

    kind: Literal["age"] = "age"
    source: Literal["name", "creation_date"] = "creation_date"
    direction: Literal["older", "younger"]
    unit: Literal["seconds", "minutes", "hours", "days", "weeks", "months", "years"]
    unit_count: int
    timestring: str | None = None
    epoch: int | None = None

    @model_validator(mode="after")
    def _timestring_if_name(self) -> Self:
        if self.source == "name" and not self.timestring:
            raise ValueError("timestring is required when source='name'")
        return self


class PeriodFilter(FilterBase):
    """Keep indices whose age falls in a relative or absolute window."""

    kind: Literal["period"] = "period"
    period_type: Literal["relative", "absolute"] = "relative"
    source: Literal["name", "creation_date"] = "creation_date"
    unit: Literal["seconds", "minutes", "hours", "days", "weeks", "months", "years"]
    range_from: int | None = None
    range_to: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    date_from_format: str | None = None
    date_to_format: str | None = None
    timestring: str | None = None
    week_starts_on: Literal["sunday", "monday"] = "sunday"
    epoch: int | None = None

    @model_validator(mode="after")
    def _period_args(self) -> Self:
        if self.source == "name" and not self.timestring:
            raise ValueError("timestring is required when source='name'")
        if self.period_type == "relative":
            if self.range_from is None or self.range_to is None:
                raise ValueError("range_from and range_to are required for relative period")
            if self.range_to < self.range_from:
                raise ValueError("range_to must be >= range_from")
            if self.unit not in {"hours", "days", "weeks", "months", "years"}:
                raise ValueError(
                    "relative period unit must be hours, days, weeks, months, or years"
                )
        else:
            if not all(
                (self.date_from, self.date_to, self.date_from_format, self.date_to_format)
            ):
                raise ValueError(
                    "absolute period requires date_from, date_to, "
                    "date_from_format, and date_to_format"
                )
        return self


class SpaceFilter(FilterBase):
    """Keep indices once cumulative store size crosses ``disk_space`` GiB."""

    kind: Literal["space"] = "space"
    disk_space: float = Field(gt=0)
    reverse: bool = True
    use_age: bool = False
    source: Literal["name", "creation_date"] = "creation_date"
    timestring: str | None = None
    threshold_behavior: Literal["greater_than", "less_than"] = "greater_than"

    @model_validator(mode="after")
    def _timestring_if_name(self) -> Self:
        if self.use_age and self.source == "name" and not self.timestring:
            raise ValueError("timestring is required when source='name'")
        return self


class EmptyFilter(FilterBase):
    """Empty-index predicate. Default exclude=True drops empty (and closed)."""

    kind: Literal["empty"] = "empty"
    exclude: bool = True


class ShardsFilter(FilterBase):
    """Keep indices by primary shard count."""

    kind: Literal["shards"] = "shards"
    number_of_shards: int = Field(ge=1)
    shard_filter_behavior: Literal[
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "equal",
    ] = "greater_than"


class AllocatedFilter(FilterBase):
    """Allocation-attribute predicate. Default exclude=True drops matches."""

    kind: Literal["allocated"] = "allocated"
    key: str
    value: str
    allocation_type: Literal["require", "include", "exclude"] = "require"
    exclude: bool = True


class ForcemergedFilter(FilterBase):
    """Forcemerged predicate. Default exclude=True drops already-merged."""

    kind: Literal["forcemerged"] = "forcemerged"
    max_num_segments: int = Field(ge=1)
    exclude: bool = True


class StateFilter(FilterBase):
    """Keep snapshots whose ``snapshot.get`` state matches."""

    # snapshot.get state only (ES 8/9). No COMPILING/ABORTED.
    kind: Literal["state"] = "state"
    state: Literal["SUCCESS", "PARTIAL", "FAILED", "IN_PROGRESS", "INCOMPATIBLE"]


Predicate = Annotated[
    SizeFilter
    | IlmFilter
    | OpenedFilter
    | ClosedFilter
    | CountFilter
    | NoneFilter
    | AgeFilter
    | PeriodFilter
    | SpaceFilter
    | EmptyFilter
    | ShardsFilter
    | AllocatedFilter
    | ForcemergedFilter
    | StateFilter,
    Field(discriminator="kind"),
]
