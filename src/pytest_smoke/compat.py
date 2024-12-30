import sys
from enum import Enum

import pytest

if sys.version_info < (3, 11):

    class StrEnum(str, Enum):
        def _generate_next_value_(name, start, count, last_values) -> str:
            return name.lower()

        def __str__(self) -> str:
            return str(self.value)
else:
    from enum import StrEnum  # noqa: F401


if pytest.version_tuple < (7, 4):
    from collections.abc import Mapping
    from typing import NamedTuple, Union

    class TestShortLogReport(NamedTuple):
        category: str
        letter: str
        word: Union[str, tuple[str, Mapping[str, bool]]]
else:
    from pytest import TestShortLogReport  # noqa: F401
