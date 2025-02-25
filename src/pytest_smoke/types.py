from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import auto
from functools import cached_property
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pytest import Config, Item

from pytest_smoke.compat import StrEnum


class SmokeEnvVar(StrEnum):
    SMOKE_TEST_SESSION_UUID = auto()


class SmokeScope(StrEnum):
    FUNCTION = auto()
    CLASS = auto()
    AUTO = auto()
    FILE = auto()
    DIRECTORY = auto()
    ALL = auto()


class SmokeSelectMode(StrEnum):
    FIRST = auto()
    LAST = auto()
    RANDOM = auto()


class SmokeIniOption(StrEnum):
    SMOKE_DEFAULT_N = auto()
    SMOKE_DEFAULT_SCOPE = auto()
    SMOKE_DEFAULT_SELECT_MODE = auto()
    SMOKE_DEFAULT_XDIST_DIST_BY_SCOPE = auto()
    SMOKE_MARKED_TESTS_AS_CRITICAL = auto()


class SmokeDefaultN(int): ...


class SmokeOption:
    def __init__(self, config: Config):
        self.config = config

    @cached_property
    def n(self) -> int | str | None:
        if n := self.config.option.smoke:
            if isinstance(n, SmokeDefaultN):
                # N was not explicitly provided to the option. Apply the INI config value or the plugin default
                n = self._parse_ini_option(SmokeIniOption.SMOKE_DEFAULT_N)
            return n
        return None

    @cached_property
    def scope(self) -> str:
        scope = self.config.option.smoke_scope or self._parse_ini_option(SmokeIniOption.SMOKE_DEFAULT_SCOPE)
        assert scope and isinstance(scope, str)
        return scope

    @cached_property
    def select_mode(self) -> str:
        mode = self.config.option.smoke_select_mode or self._parse_ini_option(SmokeIniOption.SMOKE_DEFAULT_SELECT_MODE)
        assert mode and isinstance(mode, str)
        return mode

    @cached_property
    def is_scale(self) -> bool:
        return isinstance(self.n, str) and self.n.endswith("%")

    def _parse_ini_option(self, option: SmokeIniOption) -> str | int | float | bool:
        from pytest_smoke.utils import parse_ini_option

        return parse_ini_option(self.config, option)


class SmokeMarker:
    def __init__(self, *args: Any, mustpass: bool = False, runif: bool = True, **kwargs: Any) -> None:
        self.mustpass = bool(mustpass)
        self.runif = bool(runif)

    @classmethod
    def from_item(cls, item: Item) -> SmokeMarker | None:
        if marker := item.get_closest_marker("smoke"):
            return cls(*marker.args, **marker.kwargs)
        return None


@dataclass
class MustpassCounter:
    selected: set[Item] = field(default_factory=set)
    failed: set[Item] = field(default_factory=set)


@dataclass
class SmokeCounter:
    collected: Counter[str] = field(default_factory=Counter)
    selected: Counter[str] = field(default_factory=Counter)
    mustpass: MustpassCounter = field(default_factory=MustpassCounter)
