import re
from collections.abc import Sequence
from itertools import combinations
from typing import Optional

import pytest
from pytest import ExitCode, Pytester

from pytest_smoke.plugin import SmokeScope
from tests.helper import (
    TestFileSpec,
    get_num_tests,
    get_num_tests_to_be_selected,
)

SMOKE_OPTIONS = ["--smoke", "--smoke-last", "--smoke-random"]


def test_smoke_command_help(pytester: Pytester):
    """Test pytest command help for this plugin"""
    result = pytester.runpytest("-h")
    assert result.ret == ExitCode.OK, str(result.stderr)
    pattern = (
        r"Smoke testing:\n"
        r"  --smoke=\[N\]\s+.+"
        r"  --smoke-last=\[N\]\s+.+"
        r"  --smoke-random=\[N\]\s+.+"
        r"  --smoke-scope=SCOPE\s+.+"
    )
    assert re.search(pattern, str(result.stdout), re.DOTALL)


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
    """Test all combinations of smoke options and scopes with various N values"""
    num_all_tests = get_num_tests(*test_file_specs)
    num_tests_to_be_selected = get_num_tests_to_be_selected(test_file_specs, n, scope)
    args = [option]
    if n:
        args.append(n)
    if scope:
        args.extend(["--smoke-scope", scope])
    result = pytester.runpytest(*args)
    result.assert_outcomes(passed=num_tests_to_be_selected, deselected=num_all_tests - num_tests_to_be_selected)


@pytest.mark.filterwarnings("ignore::pluggy.PluggyTeardownRaisedWarning")
@pytest.mark.parametrize("n", ["-1", "0", "0.5", "1.1", "foo", " -1%", "0%", "101%", "bar%"])
@pytest.mark.parametrize("option", SMOKE_OPTIONS)
def test_smoke_with_invalid_n(pytester: Pytester, option: Optional[str], n: str):
    """Test the option with invalid values"""
    result = pytester.runpytest(option, n)
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines(
        [rf".+ {option}: The value must be a positive number or a valid percentage if given\."]
    )


@pytest.mark.filterwarnings("ignore::pluggy.PluggyTeardownRaisedWarning")
@pytest.mark.parametrize("scope", [*SmokeScope])
def test_smoke_scope_without_n_option(pytester: Pytester, scope: str):
    """Test --smoke-scope option can not be used without other smoke option"""
    result = pytester.runpytest("--smoke-scope", scope)
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines(
        ["ERROR: The --smoke-scope option requires one of --smoke, --smoke-last, or --smoke-random to be specified"]
    )


@pytest.mark.filterwarnings("ignore::pluggy.PluggyTeardownRaisedWarning")
@pytest.mark.parametrize(
    "options", [comb for r in range(2, len(SMOKE_OPTIONS) + 1) for comb in combinations(SMOKE_OPTIONS, r)]
)
def test_smoke_options_are_mutually_exclusive(pytester: Pytester, options: Sequence[str]):
    """Test smoke options are mutually exclusive"""
    result = pytester.runpytest(*options)
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines(["ERROR: --smoke, --smoke-last, and --smoke-random options are mutually exclusive"])
