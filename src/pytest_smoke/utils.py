import sys
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from functools import lru_cache

if sys.version_info.major == 3 and sys.version_info.minor < 11:

    class StrEnum(str, Enum):
        def _generate_next_value_(name, start, count, last_values) -> str:
            return name.lower()

        def __str__(self) -> str:
            return str(self.value)
else:
    from enum import StrEnum  # noqa: F401


@lru_cache
def scale_down(value: float, percentage: float, precision: int = 0, min_value: int = 1) -> float:
    """Scales down a value with rounding

    :param value: The current value to calculate the percentage from
    :param percentage: The percentage to apply to the current value
    :param precision: The number of decimal places to round to
    :param min_value: The minimum allowed value after calculation
    """
    if percentage > 100:
        raise ValueError("The percentage must be 100 or smaller")
    val = _round_half_up(value * percentage / 100, precision)
    return max(val, min_value)


def _round_half_up(x: float, precision: int) -> float:
    return float(Decimal(str(x)).quantize(Decimal("10") ** -precision, rounding=ROUND_HALF_UP))
