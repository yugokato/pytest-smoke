from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache


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
