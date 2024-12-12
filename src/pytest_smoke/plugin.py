import random
from collections import Counter
from enum import auto
from functools import lru_cache
from typing import Optional, Union

import pytest
from pytest import Config, Item, Parser, PytestPluginManager

from pytest_smoke.utils import StrEnum, scale_down


class SmokeScope(StrEnum):
    FUNCTION = auto()
    CLASS = auto()
    FILE = auto()
    ALL = auto()


class SmokeIniOption(StrEnum):
    DEFAULT_SMOKE_N = auto()
    DEFAULT_SMOKE_SCOPE = auto()


class SmokeDefaultN(int): ...


DEFAULT_N = SmokeDefaultN(1)


@pytest.hookimpl(trylast=True)
def pytest_addhooks(pluginmanager: PytestPluginManager):
    from pytest_smoke import hooks

    pluginmanager.add_hookspecs(hooks)


def pytest_addoption(parser: Parser):
    group = parser.getgroup("smoke", description="Smoke testing")
    group.addoption(
        "--smoke",
        dest="smoke",
        metavar="N",
        const=DEFAULT_N,
        type=_parse_n,
        nargs="?",
        default=False,
        help="Run the first N (default=1) tests from each test function or specified scope",
    )
    group.addoption(
        "--smoke-last",
        dest="smoke_last",
        metavar="N",
        const=DEFAULT_N,
        type=_parse_n,
        nargs="?",
        default=False,
        help="Run the last N (default=1) tests from each test function or specified scope",
    )
    group.addoption(
        "--smoke-random",
        dest="smoke_random",
        metavar="N",
        const=DEFAULT_N,
        type=_parse_n,
        nargs="?",
        default=False,
        help="Run N (default=1) randomly selected tests from each test function or specified scope",
    )
    group.addoption(
        "--smoke-scope",
        dest="smoke_scope",
        metavar="SCOPE",
        type=_parse_scope,
        help=(
            "Specify the scope at which the value of N from the above options is applied.\n"
            "The plugin provides the following predefined scopes:\n"
            f"- {SmokeScope.FUNCTION}: Applies to each test function (default)\n"
            f"- {SmokeScope.CLASS}: Applies to each test class\n"
            f"- {SmokeScope.FILE}: Applies to each test file\n"
            f"- {SmokeScope.ALL}: Applies to the entire test suite\n"
            "NOTE: You can also implement your own custom scopes using a hook"
        ),
    )
    parser.addini(
        SmokeIniOption.DEFAULT_SMOKE_N,
        type="string",
        default=str(DEFAULT_N),
        help="Overwrite the plugin default value for smoke N",
    )
    parser.addini(
        SmokeIniOption.DEFAULT_SMOKE_SCOPE,
        type="string",
        default=SmokeScope.FUNCTION,
        help="Overwrite the plugin default value for smoke scope",
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


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_collection_modifyitems(config: Config, items: list[Item]):
    try:
        return (yield)
    finally:
        if not items:
            return

        if n := config.option.smoke or config.option.smoke_last or config.option.smoke_random:
            if isinstance(n, SmokeDefaultN):
                # N was not explicitly provided to the option. Apply the INI config value or the plugin default
                n = _parse_n(config.getini(SmokeIniOption.DEFAULT_SMOKE_N))

            if is_scale := isinstance(n, str) and n.endswith("%"):
                num_smoke = float(n[:-1])
            else:
                num_smoke = n
            scope = config.option.smoke_scope
            if scope is None:
                # --scope-smoke option was not explicitly given. Apply the INI config value or the plugin default
                scope = _parse_scope(config.getini(SmokeIniOption.DEFAULT_SMOKE_SCOPE))
            selected_items = []
            deselected_items = []
            counter_collected = Counter(filter(None, (_generate_group_id(item, scope) for item in items)))
            counter_selected = Counter()
            smoke_groups_reached_threshold = set()
            if config.option.smoke_random:
                items_to_filter = random.sample(items, len(items))
            elif config.option.smoke_last:
                items_to_filter = items[::-1]
            else:
                items_to_filter = items

            for item in items_to_filter:
                if config.hook.pytest_smoke_always_run(item=item, scope=scope):
                    # Will not be counted towards the calculation of N
                    selected_items.append(item)
                    continue

                group_id = _generate_group_id(item, scope)
                if group_id is None or group_id in smoke_groups_reached_threshold:
                    deselected_items.append(item)
                    continue

                if is_scale:
                    num_tests = counter_collected[group_id]
                    threshold = scale_down(num_tests, num_smoke)
                else:
                    threshold = num_smoke

                if counter_selected[group_id] < threshold:
                    counter_selected.update([group_id])
                    selected_items.append(item)
                else:
                    smoke_groups_reached_threshold.add(group_id)
                    deselected_items.append(item)

            if len(selected_items) < len(items):
                if config.option.smoke_random or config.option.smoke_last:
                    # retain the original test order
                    selected_items.sort(key=lambda x: items.index(x))

                items.clear()
                items.extend(selected_items)
                config.hook.pytest_deselected(items=deselected_items)


def _parse_n(value: str) -> Union[int, str]:
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


def _parse_scope(value: str) -> str:
    if (v := value.strip()) == "":
        raise pytest.UsageError(f"Invalid scope: '{value}'")
    return v


@lru_cache
def _generate_group_id(item: Item, scope: str) -> Optional[str]:
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
        if scope == SmokeScope.CLASS:
            return group_id

    # The default scope
    func_name = item.function.__name__  # type: ignore
    group_id += f"::{func_name}"
    return group_id
