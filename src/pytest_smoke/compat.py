from __future__ import annotations

import sys
from enum import Enum
from typing import Any

import pytest

if sys.version_info < (3, 11):

    class StrEnum(str, Enum):
        def _generate_next_value_(name: str, start: int, count: int, last_values: list[Any]) -> str:  # type: ignore[override]
            return name.lower()

        def __str__(self) -> str:
            return str(self.value)
else:
    from enum import StrEnum  # noqa: F401


if pytest.version_tuple < (7, 4):
    from collections.abc import Mapping
    from typing import NamedTuple

    class TestShortLogReport(NamedTuple):
        category: str
        letter: str
        word: str | tuple[str, Mapping[str, bool]]
else:
    from pytest import TestShortLogReport  # type: ignore[no-redef] # noqa: F401
