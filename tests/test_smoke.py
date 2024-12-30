import re
from collections.abc import Sequence
from itertools import combinations
from typing import Optional

import pytest
from pytest import ExitCode, Pytester

from pytest_smoke import smoke
from pytest_smoke.types import SmokeIniOption, SmokeScope
from pytest_smoke.utils import scale_down
from tests.helper import (
    PARAMETRIZED_ARG_NAME_FUNC,
    TEST_NAME_BASE,
    TestFileSpec,
    TestFuncSpec,
    generate_test_code,
    get_num_tests,
    get_num_tests_to_be_selected,
    mock_column_width,
)

if smoke.is_xdist_installed:
    from xdist.scheduler import LoadScheduling

    from pytest_smoke.extensions.xdist import SmokeScopeScheduling


requires_xdist = pytest.mark.skipif(not smoke.is_xdist_installed, reason="pytest-xdist is required")
SMOKE_OPTIONS = ["--smoke", "--smoke-last", "--smoke-random"]
SMOKE_INI_OPTIONS = [
    SmokeIniOption.SMOKE_DEFAULT_N,
    SmokeIniOption.SMOKE_DEFAULT_SCOPE,
    pytest.param(SmokeIniOption.SMOKE_DEFAULT_XDIST_DIST_BY_SCOPE, marks=requires_xdist),
]


def test_smoke_command_help(pytester: Pytester):
    """Test pytest command help for this plugin"""
    result = pytester.runpytest("-h")
    assert result.ret == ExitCode.OK, str(result.stderr)
    stdout = str(result.stdout)
    pattern1 = (
        r"Smoke testing:\n"
        r"  --smoke=\[N\]\s+.+"
        r"  --smoke-last=\[N\]\s+.+"
        r"  --smoke-random=\[N\]\s+.+"
        r"  --smoke-scope=SCOPE\s+.+"
    ) + r"\n".join(rf"\s+- {scope}: .+" for scope in SmokeScope)
    assert re.search(pattern1, stdout, re.DOTALL)

    pattern2 = r"\[pytest\] ini-options.+" + r"\n".join(
        rf"  {opt} \([^)]+\):\s+\[pytest-smoke\] .+" for opt in SmokeIniOption
    )
    assert re.search(pattern2, stdout, re.DOTALL)


@pytest.mark.usefixtures("generate_test_files")
def test_smoke_no_option(pytester: Pytester, test_file_specs: list[TestFileSpec]):
    """Test the plugin does not affect pytest when no plugin options are given"""
    num_all_tests = get_num_tests(*test_file_specs)
    result = pytester.runpytest("-n", "2")
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=num_all_tests)


@pytest.mark.usefixtures("generate_test_files")
@pytest.mark.parametrize("scope", [None, *SmokeScope])
@pytest.mark.parametrize("n", [None, "1", "5", "15", "25", "35", str(2**32 - 1), "1%", "1.23%", "10%", "33%", "100%"])
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_n(
    pytester: Pytester,
    test_file_specs: list[TestFileSpec],
    option: str,
    n: Optional[str],
    scope: Optional[str],
):
    """Test all combinations of plugin options with various smoke N values"""
    num_all_tests = get_num_tests(*test_file_specs)
    num_tests_to_be_selected = get_num_tests_to_be_selected(test_file_specs, n, scope)
    args = [option]
    if n:
        args.append(n)
    if scope:
        args.extend(["--smoke-scope", scope])
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=num_tests_to_be_selected, deselected=num_all_tests - num_tests_to_be_selected)


@requires_xdist
@pytest.mark.usefixtures("generate_test_files")
@pytest.mark.parametrize("scope", [None, *SmokeScope])
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_xdist(pytester: Pytester, test_file_specs: list[TestFileSpec], option: str, scope: Optional[str]):
    """Test basic plugin functionality with pytest-xdist.

    The plugin should handle the following points:
    - Report the number of deselected tests in xdist controller
    - smoke-random: Sets a common random seeds so that all workers can collect the exact same tests
    """
    smoke_n = "3"
    num_all_tests = get_num_tests(*test_file_specs)
    num_tests_to_be_selected = get_num_tests_to_be_selected(test_file_specs, str(smoke_n), scope)
    args = [option, smoke_n, "-n", "2", "-v"]
    if scope:
        args.extend(["--smoke-scope", scope])
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=num_tests_to_be_selected, deselected=num_all_tests - num_tests_to_be_selected)


@requires_xdist
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_xdist_disabled(pytester: Pytester, option: str):
    """Test that pytest-smoke does not access the pytest-xdist plugin when it is install but explicitly disabled"""
    assert smoke.is_xdist_installed
    num_tests = 10
    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests)))
    args = [option, "-p", "no:xdist"]
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK
    assert not smoke.is_xdist_installed
    result.assert_outcomes(passed=1, deselected=num_tests - 1)


@pytest.mark.parametrize("num_fails", [0, 1, 2])
@pytest.mark.parametrize("mustpass", [None, False, True])
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_marker_critical_tests(pytester: Pytester, option: str, mustpass: bool, num_fails: int):
    """Test @pytest.mark.smoke marker with/without the optional mustpass kwarg"""

    def is_critical(i):
        return bool(i % 2)

    def param_marker(i):
        if is_critical(i):
            if i in test2_pos_mustpass and mustpass is not None:
                return f"smoke(mustpass={mustpass})"
            else:
                return "smoke"
        else:
            return None

    smoke_n = 4
    num_tests_1 = 10
    num_tests_2 = 10
    num_mustpass = 2
    test2_pos_mustpass = list(filter(is_critical, range(num_tests_2)))[:num_mustpass]
    func_body = f"\tassert {PARAMETRIZED_ARG_NAME_FUNC} not in {test2_pos_mustpass[:num_fails]}" if num_fails else None
    test_file_spec = TestFileSpec(
        [
            TestFuncSpec(num_params=num_tests_1),
            TestFuncSpec(
                num_params=num_tests_2,
                param_marker=param_marker,
                func_body=func_body,
            ),
        ]
    )
    num_critical_tests = sum([is_critical(i) for i in range(num_tests_2)])
    num_regular_tests = smoke_n * len(test_file_spec.test_specs)
    num_expected_selected_tests = num_regular_tests + num_critical_tests
    num_fails = num_fails
    num_skips = num_regular_tests if mustpass and num_fails else 0
    assert all(
        [
            smoke_n < num_tests_1,
            smoke_n < num_tests_2,
            smoke_n < num_critical_tests,
            smoke_n + num_critical_tests < num_tests_2,
            num_fails <= len(test2_pos_mustpass),
            len(test2_pos_mustpass) < num_critical_tests,
            all((p < num_tests_2 and is_critical(p)) for p in test2_pos_mustpass),
        ]
    ), "Invalid test conditions"

    pytester.makepyfile(generate_test_code(test_file_spec))
    pytester.makeini(f"""
    [pytest]
    {SmokeIniOption.SMOKE_MARKED_TESTS_AS_CRITICAL} = true
    """)
    args = [option, str(smoke_n), "-v"]
    with mock_column_width(150):
        result = pytester.runpytest(*args)
    assert result.ret == (ExitCode.TESTS_FAILED if num_fails else ExitCode.OK)
    result.assert_outcomes(
        passed=num_expected_selected_tests - (num_fails + num_skips),
        failed=num_fails,
        skipped=num_skips,
        deselected=num_tests_1 + num_tests_2 - num_expected_selected_tests,
    )

    test_name_idx_result_word_pairs = re.findall(
        rf"test_.+\.py::({TEST_NAME_BASE}\d)\[(\d+)\] ((?:PASSED|FAILED|SKIPPED).*?)\s{{2,}}.+", str(result.stdout)
    )
    assert len(test_name_idx_result_word_pairs) == num_expected_selected_tests
    for i, (test_name, param_idx, result_word) in enumerate(test_name_idx_result_word_pairs):
        expected_test_name = (
            f"{TEST_NAME_BASE}1" if num_critical_tests <= i < num_critical_tests + smoke_n else f"{TEST_NAME_BASE}2"
        )
        assert test_name == expected_test_name
        if i < num_critical_tests:
            # ciritical tests
            assert is_critical(int(param_idx))
            word = "FAILED" if num_fails and int(param_idx) in test2_pos_mustpass[:num_fails] else "PASSED"
            if mustpass and int(param_idx) in test2_pos_mustpass:
                assert result_word == word + " (must-pass)"
            else:
                assert result_word == word
        else:
            # regular tests
            if mustpass and num_fails:
                assert (
                    result_word == f"SKIPPED ({num_fails}/{len(test2_pos_mustpass)} must-pass "
                    f"smoke test{'s' if num_fails > 1 else ''} failed)"
                )
            else:
                assert result_word == "PASSED"


@pytest.mark.parametrize("with_hook", [True, False])
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_hook_pytest_smoke_generate_group_id(pytester: Pytester, option: str, with_hook: bool):
    """Test pytest_smoke_generate_group_id hook and custome scopes, with/without hook definition"""
    custom_scope = "my-scope"
    num_tests = 10
    n = 2
    num_expected_selected_tests = n * 2
    assert num_expected_selected_tests < num_tests
    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests)))
    if with_hook:
        pytester.makeconftest(f"""
        import pytest
        def pytest_smoke_generate_group_id(item, scope):
            if scope == "{custom_scope}":
                # group tests by odd/even index
                return item.session.items.index(item) % 2
        """)
    args = [option, str(n), "--smoke-scope", custom_scope]
    result = pytester.runpytest(*args)
    if not with_hook:
        assert result.ret == ExitCode.USAGE_ERROR
        result.stderr.re_match_lines(
            [
                f"ERROR: The logic for the custom scope '{custom_scope}' must be implemented using the "
                f"pytest_smoke_generate_group_id hook"
            ]
        )
    else:
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=num_expected_selected_tests, deselected=num_tests - num_expected_selected_tests)


@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_hook_pytest_smoke_include(pytester: Pytester, option: str):
    """Test pytest_smoke_include hook"""
    num_tests = 10
    n = 2
    num_include = 2
    num_expected_selected_tests = n + num_include
    assert num_expected_selected_tests < num_tests
    param_marker = lambda p: "smoke" if p < num_include else None  # noqa
    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests, param_marker=param_marker)))
    pytester.makeconftest("""
    import pytest
    def pytest_smoke_include(item, scope):
        # Include tests with the smoke mark as additional tests
        return item.get_closest_marker("smoke")
    """)
    args = [option, str(n)]
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=num_expected_selected_tests, deselected=num_tests - num_expected_selected_tests)


@pytest.mark.parametrize("n", ["2", "10", "100", "20%", "100%"])
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_hook_pytest_smoke_exclude(pytester: Pytester, option: str, n: str):
    """Test pytest_smoke_exclude hook"""
    num_tests = 20
    divisor = 3
    num_selectable_tests = int(sum([x % divisor not in [1, 2] for x in range(num_tests)]))
    is_scale = n.endswith("%")
    if is_scale:
        num_expected_selected_tests = scale_down(num_selectable_tests, float(n[:-1]))
    else:
        num_expected_selected_tests = min([int(n), num_selectable_tests])

    def param_marker(i):
        reminder = i % divisor
        if reminder == 1:
            return "skip"
        elif reminder == 2:
            return "xfail"

    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests, param_marker=param_marker)))
    pytester.makeconftest("""
    import pytest
    def pytest_smoke_exclude(item, scope):
        # Exclude tests with skip/xfail marks
        return any(item.get_closest_marker(m) for m in ["skip", "xfail"])
    """)

    args = [option, str(n)]
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=num_expected_selected_tests, deselected=num_tests - num_expected_selected_tests)


@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_ini_option_smoke_default_n(pytester: Pytester, option: str):
    """Test smoke_default_n INI option"""
    num_tests = 10
    default_n = 3
    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests)))
    pytester.makeini(f"""
    [pytest]
    {SmokeIniOption.SMOKE_DEFAULT_N} = {default_n}
    """)

    result = pytester.runpytest(option)
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=default_n, deselected=num_tests - default_n)


@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_ini_option_smoke_default_scope(pytester: Pytester, option: str):
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
    result = pytester.runpytest(option)
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=1, deselected=num_tests_1 + num_tests_2 - 1)


@requires_xdist
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
@pytest.mark.parametrize("dist_option", [None, "--dist=load", "-d"])
@pytest.mark.parametrize("value", ["true", "false", None])
def test_smoke_ini_option_smoke_default_xdist_dist_by_scope(
    pytester: Pytester, option: str, value: Optional[str], dist_option: Optional[str]
):
    """Test smoke_default_xdist_dist_by_scope INI option.

    The plugin should extend the pytest-xdist to use the custom scheduler when the INI option value is true and
    when no dist option (--dist or -d) is explicitly given
    """
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
    args = [option, str(smoke_n), "-v", "-n", "2"]
    if dist_option:
        args.append(dist_option)

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


@pytest.mark.parametrize("option", SMOKE_OPTIONS)
@pytest.mark.parametrize("value", [None, "true", "false"])
def test_smoke_ini_option_smoke_marked_tests_as_critical(pytester: Pytester, option: str, value: Optional[str]):
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
    with mock_column_width(150):
        result = pytester.runpytest(option, "-v")
    assert result.ret == ExitCode.OK
    test_nums = re.findall(rf"test_.+\.py::{TEST_NAME_BASE}(\d).+", str(result.stdout))
    if is_enabled:
        assert sorted(test_nums, reverse=True) == test_nums
        num_passes = 1 + num_tests_2
    else:
        assert sorted(test_nums) == test_nums
        num_passes = len(test_file_spec.test_specs)
    result.assert_outcomes(passed=num_passes, deselected=num_tests_1 + num_tests_2 - num_passes)


@pytest.mark.filterwarnings("ignore::pluggy.PluggyTeardownRaisedWarning")
@pytest.mark.parametrize("n", ["-1", "0", "0.5", "1.1", "foo", " -1%", "0%", "101%", "bar%"])
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_invalid_n(pytester: Pytester, option: str, n: str):
    """Test the option with invalid values"""
    result = pytester.runpytest(option, n)
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines(
        [rf"ERROR: The smoke N value must be a positive number or a valid percentage\. '{n}' was given"]
    )


@pytest.mark.parametrize("scope", [*SmokeScope])
def test_smoke_scope_without_n_option(pytester: Pytester, scope: str):
    """Test --smoke-scope option can not be used without other smoke option"""
    result = pytester.runpytest("--smoke-scope", scope)
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines(
        ["ERROR: The --smoke-scope option requires one of --smoke, --smoke-last, or --smoke-random to be specified"]
    )


@pytest.mark.parametrize(
    "options", [comb for r in range(2, len(SMOKE_OPTIONS) + 1) for comb in combinations(SMOKE_OPTIONS, r)]
)
def test_smoke_options_are_mutually_exclusive(pytester: Pytester, options: Sequence[str]):
    """Test smoke options are mutually exclusive"""
    result = pytester.runpytest(*options)
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines(["ERROR: --smoke, --smoke-last, and --smoke-random options are mutually exclusive"])


@pytest.mark.parametrize("ini_option", SMOKE_INI_OPTIONS)
@pytest.mark.parametrize("value", ["foo", ""])
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_ini_option_with_invalid_value(pytester: Pytester, option: str, ini_option: str, value: str):
    """Test INI options with an invalid value are handled as a usage error"""
    pytester.makepyfile(generate_test_code(TestFuncSpec()))
    pytester.makeini(f"""
    [pytest]
    {ini_option} = {value}
    """)
    args = [option]
    if ini_option == SmokeIniOption.SMOKE_DEFAULT_XDIST_DIST_BY_SCOPE:
        args.extend(["-n", "2"])
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.USAGE_ERROR
