import sys
from enum import Enum, auto

if sys.version_info < (3, 11):

    class StrEnum(str, Enum):
        def _generate_next_value_(name, start, count, last_values) -> str:
            return name.lower()

        def __str__(self) -> str:
            return str(self.value)
else:
    from enum import StrEnum


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


class SmokeDefaultN(int): ...
