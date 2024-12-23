import os
import random
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from pytest import Config, Item, Parser, PytestPluginManager, Session

from pytest_smoke import smoke
from pytest_smoke.types import SmokeDefaultN, SmokeEnvVar, SmokeIniOption, SmokeScope
from pytest_smoke.utils import generate_group_id, get_scope, parse_ini_option, parse_n, parse_scope, scale_down

if smoke.is_xdist_installed:
    from xdist import is_xdist_controller, is_xdist_worker

    from pytest_smoke.extensions.xdist import PytestSmokeXdist


DEFAULT_N = SmokeDefaultN(1)


@dataclass
class SmokeGroupIDCounter:
    collected: Counter = field(default_factory=Counter)
    sellected: Counter = field(default_factory=Counter)


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
        type=parse_n,
        nargs="?",
        default=False,
        help="Run the first N (default=1) tests from each test function or specified scope",
    )
    group.addoption(
        "--smoke-last",
        dest="smoke_last",
        metavar="N",
        const=DEFAULT_N,
        type=parse_n,
        nargs="?",
        default=False,
        help="Run the last N (default=1) tests from each test function or specified scope",
    )
    group.addoption(
        "--smoke-random",
        dest="smoke_random",
        metavar="N",
        const=DEFAULT_N,
        type=parse_n,
        nargs="?",
        default=False,
        help="Run N (default=1) randomly selected tests from each test function or specified scope",
    )
    group.addoption(
        "--smoke-scope",
        dest="smoke_scope",
        metavar="SCOPE",
        type=parse_scope,
        help=(
            "Specify the scope at which the value of N from the above options is applied.\n"
            "The plugin provides the following predefined scopes:\n"
            f"- {SmokeScope.FUNCTION}: Applies to each test function (default)\n"
            f"- {SmokeScope.CLASS}: Applies to each test class\n"
            f"- {SmokeScope.AUTO}: Applies {SmokeScope.FUNCTION} scope for test functions, "
            f"{SmokeScope.CLASS} scope for test methods\n"
            f"- {SmokeScope.FILE}: Applies to each test file\n"
            f"- {SmokeScope.ALL}: Applies to the entire test suite\n"
            "NOTE: You can also implement your own custom scopes using a hook"
        ),
    )

    parser.addini(
        SmokeIniOption.SMOKE_DEFAULT_N,
        type="string",
        default=str(DEFAULT_N),
        help="[pytest-smoke] Override the plugin default value for smoke N",
    )
    parser.addini(
        SmokeIniOption.SMOKE_DEFAULT_SCOPE,
        type="string",
        default=SmokeScope.FUNCTION,
        help="[pytest-smoke] Override the plugin default value for smoke scope",
    )
    parser.addini(
        SmokeIniOption.SMOKE_DEFAULT_XDIST_DIST_BY_SCOPE,
        type="bool",
        default=False,
        help="[pytest-smoke] When using the pytest-xdist plugin for parallel testing, replace the default scheduler "
        "with a custom distribution algorithm that distributes tests based on the smoke scope",
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

    if smoke.is_xdist_installed:
        if config.pluginmanager.has_plugin("xdist"):
            # Register the smoke-xdist plugin if -n/--numprocesses option is given.
            if config.getoption("numprocesses", default=None):
                config.pluginmanager.register(PytestSmokeXdist(), name=PytestSmokeXdist.name)
        else:
            smoke.is_xdist_installed = False


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_sessionstart(session: Session):
    if not smoke.is_xdist_installed or not is_xdist_worker(session):
        os.environ[SmokeEnvVar.SMOKE_TEST_SESSION_UUID] = str(uuid4())
    return (yield)


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_collection_modifyitems(session: Session, config: Config, items: list[Item]):
    try:
        return (yield)
    finally:
        if not items:
            return

        if n := (config.option.smoke or config.option.smoke_last or config.option.smoke_random):
            if isinstance(n, SmokeDefaultN):
                # N was not explicitly provided to the option. Apply the INI config value or the plugin default
                n = parse_ini_option(config, SmokeIniOption.SMOKE_DEFAULT_N)

            if is_scale := isinstance(n, str) and n.endswith("%"):
                num_smoke = float(n[:-1])
            else:
                num_smoke = n
            scope = get_scope(config)
            selected_items = []
            deselected_items = []
            counter = SmokeGroupIDCounter(
                collected=Counter(filter(None, (generate_group_id(item, scope) for item in items)))
            )
            smoke_groups_reached_threshold = set()
            if config.option.smoke_random:
                if smoke.is_xdist_installed and (is_xdist_controller(session) or is_xdist_worker(session)):
                    # Set the seed to ensure XDIST controler and workers collect the same items
                    random_ = random.Random(UUID(os.environ[SmokeEnvVar.SMOKE_TEST_SESSION_UUID]).time)
                else:
                    random_ = random
                items_to_filter = random_.sample(items, len(items))
            elif config.option.smoke_last:
                items_to_filter = items[::-1]
            else:
                items_to_filter = items

            for item in items_to_filter:
                if config.hook.pytest_smoke_always_run(item=item, scope=scope):
                    # Will not be counted towards the calculation of N
                    selected_items.append(item)
                    continue

                group_id = generate_group_id(item, scope)
                if group_id is None or group_id in smoke_groups_reached_threshold:
                    deselected_items.append(item)
                    continue

                threshold = scale_down(counter.collected[group_id], num_smoke) if is_scale else num_smoke
                if counter.sellected[group_id] < threshold:
                    counter.sellected.update([group_id])
                    selected_items.append(item)
                else:
                    smoke_groups_reached_threshold.add(group_id)
                    deselected_items.append(item)

            if deselected_items:
                config.hook.pytest_deselected(items=deselected_items)
                if config.option.smoke_random or config.option.smoke_last:
                    # retain the original test order
                    selected_items.sort(key=lambda x: items.index(x))
                items.clear()
                items.extend(selected_items)
