import argparse
import random
from collections import Counter

import pytest
from pytest import Config, Item, Parser


def pytest_addoption(parser: Parser):
    group = parser.getgroup("smoke", description="Smoke testing")
    group.addoption(
        "--smoke",
        dest="smoke",
        metavar="N",
        const=True,
        type=_parse_smoke_option,
        nargs="?",
        default=False,
        help="Run the first N (default=1) tests from each test function",
    )
    group.addoption(
        "--smoke-last",
        dest="smoke_last",
        metavar="N",
        const=True,
        type=_parse_smoke_option,
        nargs="?",
        default=False,
        help="Run the last N (default=1) tests from each test function",
    )
    group.addoption(
        "--smoke-random",
        dest="smoke_random",
        metavar="N",
        const=True,
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
    if items and (
        num_tests_to_smoke := int(config.option.smoke or config.option.smoke_last or config.option.smoke_random)
    ):
        counter = Counter()
        selected_items = []
        deselected_items = []
        if config.option.smoke_random:
            items_to_filter = sorted(items, key=lambda x: random.random())
        elif config.option.smoke_last:
            items_to_filter = items[::-1]
        else:
            items_to_filter = items

        for item in items_to_filter:
            test_func_name = item.function.__name__  # type: ignore
            if counter.get(test_func_name, 0) < num_tests_to_smoke:
                counter.update([test_func_name])
                selected_items.append(item)
            else:
                deselected_items.append(item)

        if len(selected_items) < len(items):
            if config.option.smoke_random or config.option.smoke_last:
                # retain the original test order
                selected_items.sort(key=lambda x: items.index(x))

            del items[:]
            items.extend(selected_items)
            config.hook.pytest_deselected(items=deselected_items)


def _parse_smoke_option(value: str) -> int:
    try:
        val = int(value)
        if val < 1:
            raise ValueError
        return val
    except ValueError:
        raise argparse.ArgumentTypeError("The value must be a positive number if given.")
