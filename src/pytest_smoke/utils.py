from __future__ import annotations

import os
import random
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from types import ModuleType
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest
from pytest import Class, Function

from pytest_smoke import smoke
from pytest_smoke.types import SmokeEnvVar, SmokeIniOption, SmokeOption, SmokeScope, SmokeSelectMode

if smoke.is_xdist_installed:
    from xdist import is_xdist_controller, is_xdist_worker

if TYPE_CHECKING:
    from _pytest.nodes import Node
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
def generate_group_id(item: Item, scope: str) -> str | None:
    """Generate a smoke scope group ID for the item

    :param item: Collected Pytest item
    :param scope: Smoke scope
    """
    assert scope
    if item.config.hook.pytest_smoke_exclude(item=item, scope=scope):
        return None

    if (group_id := item.config.hook.pytest_smoke_generate_group_id(item=item, scope=scope)) is not None:
        return group_id

    return _generate_scope_group_id(item, scope)


@lru_cache
def has_parametrized_test(node: Node) -> bool:
    """Check if at least one parametrized test exists in the node

    :param node: Pytest node
    """
    node_items = tuple(x for x in node.session.items if x.parent == node)
    for node_item in node_items:
        if node_item.get_closest_marker("parametrize"):
            return True
    return False


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
        random_: random.Random | ModuleType
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


def parse_n(value: str) -> int | float | str:
    v = value.strip()
    try:
        if is_scale := v.endswith("%"):
            num = float(v[:-1])
        else:
            num = int(v)

        if num < 1 or (is_scale and num > 100):
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


def parse_ini_option(config: Config, option: SmokeIniOption) -> str | int | float | bool:
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


@lru_cache
def _generate_scope_group_id(item: Item, scope: str) -> str | None:
    def _generate_class_group_id(current_item: Node, class_id: str = "") -> str:
        parent = current_item.parent
        if isinstance(parent, Class):
            return _generate_class_group_id(parent, class_id=f"::{parent.name}{class_id}")
        return class_id

    if scope not in [str(x) for x in SmokeScope]:
        raise pytest.UsageError(
            f"The logic for the custom scope '{scope}' must be implemented using the "
            f"pytest_smoke_generate_group_id hook"
        )

    if scope == SmokeScope.ALL:
        return "*"

    is_class_method = isinstance(item.parent, Class)
    if not is_class_method and scope == SmokeScope.CLASS:
        return None

    file_path = item.path
    if scope == SmokeScope.DIRECTORY:
        return str(file_path.parent)

    group_id = str(file_path)
    if scope == SmokeScope.FILE:
        return group_id

    if is_class_method:
        group_id += _generate_class_group_id(item)
        if scope == SmokeScope.CLASS:
            return group_id

    # function or auto scope
    assert scope in [SmokeScope.FUNCTION, SmokeScope.AUTO]
    if scope == SmokeScope.FUNCTION or has_parametrized_test(item.parent):
        func_name = cast(Function, item).function.__name__
        return f"{group_id}::{func_name}"
    else:
        # The parent node has no parametrized tests. Fall back to file or class scope
        if is_class_method:
            dynamic_scope = SmokeScope.CLASS
        else:
            dynamic_scope = SmokeScope.FILE
        return _generate_scope_group_id(item, dynamic_scope)
