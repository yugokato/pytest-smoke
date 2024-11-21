from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache


@lru_cache
def calculate_scaled_value(total: float, percentage: float, precision: int = 0, min_value: int = 1) -> float:
    """Calculates a scaled value with rounding

    :param total: The total value to calculate the percentage from
    :param percentage: The percentage to apply to the total
    :param precision: The number of decimal places to round to
    :param min_value: The minimum allowed value after calculation
    """
    val = _round_half_up(total * percentage / 100, precision)
    return max(val, min_value)


def _round_half_up(x: float, precision: int) -> float:
    return float(Decimal(str(x)).quantize(Decimal("10") ** -precision, rounding=ROUND_HALF_UP))
