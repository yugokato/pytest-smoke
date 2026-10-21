from __future__ import annotations

import pytest

if pytest.version_tuple < (7, 4):
    from collections.abc import Mapping
    from typing import NamedTuple

    class TestShortLogReport(NamedTuple):
        category: str
        letter: str
        word: str | tuple[str, Mapping[str, bool]]
else:
    from pytest import TestShortLogReport  # type: ignore[no-redef] # noqa: F401
