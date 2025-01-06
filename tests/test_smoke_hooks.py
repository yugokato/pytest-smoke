import re

import pytest
from pytest import ExitCode, Pytester

from pytest_smoke.utils import scale_down
from tests.helper import TEST_NAME_BASE, TestFuncSpec, generate_test_code


@pytest.mark.parametrize("with_hook", [True, False])
def test_smoke_hook_pytest_smoke_generate_group_id(pytester: Pytester, with_hook: bool):
    """Test pytest_smoke_generate_group_id hook and custome scopes, with/without hook definition"""
    custom_scope = "my-scope"
    num_tests = 10
    smoke_n = 2
    num_expected_selected_tests = smoke_n * 2
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
    result = pytester.runpytest("--smoke", str(smoke_n), "--smoke-scope", custom_scope)
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


def test_smoke_hook_pytest_smoke_include(pytester: Pytester):
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
    result = pytester.runpytest("--smoke", str(n))
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=num_expected_selected_tests, deselected=num_tests - num_expected_selected_tests)


@pytest.mark.parametrize("n", ["2", "10", "100", "20%", "100%"])
def test_smoke_hook_pytest_smoke_exclude(pytester: Pytester, n: str):
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
    result = pytester.runpytest("--smoke", str(n))
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=num_expected_selected_tests, deselected=num_tests - num_expected_selected_tests)


@pytest.mark.parametrize("with_hook", [True, False])
def test_smoke_hook_pytest_smoke_sort_by_select_mode(pytester: Pytester, with_hook: bool):
    """Test custom select mode using the pytest_smoke_sort_by_select_mode hook, with/without hook
    definition
    """
    custom_select_mode = "my-select-mode"
    num_tests = 10
    smoke_n = 2
    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests)))
    if with_hook:
        pytester.makeconftest("""
        import pytest
        def pytest_smoke_sort_by_select_mode(items):
            # sort tests by odd/even index
            return sorted(items, key=lambda x: items.index(x) % 2)
        """)
    result = pytester.runpytest("--smoke", str(smoke_n), "--smoke-select-mode", custom_select_mode, "-v")
    if not with_hook:
        assert result.ret == ExitCode.USAGE_ERROR
        result.stderr.re_match_lines(
            [
                f"ERROR: The custom sort logic for the select mode '{custom_select_mode}' must be implemented "
                f"using the pytest_smoke_sort_by_select_mode hook"
            ]
        )
    else:
        assert result.ret == ExitCode.OK
        result.assert_outcomes(passed=smoke_n, deselected=num_tests - smoke_n)
        matched_test_nums = re.findall(rf"test_.+\.py::{TEST_NAME_BASE}\[(\d+)\]", str(result.stdout))
        assert len(matched_test_nums) == smoke_n
        assert [int(n) for n in matched_test_nums] == sorted([x for x in range(num_tests)], key=lambda x: x % 2)[
            :smoke_n
        ]
