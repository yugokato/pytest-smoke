import argparse
import random
from collections import Counter
from enum import Enum, auto
from functools import lru_cache
from typing import Union

import pytest
from pytest import Config, Item, Parser

from pytest_smoke.utils import scale_down


class SmokeScope(str, Enum):
    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()

    FUNCTION = auto()
    CLASS = auto()
    FILE = auto()
    ALL = auto()

    def __str__(self) -> str:
        return str(self.value)


def pytest_addoption(parser: Parser):
    group = parser.getgroup("smoke", description="Smoke testing")
    group.addoption(
        "--smoke",
        dest="smoke",
        metavar="N",
        const=1,
        type=_parse_smoke_option,
        nargs="?",
        default=False,
        help="Run the first N (default=1) tests from each test function or specified scope",
    )
    group.addoption(
        "--smoke-last",
        dest="smoke_last",
        metavar="N",
        const=1,
        type=_parse_smoke_option,
        nargs="?",
        default=False,
        help="Run the last N (default=1) tests from each test function or specified scope",
    )
    group.addoption(
        "--smoke-random",
        dest="smoke_random",
        metavar="N",
        const=1,
        type=_parse_smoke_option,
        nargs="?",
        default=False,
        help="Run N (default=1) randomly selected tests from each test function or specified scope",
    )
    group.addoption(
        "--smoke-scope",
        dest="smoke_scope",
        metavar="SCOPE",
        choices=[str(x) for x in SmokeScope],
        help=(
            "Specify the scope at which N from the above options is applied.\n"
            "Supported values:\n"
            "- function: Applies to each test function (default)\n"
            "- class: Applies to each test class\n"
            "- file: Applies to each test file\n"
            "- all: Applies to the entire test suite"
        ),
    )


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: Config):
    if sum([bool(config.option.smoke), bool(config.option.smoke_last), bool(config.option.smoke_random)]) > 1:
        raise pytest.UsageError("--smoke, --smoke-last, and --smoke-random options are mutually exclusive")

    if config.option.smoke_scope and not any(
        [config.option.smoke, config.option.smoke_last, config.option.smoke_random]
    ):
        raise pytest.UsageError(
            "The --smoke-scope option requires one of --smoke, --smoke-last, or --smoke-random to be specified"
        )


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: Config, items: list[Item]):
    if not items:
        return

    if n := config.option.smoke or config.option.smoke_last or config.option.smoke_random:
        if is_scale := isinstance(n, str) and n.endswith("%"):
            num_smoke = float(n[:-1])
        else:
            num_smoke = n
        scope = config.option.smoke_scope or SmokeScope.FUNCTION
        selected_items = []
        deselected_items = []
        counter_collected = Counter(_generate_id(item, scope) for item in items)
        counter_selected = Counter()
        tests_reached_threshold = set()
        if config.option.smoke_random:
            items_to_filter = random.sample(items, len(items))
        elif config.option.smoke_last:
            items_to_filter = items[::-1]
        else:
            items_to_filter = items

        for item in items_to_filter:
            scoped_item_id = _generate_id(item, scope)
            if (
                scope == SmokeScope.CLASS and not getattr(item, "cls", None)
            ) or scoped_item_id in tests_reached_threshold:
                deselected_items.append(item)
                continue

            if is_scale:
                num_tests = counter_collected[scoped_item_id]
                threshold = scale_down(num_tests, num_smoke)
            else:
                threshold = num_smoke

            num_selected_tests = counter_selected[scoped_item_id]
            if num_selected_tests < threshold:
                counter_selected.update([scoped_item_id])
                selected_items.append(item)
            else:
                tests_reached_threshold.add(scoped_item_id)
                deselected_items.append(item)

        if len(selected_items) < len(items):
            if config.option.smoke_random or config.option.smoke_last:
                # retain the original test order
                selected_items.sort(key=lambda x: items.index(x))

            items.clear()
            items.extend(selected_items)
            config.hook.pytest_deselected(items=deselected_items)


def _parse_smoke_option(value: str) -> Union[int, str]:
    try:
        if is_scale := value.endswith("%"):
            val = float(value[:-1])
        else:
            val = int(value)

        if val < 1 or is_scale and val > 100:
            raise ValueError

        if is_scale:
            return f"{val}%"
        else:
            return val
    except ValueError:
        raise argparse.ArgumentTypeError("The value must be a positive number or a valid percentage if given.")


@lru_cache
def _generate_id(item: Item, scope: str) -> str:
    if scope == SmokeScope.ALL:
        return "*"

    scoped_id = str(item.path or item.location[0])
    if scope == SmokeScope.FILE:
        return scoped_id

    if cls := getattr(item, "cls", None):
        scoped_id += f"::{cls.__name__}"

    if scope == SmokeScope.FUNCTION:
        func_name = item.function.__name__  # type: ignore
        scoped_id += f"::{func_name}"

    return scoped_id
