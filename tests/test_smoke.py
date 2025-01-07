import re
from typing import Optional

import pytest
from pytest import ExitCode, Pytester

from pytest_smoke import smoke
from pytest_smoke.types import SmokeIniOption, SmokeScope, SmokeSelectMode
from tests.helper import (
    PARAMETRIZED_ARG_NAME_FUNC,
    TEST_NAME_BASE,
    TestFileSpec,
    TestFuncSpec,
    generate_test_code,
    get_num_tests,
    get_num_tests_to_be_selected,
    requires_xdist,
)


def test_smoke_command_help(pytester: Pytester):
    """Test pytest command help for this plugin"""
    result = pytester.runpytest("-h")
    assert result.ret == ExitCode.OK, str(result.stderr)
    stdout = str(result.stdout)
    pattern1 = (
        r"\n"
        + r"Smoke testing:\n"
        + (r"  --smoke=\[N\]\s+.+")
        + (r"  --smoke-scope=SCOPE\s+.+" + r"\n".join(rf"\s+- {s}: .+" for s in SmokeScope))
        + (r"  --smoke-select-mode=MODE\s+.+" + r"\n".join(rf"\s+- {s}: .+" for s in SmokeSelectMode))
        + r"\n"
    )
    assert re.search(pattern1, stdout, re.DOTALL)

    pattern2 = r"\[pytest\] ini-options.+" + r"\n".join(
        rf"  {opt} \([^)]+\):\s+\[pytest-smoke\] .+" for opt in SmokeIniOption
    )
    assert re.search(pattern2, stdout, re.DOTALL)


def test_smoke_show_markers(pytester: Pytester):
    """Test the custom marker information provided by the plugin"""
    result = pytester.runpytest("--markers")
    assert result.ret == ExitCode.OK
    result.stdout.re_match_lines([r"@pytest\.mark\.smoke\(\*, mustpass=False, runif=True\): .+"])


@pytest.mark.usefixtures("generate_test_files")
def test_smoke_no_option(pytester: Pytester, test_file_specs: list[TestFileSpec]):
    """Test the plugin does not affect pytest when no plugin options are given"""
    num_all_tests = get_num_tests(*test_file_specs)
    result = pytester.runpytest()
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=num_all_tests)


@pytest.mark.usefixtures("generate_test_files")
@pytest.mark.parametrize("scope", [None, *SmokeScope])
@pytest.mark.parametrize("n", [None, "1", "5", "15", "25", "35", str(2**32 - 1), "1%", "1.23%", "10%", "33%", "100%"])
def test_smoke_n(pytester: Pytester, test_file_specs: list[TestFileSpec], n: Optional[str], scope: Optional[str]):
    """Test various smoke N values with/without a smoke scope"""
    num_all_tests = get_num_tests(*test_file_specs)
    num_tests_to_be_selected = get_num_tests_to_be_selected(test_file_specs, n, scope)
    args = ["--smoke"]
    if n:
        args.append(n)
    if scope:
        args.extend(["--smoke-scope", scope])
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=num_tests_to_be_selected, deselected=num_all_tests - num_tests_to_be_selected)


@pytest.mark.parametrize("select_mode", [None, *SmokeSelectMode])
def test_smoke_select_mode(pytester: Pytester, select_mode: Optional[str]):
    """Test the predefined test selection logic with/without the --smoke-select-mode option"""
    smoke_n = 5
    num_tests = 100
    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests)))
    args = ["--smoke", str(smoke_n), "--co", "-q"]
    if select_mode:
        args.extend(["--smoke-select-mode", select_mode])

    prev_test_nums = None
    for i in range(2):
        result = pytester.runpytest(*args)
        assert result.ret == ExitCode.OK
        result.assert_outcomes(deselected=num_tests - smoke_n)

        matched_test_nums = re.findall(rf"test_.+\.py::{TEST_NAME_BASE}\[(\d+)\]", str(result.stdout))
        assert len(matched_test_nums) == smoke_n
        test_nums = [int(n) for n in matched_test_nums]

        if select_mode == SmokeSelectMode.LAST:
            assert test_nums == [n for n in range(num_tests)][-smoke_n:]
        elif select_mode == SmokeSelectMode.RANDOM:
            assert sorted(test_nums) == test_nums
        else:
            assert test_nums == [n for n in range(num_tests)][:smoke_n]

        if prev_test_nums:
            if select_mode == SmokeSelectMode.RANDOM:
                assert test_nums != prev_test_nums
            else:
                assert test_nums == prev_test_nums
        else:
            prev_test_nums = test_nums


@pytest.mark.parametrize("num_fails", [0, 1, 2])
@pytest.mark.parametrize("runif", [None, False, True])
@pytest.mark.parametrize("mustpass", [None, False, True])
def test_smoke_marker_critical_tests(pytester: Pytester, mustpass: bool, runif: Optional[bool], num_fails: int):
    """Test @pytest.mark.smoke marker with/without the optional mustpass and runif kwargs"""

    def is_critical(i):
        return bool(i % 2)

    def param_marker(i):
        mark = "smoke"
        if is_critical(i):
            kwargs = {}
            if i in test2_pos_mustpass and mustpass is not None:
                kwargs["mustpass"] = mustpass
            if i in test2_pos_with_runif and runif is not None:
                kwargs["runif"] = runif
            if kwargs:
                args = ", ".join(f"{k}={v}" for k, v in kwargs.items())
                mark = f"{mark}({args})"
            return mark
        else:
            return None

    smoke_n = 4
    num_tests_1 = 10
    num_tests_2 = 20
    num_mustpass = 2
    num_critical_with_runif = 3
    test2_pos_critical = list(filter(is_critical, range(num_tests_2)))
    test2_pos_mustpass = test2_pos_critical[:num_mustpass]
    test2_pos_with_runif = test2_pos_critical[-num_critical_with_runif:]
    func_body = f"\tassert {PARAMETRIZED_ARG_NAME_FUNC} not in {test2_pos_mustpass[:num_fails]}" if num_fails else None
    test_file_spec = TestFileSpec(
        [
            TestFuncSpec(num_params=num_tests_1),
            TestFuncSpec(num_params=num_tests_2, param_marker=param_marker, func_body=func_body),
        ]
    )
    num_critical_tests = sum([is_critical(i) for i in range(num_tests_2)])
    if runif is False:
        num_critical_tests -= len(test2_pos_with_runif)
    num_regular_tests = smoke_n * len(test_file_spec.test_specs)
    num_expected_selected_tests = num_regular_tests + num_critical_tests
    num_skips = num_regular_tests if mustpass and num_fails else 0
    assert all(
        [
            smoke_n < num_tests_1,
            smoke_n < num_tests_2,
            smoke_n < num_critical_tests,
            smoke_n + num_critical_tests < num_tests_2,
            num_fails <= num_mustpass,
            num_mustpass < num_critical_tests,
            num_critical_with_runif < num_critical_tests,
            all((p < num_tests_2 and is_critical(p)) for p in test2_pos_mustpass),
        ]
    ), "Invalid test conditions"

    pytester.makepyfile(generate_test_code(test_file_spec))
    pytester.makeini(f"""
    [pytest]
    {SmokeIniOption.SMOKE_MARKED_TESTS_AS_CRITICAL} = true
    """)
    result = pytester.runpytest("--smoke", str(smoke_n), "-v")
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


@requires_xdist
@pytest.mark.usefixtures("generate_test_files")
@pytest.mark.parametrize("select_mode", [None, *SmokeSelectMode])
@pytest.mark.parametrize("scope", [None, *SmokeScope])
def test_smoke_xdist(
    pytester: Pytester, test_file_specs: list[TestFileSpec], scope: Optional[str], select_mode: Optional[str]
):
    """Test basic plugin functionality with pytest-xdist.

    The plugin should handle the following points:
    - Report the number of deselected tests in xdist controller
    - When the select mode is random, sets a common random seeds so that all workers can collect the exact same
      tests
    """
    smoke_n = 3
    num_all_tests = get_num_tests(*test_file_specs)
    num_tests_to_be_selected = get_num_tests_to_be_selected(test_file_specs, str(smoke_n), scope)
    args = ["--smoke", str(smoke_n), "-n", "2", "-v"]
    if scope:
        args.extend(["--smoke-scope", scope])
    if select_mode:
        args.extend(["--smoke-select-mode", select_mode])
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK
    result.assert_outcomes(passed=num_tests_to_be_selected, deselected=num_all_tests - num_tests_to_be_selected)


@requires_xdist
@pytest.mark.parametrize("select_mode", [None, *SmokeSelectMode])
def test_smoke_xdist_disabled(pytester: Pytester, select_mode: Optional[str]):
    """Test that pytest-smoke does not access the pytest-xdist plugin when it is install but explicitly disabled"""
    assert smoke.is_xdist_installed
    num_tests = 10
    pytester.makepyfile(generate_test_code(TestFuncSpec(num_params=num_tests)))
    args = ["--smoke", "-p", "no:xdist"]
    if select_mode:
        args.extend(["--smoke-select-mode", select_mode])
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK
    assert not smoke.is_xdist_installed
    result.assert_outcomes(passed=1, deselected=num_tests - 1)


@pytest.mark.filterwarnings("ignore::pluggy.PluggyTeardownRaisedWarning")
@pytest.mark.parametrize("n", ["-1", "0", "0.5", "1.1", "foo", " -1%", "0%", "101%", "bar%"])
def test_smoke_invalid_n(pytester: Pytester, n: str):
    """Test the option with invalid values"""
    result = pytester.runpytest("--smoke", n)
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines(
        [rf"ERROR: The smoke N value must be a positive number or a valid percentage\. '{n}' was given"]
    )


@pytest.mark.parametrize("option", ["--smoke-scope", "--smoke-select-mode"])
def test_smoke_without_n_option(pytester: Pytester, option: str):
    """Test the --smoke option is required to use any functionality provided by the plugin"""
    result = pytester.runpytest(option, "foo")
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines([r"ERROR: The --smoke option is requierd to use the pytest-smoke functionality"])
