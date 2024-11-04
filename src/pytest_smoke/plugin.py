import argparse
from collections import Counter

import pytest
from pytest import Config, Item, Parser, Session


def pytest_addoption(parser: Parser):
    parser.addoption(
        "--smoke",
        dest="smoke",
        metavar="N",
        const=True,
        type=_parse_smoke_option,
        nargs="?",
        default=False,
        help="Run only the first N (default=1) tests from each test function",
    )


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(session: Session, config: Config, items: list[Item]):
    if num_tests_to_smoke := int(config.option.smoke):
        counter = Counter()
        filtered_items = []
        for item in items:
            test_func_name = item.function.__name__  # type: ignore
            if counter.get(test_func_name, 0) < num_tests_to_smoke:
                counter.update([test_func_name])
                filtered_items.append(item)

        del items[:]
        items.extend(filtered_items)


def _parse_smoke_option(value: str) -> int:
    try:
        val = int(value)
        if val < 1:
            raise ValueError
        return val
    except ValueError:
        raise argparse.ArgumentTypeError("The value must be a positive number if given.")
