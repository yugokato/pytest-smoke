import re
from collections.abc import Sequence
from itertools import combinations
from typing import Optional

import pytest
from pytest import ExitCode, Pytester

from pytest_smoke import smoke
from pytest_smoke.types import SmokeIniOption, SmokeScope
from pytest_smoke.utils import scale_down
from tests.helper import TestFileSpec, TestFuncSpec, generate_test_code, get_num_tests, get_num_tests_to_be_selected

if smoke.is_xdist_installed:
    from xdist.scheduler import LoadScheduling, LoadScopeScheduling

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
@pytest.mark.parametrize("scope", [None, *SmokeScope])
@pytest.mark.parametrize("n", [None, "1", "5", "15", "25", "35", str(2**32 - 1), "1%", "1.23%", "10%", "33%", "100%"])
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_with_valid_n(
    pytester: Pytester,
    test_file_specs: list[TestFileSpec],
    option: str,
    n: Optional[str],
    scope: Optional[str],
):
    """Test all combinations of smoke options and predefined scopes with various N values"""
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


@pytest.mark.parametrize("with_hook", [True, False])
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_hook_pytest_smoke_generate_group_id(pytester: Pytester, option: str, with_hook):
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
def test_smoke_hook_pytest_smoke_always_run(pytester: Pytester, option: str):
    """Test pytest_smoke_always_run hook"""
    num_tests = 10
    n = 2
    num_tests_always_run = 2
    num_expected_selected_tests = n + num_tests_always_run
    assert num_expected_selected_tests < num_tests
    param_marker = lambda p: "smoke" if p < num_tests_always_run else None  # noqa
    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests, param_marker=param_marker)))
    pytester.makeconftest("""
    import pytest
    def pytest_smoke_always_run(item, scope):
        # Always run tests with the smoke mark
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
@pytest.mark.parametrize("dist", [None, "load", "loadscope"])
@pytest.mark.parametrize("value", ["true", "false"])
def test_smoke_ini_option_smoke_default_xdist_dist_by_scope(pytester: Pytester, option: str, value: str, dist: str):
    """Test smoke_default_xdist_dist_by_scope INI option. The custom scheduler should be used only when the INI option
    value is true and when --dist option is not given
    """
    num_tests_1 = 5
    num_tests_2 = 10
    smoke_n = 2
    test_file_spec = TestFileSpec([TestFuncSpec(num_params=num_tests_1), TestFuncSpec(num_params=num_tests_2)])
    pytester.makepyfile(generate_test_code(test_file_spec))
    pytester.makeini(f"""
    [pytest]
    {SmokeIniOption.SMOKE_DEFAULT_XDIST_DIST_BY_SCOPE} = {value}
    """)
    args = [option, str(smoke_n), "-v", "-n", "2"]
    if dist:
        args.extend(["--dist", dist])
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK
    num_passed = len(test_file_spec.test_specs) * smoke_n
    result.assert_outcomes(passed=num_passed, deselected=num_tests_1 + num_tests_2 - num_passed)

    if dist == "load":
        scheduler = LoadScheduling.__name__
    elif dist == "loadscope":
        scheduler = LoadScopeScheduling.__name__
    else:
        if value == "true":
            scheduler = SmokeScopeScheduling.__name__
        else:
            # pytest-xdist default
            scheduler = LoadScheduling.__name__
    result.stdout.re_match_lines(f"scheduling tests via {scheduler}")


@pytest.mark.filterwarnings("ignore::pluggy.PluggyTeardownRaisedWarning")
@pytest.mark.parametrize("n", ["-1", "0", "0.5", "1.1", "foo", " -1%", "0%", "101%", "bar%"])
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_with_invalid_n(pytester: Pytester, option: str, n: str):
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


@requires_xdist
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_with_xdist_disabled(pytester: Pytester, option: str):
    """Test that pytest-smoke does not access the pytest-xdist plugin when it is explicitly disabled"""
    num_tests = 10
    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests)))
    args = [option, "-p", "no:xdist"]
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=1, deselected=num_tests - 1)
