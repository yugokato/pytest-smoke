import re
from itertools import combinations

import pytest
from pytest import ExitCode, Pytester

NUM_PARAMETRIZATION1 = 5
NUM_PARAMETRIZATION2 = 10
OPTIONS = ["--smoke", "--smoke-last", "--smoke-random"]


def test_smoke_command_help(pytester: Pytester):
    """Test pytest command help for this plugin"""
    result = pytester.runpytest("-h")
    result.stdout.re_match_lines([r"Smoke testing:", *(rf"\s+{opt}=\[N\]\s+.+" for opt in OPTIONS)])


@pytest.mark.parametrize("option", OPTIONS)
def test_smoke_collection(pytester: Pytester, option):
    """Test the result of test collection"""
    num_tests = 30
    test_name = "test_something"
    pattern_test_id = rf".+::{test_name}\[\d*\]"
    pytester.makepyfile(f"""
        import pytest

        @pytest.mark.parametrize("p", range({num_tests}))
        def {test_name}(p):
            pass
        """)

    n = 10
    args = [option, n, "--collect-only", "-q"]
    prev_collected_tests = None
    for i in range(2):
        result = pytester.runpytest(*args)
        assert result.ret == ExitCode.OK
        result.assert_outcomes(deselected=num_tests - n)
        collected_tests = re.findall(pattern_test_id, str(result.stdout))
        assert len(collected_tests) == n
        if prev_collected_tests:
            if option == "--smoke-random":
                assert prev_collected_tests != collected_tests
            else:
                assert prev_collected_tests == collected_tests
        prev_collected_tests = collected_tests


@pytest.mark.parametrize(
    "n",
    [
        None,
        1,
        NUM_PARAMETRIZATION1 - 1,
        NUM_PARAMETRIZATION1,
        NUM_PARAMETRIZATION1 + 1,
        NUM_PARAMETRIZATION2,
        NUM_PARAMETRIZATION2 + 1,
    ],
)
@pytest.mark.parametrize("option", OPTIONS)
def test_smoke_with_valid_n(pytester: Pytester, option, n):
    """Test the option with no value, or with positive numbers"""
    assert NUM_PARAMETRIZATION1 < NUM_PARAMETRIZATION2
    test_file = pytester.makepyfile(f"""
        import pytest
        
        def test_something1():
            pass
            
        @pytest.mark.parametrize("p", range({NUM_PARAMETRIZATION1}))
        def test_something2(p):
            pass
            
        @pytest.mark.parametrize("p", range({NUM_PARAMETRIZATION2}))
        def test_something3(p):
            pass
    """)
    num_tests = len(pytester.getitems(test_file))

    args = [option]
    if n:
        args.append(n)
    result = pytester.runpytest(*args)
    assert result.ret == ExitCode.OK

    num_passed = 1
    if n:
        if n <= NUM_PARAMETRIZATION1:
            num_passed += n * 2
        elif n <= NUM_PARAMETRIZATION2:
            num_passed += NUM_PARAMETRIZATION1 + n
        else:
            num_passed += NUM_PARAMETRIZATION1 + NUM_PARAMETRIZATION2
    else:
        num_passed += 2
    result.assert_outcomes(passed=num_passed, deselected=num_tests - num_passed)


@pytest.mark.filterwarnings("ignore::pluggy.PluggyTeardownRaisedWarning")
@pytest.mark.parametrize("n", [-1, 0, "foo"])
@pytest.mark.parametrize("option", OPTIONS)
def test_smoke_with_invalid_n(pytester: Pytester, option, n):
    """Test the option with invalid values"""
    result = pytester.runpytest(option, n)
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines([rf".+ {option}: The value must be a positive number if given\."])


@pytest.mark.filterwarnings("ignore::pluggy.PluggyTeardownRaisedWarning")
@pytest.mark.parametrize("options", [comb for r in range(2, len(OPTIONS) + 1) for comb in combinations(OPTIONS, r)])
def test_smoke_options_are_mutually_exclusive(pytester: Pytester, options):
    """Test smoke options are mutually exclusive"""
    result = pytester.runpytest(*options)
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines(["ERROR: --smoke, --smoke-last, and --smoke-random are mutually exclusive"])
