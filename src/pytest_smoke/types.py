from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytest import Item

from pytest_smoke.compat import StrEnum


class SmokeEnvVar(StrEnum):
    SMOKE_TEST_SESSION_UUID = auto()


class SmokeScope(StrEnum):
    FUNCTION = auto()
    CLASS = auto()
    AUTO = auto()
    FILE = auto()
    ALL = auto()


class SmokeIniOption(StrEnum):
    SMOKE_DEFAULT_N = auto()
    SMOKE_DEFAULT_SCOPE = auto()
    SMOKE_DEFAULT_XDIST_DIST_BY_SCOPE = auto()
    SMOKE_MARKED_TESTS_AS_CRITICAL = auto()


class SmokeDefaultN(int): ...


@dataclass
class MustpassCounter:
    selected: set[Item] = field(default_factory=set)
    failed: set[Item] = field(default_factory=set)


@dataclass
class SmokeCounter:
    collected: Counter = field(default_factory=Counter)
    selected: Counter = field(default_factory=Counter)
    mustpass: MustpassCounter = field(default_factory=MustpassCounter)
