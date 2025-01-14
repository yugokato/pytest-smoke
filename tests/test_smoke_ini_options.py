import re
from typing import Optional

import pytest
from pytest import ExitCode, Pytester

from pytest_smoke import smoke
from pytest_smoke.types import SmokeIniOption, SmokeScope, SmokeSelectMode
from tests.helper import TEST_NAME_BASE, TestFileSpec, TestFuncSpec, generate_test_code, requires_xdist

if smoke.is_xdist_installed:
    from xdist.scheduler import LoadScheduling

    from pytest_smoke.extensions.xdist import SmokeScopeScheduling


def test_smoke_ini_option_smoke_default_n(pytester: Pytester):
    """Test smoke_default_n INI option"""
    num_tests = 10
    default_n = 3
    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests)))
    pytester.makeini(f"""
    [pytest]
    {SmokeIniOption.SMOKE_DEFAULT_N} = {default_n}
    """)
    result = pytester.runpytest("--smoke")
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=default_n, deselected=num_tests - default_n)


def test_smoke_ini_option_smoke_default_scope(pytester: Pytester):
    """Test smoke_default_scope INI option"""
    num_tests_1 = 5
    num_tests_2 = 10
    pytester.makepyfile(
        generate_test_code(TestFileSpec([TestFuncSpec(num_params=num_tests_1), TestFuncSpec(num_params=num_tests_2)]))
    )
    pytester.makeini(f"""
    [pytest]
    {SmokeIniOption.SMOKE_DEFAULT_SCOPE} = {SmokeScope.FILE}
    """)
    result = pytester.runpytest("--smoke")
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=1, deselected=num_tests_1 + num_tests_2 - 1)


def test_smoke_ini_option_smoke_default_select_mode(pytester: Pytester):
    """Test smoke_default_select_mode INI option"""
    smoke_n = 3
    num_tests = 10
    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests)))
    pytester.makeini(f"""
    [pytest]
    {SmokeIniOption.SMOKE_DEFAULT_SELECT_MODE} = {SmokeSelectMode.LAST}
    """)
    result = pytester.runpytest("--smoke", str(smoke_n), "--co", "-q")
    assert result.ret == ExitCode.OK
    result.assert_outcomes(deselected=num_tests - smoke_n)

    matched_test_nums = re.findall(rf"test_.+\.py::{TEST_NAME_BASE}\[(\d+)\]", str(result.stdout))
    assert len(matched_test_nums) == smoke_n
    assert [int(n) for n in matched_test_nums] == list(range(num_tests))[-smoke_n:]


@requires_xdist
@pytest.mark.parametrize("dist_option", [None, "--dist=load", "-d"])
@pytest.mark.parametrize("value", ["true", "false", None])
def test_smoke_ini_option_smoke_default_xdist_dist_by_scope(
    pytester: Pytester, value: Optional[str], dist_option: Optional[str]
):
    """Test smoke_default_xdist_dist_by_scope INI option.

    The plugin should extend the pytest-xdist to use the custom scheduler when the INI option value is true and
    when no dist option (--dist or -d) is explicitly given
    """
    from xdist import __version__ as xdist_ver

    num_tests_1 = 100
    num_tests_2 = 100
    test_file_spec = TestFileSpec([TestFuncSpec(num_params=num_tests_1), TestFuncSpec(num_params=num_tests_2)])
    num_test_func = len(test_file_spec.test_specs)
    smoke_n = 99
    pytester.makepyfile(test_xdist=generate_test_code(test_file_spec))
    if value:
        pytester.makeini(f"""
        [pytest]
        {SmokeIniOption.SMOKE_DEFAULT_XDIST_DIST_BY_SCOPE} = {value}
        """)
    args = ["--smoke", str(smoke_n), "-v", "-n", "2"]
    if dist_option:
        args.append(dist_option)
        if tuple(map(int, xdist_ver.split("."))) >= (3, 2, 0):
            # Sometimes our github test workflow on windows fails as tests don't get distributed evenly.
            # Add --maxschedchunk=1 as a workaround
            args.extend(["--maxschedchunk", "1"])

    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK
    expected_scheduler = SmokeScopeScheduling if dist_option is None and value == "true" else LoadScheduling
    result.stdout.re_match_lines(f"scheduling tests via {expected_scheduler.__name__}")
    num_passed = num_test_func * smoke_n
    result.assert_outcomes(passed=num_passed, deselected=num_tests_1 + num_tests_2 - num_passed)

    test_ids_worker1 = re.findall(rf"\[gw0\].+PASSED (test_xdist\.py::{TEST_NAME_BASE}\d)\[\d+\]", str(result.stdout))
    test_ids_worker2 = re.findall(rf"\[gw1\].+PASSED (test_xdist\.py::{TEST_NAME_BASE}\d)\[\d+\]", str(result.stdout))
    assert test_ids_worker1 and test_ids_worker2
    assert len(test_ids_worker1) + len(test_ids_worker2) == num_passed
    for test_ids in (test_ids_worker1, test_ids_worker2):
        if expected_scheduler == SmokeScopeScheduling:
            # Since the default smoke scope is function, each worker processes tests only for single test function
            assert len(test_ids) == smoke_n
            assert len(set(test_ids)) == 1
        else:
            # Tests should be distributed from both test functions
            assert len(set(test_ids)) == num_test_func


@pytest.mark.parametrize("value", [None, "true", "false"])
def test_smoke_ini_option_smoke_marked_tests_as_critical(pytester: Pytester, value: Optional[str]):
    """Test smoke_marked_tests_as_critical INI option"""
    is_enabled = value == "true"
    num_tests_1 = 5
    num_tests_2 = 5
    test_file_spec = TestFileSpec(
        [
            TestFuncSpec(num_params=num_tests_1),
            TestFuncSpec(
                num_params=num_tests_2,
                # Apply @pytest.mark.smoke to all tests
                param_marker=lambda x: "smoke",
            ),
        ]
    )
    pytester.makepyfile(generate_test_code(test_file_spec))
    if value:
        pytester.makeini(f"""
        [pytest]
        {SmokeIniOption.SMOKE_MARKED_TESTS_AS_CRITICAL} = {value}
        """)
    result = pytester.runpytest("--smoke", "-v")
    assert result.ret == ExitCode.OK
    test_nums = re.findall(rf"test_.+\.py::{TEST_NAME_BASE}(\d).+", str(result.stdout))
    if is_enabled:
        assert sorted(test_nums, reverse=True) == test_nums
        num_passes = 1 + num_tests_2
    else:
        assert sorted(test_nums) == test_nums
        num_passes = len(test_file_spec.test_specs)
    result.assert_outcomes(passed=num_passes, deselected=num_tests_1 + num_tests_2 - num_passes)


@pytest.mark.parametrize(
    "ini_option",
    [
        pytest.param(x, marks=requires_xdist if x == SmokeIniOption.SMOKE_DEFAULT_XDIST_DIST_BY_SCOPE else [])
        for x in SmokeIniOption
    ],
)
@pytest.mark.parametrize("value", ["foo", ""])
def test_smoke_ini_option_with_invalid_value(pytester: Pytester, ini_option: str, value: str):
    """Test INI options with an invalid value are handled as a usage error"""
    pytester.makepyfile(generate_test_code(TestFuncSpec()))
    pytester.makeini(f"""
    [pytest]
    {ini_option} = {value}
    """)
    args = ["--smoke"]
    if ini_option == SmokeIniOption.SMOKE_DEFAULT_XDIST_DIST_BY_SCOPE:
        args.extend(["-n", "2"])
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.USAGE_ERROR
