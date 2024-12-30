from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import TYPE_CHECKING, Optional, Union

import pytest

if TYPE_CHECKING:
    from pytest import Config, Item

from pytest_smoke.types import SmokeIniOption, SmokeScope


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


@lru_cache
def generate_group_id(item: Item, scope: str) -> Optional[str]:
    assert scope
    if item.config.hook.pytest_smoke_exclude(item=item, scope=scope):
        return

    if (group_id := item.config.hook.pytest_smoke_generate_group_id(item=item, scope=scope)) is not None:
        return group_id

    if scope not in [str(x) for x in SmokeScope]:
        raise pytest.UsageError(
            f"The logic for the custom scope '{scope}' must be implemented using the "
            f"pytest_smoke_generate_group_id hook"
        )

    if scope == SmokeScope.ALL:
        return "*"

    cls = getattr(item, "cls", None)
    if not cls and scope == SmokeScope.CLASS:
        return

    group_id = str(item.path or item.location[0])
    if scope == SmokeScope.FILE:
        return group_id

    if cls:
        group_id += f"::{cls.__name__}"
        if scope in [SmokeScope.CLASS, SmokeScope.AUTO]:
            return group_id

    # The default scope
    func_name = item.function.__name__  # type: ignore
    group_id += f"::{func_name}"
    return group_id


def parse_n(value: str) -> Union[int, str]:
    v = value.strip()
    try:
        if is_scale := v.endswith("%"):
            num = float(v[:-1])
        else:
            num = int(v)

        if num < 1 or is_scale and num > 100:
            raise ValueError

        if is_scale:
            return f"{num}%"
        else:
            return num
    except ValueError:
        raise pytest.UsageError(
            f"The smoke N value must be a positive number or a valid percentage. '{value}' was given."
        )


def parse_scope(value: str) -> str:
    if (v := value.strip()) == "":
        raise pytest.UsageError(f"Invalid scope: '{value}'")
    return v


def parse_ini_option(config: Config, option: SmokeIniOption) -> Union[str, int, bool]:
    try:
        v = config.getini(option)
        if option == SmokeIniOption.SMOKE_DEFAULT_N:
            return parse_n(v)
        elif option == SmokeIniOption.SMOKE_DEFAULT_SCOPE:
            return parse_scope(v)
        else:
            return v
    except ValueError as e:
        raise pytest.UsageError(f"{option}: {e}")


@lru_cache
def get_scope(config: Config) -> str:
    scope = config.option.smoke_scope or parse_ini_option(config, SmokeIniOption.SMOKE_DEFAULT_SCOPE)
    assert scope
    return scope


def _round_half_up(x: float, precision: int) -> float:
    return float(Decimal(str(x)).quantize(Decimal("10") ** -precision, rounding=ROUND_HALF_UP))
