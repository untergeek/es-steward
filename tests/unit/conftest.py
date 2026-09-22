"""Shared unit-test stand-ins."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest


class FakeRun:
    """ActionRun stand-in. Records persist, dry_run, action, names, and run kwargs."""

    last: ClassVar[FakeRun | None] = None

    def __init__(
        self,
        *args: object,
        persist: bool = False,
        dry_run: bool = False,
        **kwargs: object,
    ) -> None:
        del args, kwargs
        self.persist = persist
        self.dry_run = dry_run
        self.action: object = None
        self.names: object = None
        self.kwargs: dict[str, Any] = {}
        FakeRun.last = self

    def run(
        self, action: object = None, names: object = None, **kwargs: object
    ) -> object:
        self.action = action
        self.names = names
        self.kwargs = dict(kwargs)
        return SimpleNamespace(status="COMPLETED", results=[])


@pytest.fixture(autouse=True)
def _reset_fake_run() -> Iterator[None]:
    FakeRun.last = None
    yield
    FakeRun.last = None
