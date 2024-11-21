import argparse
import random
from collections import Counter
from typing import Union

import pytest
from pytest import Config, Item, Parser

from pytest_smoke.utils import calculate_scaled_value


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
        help="Run the first N (default=1) tests from each test function",
    )
    group.addoption(
        "--smoke-last",
        dest="smoke_last",
        metavar="N",
        const=1,
        type=_parse_smoke_option,
        nargs="?",
        default=False,
        help="Run the last N (default=1) tests from each test function",
    )
    group.addoption(
        "--smoke-random",
        dest="smoke_random",
        metavar="N",
        const=1,
        type=_parse_smoke_option,
        nargs="?",
        default=False,
        help="Run N (default=1) randomly selected tests from each test function",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: Config):
    if sum([bool(config.option.smoke), bool(config.option.smoke_last), bool(config.option.smoke_random)]) > 1:
        raise pytest.UsageError("--smoke, --smoke-last, and --smoke-random are mutually exclusive")


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: Config, items: list[Item]):
    if items and (n := (config.option.smoke or config.option.smoke_last or config.option.smoke_random)):
        if is_scale := isinstance(n, str) and n.endswith("%"):
            if (num_smoke := float(n[:-1])) == 100:
                return
        else:
            num_smoke = n
        selected_items = []
        deselected_items = []
        counter_collected = Counter(_generate_test_func_id(item) for item in items)
        counter_selected = Counter()
        tests_reached_threshold = set()
        if config.option.smoke_random:
            items_to_filter = sorted(items, key=lambda x: random.random())
        elif config.option.smoke_last:
            items_to_filter = items[::-1]
        else:
            items_to_filter = items

        for item in items_to_filter:
            test_func_id = _generate_test_func_id(item)
            if test_func_id in tests_reached_threshold:
                deselected_items.append(item)
                continue

            num_selected_tests = counter_selected.get(test_func_id, 0)
            if is_scale:
                num_tests = counter_collected[test_func_id]
                threshold = calculate_scaled_value(num_tests, num_smoke)
            else:
                threshold = num_smoke

            if num_selected_tests < threshold:
                counter_selected.update([test_func_id])
                selected_items.append(item)
            else:
                tests_reached_threshold.add(test_func_id)
                deselected_items.append(item)

        if len(selected_items) < len(items):
            if config.option.smoke_random or config.option.smoke_last:
                # retain the original test order
                selected_items.sort(key=lambda x: items.index(x))

            del items[:]
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


def _generate_test_func_id(item: Item) -> str:
    relfspath = item.location[0]
    func_name = item.function.__name__  # type: ignore
    if cls := getattr(item, "cls", None):
        return f"{relfspath}::{cls.__name__}::{func_name}"
    else:
        return f"{relfspath}::{func_name}"
