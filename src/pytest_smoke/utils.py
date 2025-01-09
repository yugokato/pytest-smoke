from __future__ import annotations

import os
import random
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import TYPE_CHECKING, Optional, Union
from uuid import UUID

import pytest

from pytest_smoke import smoke
from pytest_smoke.types import SmokeEnvVar, SmokeIniOption, SmokeOption, SmokeScope, SmokeSelectMode

if smoke.is_xdist_installed:
    from xdist import is_xdist_controller, is_xdist_worker

if TYPE_CHECKING:
    from pytest import Config, Item, Session


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
    """Generate a smoke scope group ID for the item

    :param item: Collected Pytest item
    :param scope: Smoke scope
    """
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

    file_path = item.path
    if scope == SmokeScope.DIRECTORY:
        return str(file_path.parent)

    group_id = str(file_path)
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


def sort_items(items: list[Item], session: Session, smoke_option: SmokeOption) -> list[Item]:
    """Sort collected Pytest items for the given select mode

    :param items: Collected Pytest items
    :param session: Pytest session
    :param smoke_option: Smoke option
    """
    if smoke_option.select_mode == SmokeSelectMode.FIRST:
        sorted_items = items
    elif smoke_option.select_mode == SmokeSelectMode.LAST:
        sorted_items = items[::-1]
    elif smoke_option.select_mode == SmokeSelectMode.RANDOM:
        if smoke.is_xdist_installed and (is_xdist_controller(session) or is_xdist_worker(session)):
            # Set the seed to ensure XDIST controler and workers collect the same items
            random_ = random.Random(UUID(os.environ[SmokeEnvVar.SMOKE_TEST_SESSION_UUID]).time)
        else:
            random_ = random
        sorted_items = random_.sample(items, len(items))
    else:
        sorted_items = session.config.hook.pytest_smoke_sort_by_select_mode(
            items=items.copy(), scope=smoke_option.scope, select_mode=smoke_option.select_mode
        )
        if sorted_items is None:
            raise pytest.UsageError(
                f"The custom sort logic for the select mode '{smoke_option.select_mode}' must be implemented using the "
                f"pytest_smoke_sort_by_select_mode hook"
            )
    return sorted_items


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


def parse_select_mode(value: str) -> str:
    if (v := value.strip()) == "":
        raise pytest.UsageError(f"Invalid select mode: '{value}'")
    return v


def parse_scope(value: str) -> str:
    if (v := value.strip()) == "":
        raise pytest.UsageError(f"Invalid scope: '{value}'")
    return v


def parse_ini_option(config: Config, option: SmokeIniOption) -> Union[str, int, bool]:
    try:
        v = config.getini(option)
        if option == SmokeIniOption.SMOKE_DEFAULT_N:
            return parse_n(v)
        elif option == SmokeIniOption.SMOKE_DEFAULT_SELECT_MODE:
            return parse_select_mode(v)
        elif option == SmokeIniOption.SMOKE_DEFAULT_SCOPE:
            return parse_scope(v)
        else:
            return v
    except ValueError as e:
        raise pytest.UsageError(f"{option}: {e}")


def _round_half_up(x: float, precision: int) -> float:
    return float(Decimal(str(x)).quantize(Decimal("10") ** -precision, rounding=ROUND_HALF_UP))
