from __future__ import annotations

import os
from collections import Counter
from typing import TYPE_CHECKING, Optional, Union
from uuid import uuid4

import pytest
from pytest import StashKey

from pytest_smoke import smoke
from pytest_smoke.compat import TestShortLogReport
from pytest_smoke.types import (
    SmokeCounter,
    SmokeDefaultN,
    SmokeEnvVar,
    SmokeIniOption,
    SmokeMarker,
    SmokeOption,
    SmokeScope,
    SmokeSelectMode,
)
from pytest_smoke.utils import (
    generate_group_id,
    parse_ini_option,
    parse_n,
    parse_scope,
    parse_select_mode,
    scale_down,
    sort_items,
)

if smoke.is_xdist_installed:
    from xdist import is_xdist_worker

    from pytest_smoke.extensions.xdist import PytestSmokeXdist

if TYPE_CHECKING:
    from pytest import Config, Item, Parser, PytestPluginManager, Session, StashKey, TestReport


STASH_KEY_SMOKE_COUNTER = StashKey[SmokeCounter]()
STASH_KEY_SMOKE_IS_CIRITICAL = StashKey[bool]()
STASH_KEY_SMOKE_IS_MUSTPASS = StashKey[bool]()
STASH_KEY_SMOKE_SHOULD_SKIP_RESET = StashKey[bool]()
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
        type=parse_n,
        nargs="?",
        default=False,
        help="Run only N tests from each test function or specified scope.\n"
        "N can be a number (e.g. 5) or a percentage (e.g. 10%%).\n"
        "If not provided, the default value is 1.",
    )
    group.addoption(
        "--smoke-scope",
        dest="smoke_scope",
        metavar="SCOPE",
        type=parse_scope,
        help=(
            "Specify the scope at which the value of N from the above options is applied.\n"
            "The plugin provides the following predefined scopes, as well as custom user-defined scopes via a hook:\n"
            f"- {SmokeScope.FUNCTION}: Applies to each test function (default)\n"
            f"- {SmokeScope.CLASS}: Applies to each test class\n"
            f"- {SmokeScope.AUTO}: Applies {SmokeScope.FUNCTION} scope for test functions, "
            f"{SmokeScope.CLASS} scope for test methods\n"
            f"- {SmokeScope.FILE}: Applies to each test file\n"
            f"- {SmokeScope.DIRECTORY}: Applies to each test directory\n"
            f"- {SmokeScope.ALL}: Applies to the entire test suite"
        ),
    )
    group.addoption(
        "--smoke-select-mode",
        dest="smoke_select_mode",
        metavar="MODE",
        type=parse_select_mode,
        help=(
            "Specify the mode for selecting tests from each scope.\n"
            "The plugin provides the following predefined values, as well as custom user-defined values via a hook:\n"
            f"- {SmokeSelectMode.FIRST}: The first N tests (default)\n"
            f"- {SmokeSelectMode.LAST}: The last N tests\n"
            f"- {SmokeSelectMode.RANDOM}: N randomly selected tests"
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
        SmokeIniOption.SMOKE_DEFAULT_SELECT_MODE,
        type="string",
        default=SmokeSelectMode.FIRST,
        help="[pytest-smoke] Override the plugin default value for smoke select mode",
    )
    parser.addini(
        SmokeIniOption.SMOKE_DEFAULT_XDIST_DIST_BY_SCOPE,
        type="bool",
        default=False,
        help="[pytest-smoke] When using the pytest-xdist plugin for parallel testing, replace the default scheduler "
        "with a custom distribution algorithm that distributes tests based on the smoke scope",
    )
    parser.addini(
        SmokeIniOption.SMOKE_MARKED_TESTS_AS_CRITICAL,
        type="bool",
        default=False,
        help="[pytest-smoke] Treat tests marked with @pytest.mark.smoke as 'critical' smoke tests",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: Config):
    if not config.option.smoke and (config.option.smoke_scope or config.option.smoke_select_mode):
        raise pytest.UsageError("The --smoke option is requierd to use the pytest-smoke functionality")

    config.addinivalue_line(
        "markers",
        "smoke(*, mustpass=False, runif=True): [pytest-smoke] When running smoke tests using the pytest-smoke plugin, "
        "and the feature is explicitly enabled via an INI option, the marked test is considered a 'critical' smoke "
        "test. Additionally, if the optional mustpass keyword argument is set to True, the test is considered a "
        "'must-pass' critical smoke test. Critical smoke tests with runif=True are automatically included and executed "
        "first, before regular smoke tests. If any 'must-pass' test fails, all subsequent regular smoke tests will be "
        "skipped.\n"
        "Note: The marker will have no effect on the plugin until the feature has been enabled",
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

        opt = SmokeOption(config)
        if opt.n:
            selected_items_regular = []
            selected_items_critical = []
            deselected_items = []
            smoke_groups_reached_threshold = set()
            counter = SmokeCounter(
                collected=Counter(filter(None, (generate_group_id(item, opt.scope) for item in items)))
            )
            session.stash[STASH_KEY_SMOKE_COUNTER] = counter
            enable_critical_tests = parse_ini_option(config, SmokeIniOption.SMOKE_MARKED_TESTS_AS_CRITICAL)

            for item in sort_items(items, session, opt):
                group_id = generate_group_id(item, opt.scope)
                if group_id is None:
                    deselected_items.append(item)
                    continue

                # Tests that match the below conditions will not be counted towards the calculation of N
                if enable_critical_tests and (smoke_marker := SmokeMarker.from_item(item)):
                    if smoke_marker.runif:
                        selected_items_critical.append(item)
                        if smoke_marker.mustpass:
                            counter.mustpass.selected.add(item)
                        item.stash[STASH_KEY_SMOKE_IS_CIRITICAL] = True
                        item.stash[STASH_KEY_SMOKE_IS_MUSTPASS] = smoke_marker.mustpass
                    else:
                        deselected_items.append(item)
                    continue
                elif config.hook.pytest_smoke_include(item=item, scope=opt.scope):
                    selected_items_regular.append(item)
                    continue

                if group_id in smoke_groups_reached_threshold:
                    deselected_items.append(item)
                    continue

                threshold = scale_down(counter.collected[group_id], float(opt.n[:-1])) if opt.is_scale else opt.n
                if counter.selected[group_id] < threshold:
                    counter.selected.update([group_id])
                    selected_items_regular.append(item)
                else:
                    smoke_groups_reached_threshold.add(group_id)
                    deselected_items.append(item)

            assert len(items) == len(selected_items_critical + selected_items_regular + deselected_items)
            if selected_items_critical or deselected_items:
                if deselected_items:
                    config.hook.pytest_deselected(items=deselected_items)

                if opt.select_mode != SmokeSelectMode.FIRST:
                    # retain the original test order
                    for smoke_items in (selected_items_critical, selected_items_regular):
                        if smoke_items:
                            smoke_items.sort(key=lambda x: items.index(x))

                items.clear()
                items.extend(selected_items_critical + selected_items_regular)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: Item, nextitem: Optional[Item]):
    try:
        return (yield)
    finally:
        if nextitem and item.stash.get(STASH_KEY_SMOKE_IS_CIRITICAL, False):
            counter = item.session.stash[STASH_KEY_SMOKE_COUNTER].mustpass
            if counter.failed and not nextitem.stash.get(STASH_KEY_SMOKE_IS_CIRITICAL, False):
                # At least one must-pass test failed, and this is the last critical test.
                # Set the flag to skip all subsequent regular tests
                item.session.stash[STASH_KEY_SMOKE_SHOULD_SKIP_RESET] = True


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: Item):
    if item.session.stash.get(STASH_KEY_SMOKE_SHOULD_SKIP_RESET, False):
        counter = item.session.stash[STASH_KEY_SMOKE_COUNTER].mustpass
        num_selected = len(counter.selected)
        num_failed = len(counter.failed)
        pytest.skip(reason=f"{num_failed}/{num_selected} must-pass smoke test{'s' if num_failed > 1 else ''} failed")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: Item):
    report: TestReport = yield
    if item.stash.get(STASH_KEY_SMOKE_IS_MUSTPASS, False):
        setattr(report, "_is_smoke_must_pass", True)
        if report.failed:
            item.session.stash[STASH_KEY_SMOKE_COUNTER].mustpass.failed.add(item)
    return report


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_report_teststatus(report: TestReport):
    status: Union[tuple, TestShortLogReport] = yield
    if not isinstance(status, TestShortLogReport):
        status = TestShortLogReport(*status)
    if status.word and getattr(report, "_is_smoke_must_pass", False):
        annot = " (must-pass)"
        if isinstance(status.word, str):
            status = status._replace(word=status.word + annot)
        elif isinstance(status.word, tuple):
            status = status._replace(word=([status.word[0] + annot, *status.word[1:]]))
    return status
