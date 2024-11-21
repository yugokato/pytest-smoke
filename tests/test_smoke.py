import re
from itertools import combinations

import pytest
from pytest import ExitCode, Pytester

from pytest_smoke.utils import calculate_scaled_value

NUM_PARAMETRIZATION1 = 10
NUM_PARAMETRIZATION2 = 100
OPTIONS = ["--smoke", "--smoke-last", "--smoke-random"]


def test_smoke_command_help(pytester: Pytester):
    """Test pytest command help for this plugin"""
    result = pytester.runpytest("-h")
    result.stdout.re_match_lines([r"Smoke testing:", *(rf"\s+{opt}=\[N\]\s+.+" for opt in OPTIONS)])


@pytest.mark.parametrize("n", ["5", "5%"])
@pytest.mark.parametrize("option", OPTIONS)
def test_smoke_collection(pytester: Pytester, option, n):
    """Test the result of test collection"""
    test_name = "test_something"
    num_tests_1 = 1
    num_tests_2 = NUM_PARAMETRIZATION1
    num_tests_3 = NUM_PARAMETRIZATION2
    num_expected_selected_tests_1 = num_tests_1
    if n.endswith("%"):
        num_expected_selected_tests_2 = int(calculate_scaled_value(num_tests_2, float(n[:-1])))
        num_expected_selected_tests_3 = int(calculate_scaled_value(num_tests_3, float(n[:-1])))
    else:
        num_expected_selected_tests_2 = int(n)
        num_expected_selected_tests_3 = int(n)
    assert num_expected_selected_tests_2 < num_tests_2
    assert num_expected_selected_tests_3 < num_tests_3
    num_tests = num_tests_1 + num_tests_2 + num_tests_3
    num_expected_selected_tests = (
        num_expected_selected_tests_1 + num_expected_selected_tests_2 + num_expected_selected_tests_3
    )
    pytester.makepyfile(
        test_1=f"""
        def {test_name}():
            pass
        """,
        test_2=f"""
        import pytest

        @pytest.mark.parametrize("p", range({num_tests_2}))
        def {test_name}(p):
            pass
        """,
        test_3=f"""
        import pytest

        class Test:
            @pytest.mark.parametrize("p", range({num_tests_3}))
            def {test_name}(self, p):
                pass
        """,
    )

    args = [option, n, "--collect-only", "-q"]
    prev_collected_tests = None
    pattern_test_id = rf"test_\d\.py::(?:Test::)?{test_name}(?:\[\d*\])?"
    for i in range(2):
        result = pytester.runpytest(*args)
        assert result.ret == ExitCode.OK
        result.assert_outcomes(deselected=num_tests - num_expected_selected_tests)
        collected_tests = re.findall(pattern_test_id, str(result.stdout))
        assert len(collected_tests) == num_expected_selected_tests
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
        "1",
        str(NUM_PARAMETRIZATION1 - 1),
        str(NUM_PARAMETRIZATION1),
        str(NUM_PARAMETRIZATION1 + 1),
        str(NUM_PARAMETRIZATION2 - 1),
        str(NUM_PARAMETRIZATION2),
        str(NUM_PARAMETRIZATION2 + 1),
        "1%",
        "10%",
        "10.5%",
        "50%",
        "100%",
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
            
        class Test:
            @pytest.mark.parametrize("p", range({NUM_PARAMETRIZATION2}))
            def test_something3(self, p):
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
        if n.endswith("%"):
            scale = float(n[:-1])
            num_passed += int(calculate_scaled_value(NUM_PARAMETRIZATION1, scale)) + int(
                calculate_scaled_value(NUM_PARAMETRIZATION2, scale)
            )
        else:
            num = int(n)
            if num <= NUM_PARAMETRIZATION1:
                num_passed += num * 2
            elif num <= NUM_PARAMETRIZATION2:
                num_passed += NUM_PARAMETRIZATION1 + num
            else:
                num_passed += NUM_PARAMETRIZATION1 + NUM_PARAMETRIZATION2
    else:
        num_passed += 2
    result.assert_outcomes(passed=num_passed, deselected=num_tests - num_passed)


@pytest.mark.filterwarnings("ignore::pluggy.PluggyTeardownRaisedWarning")
@pytest.mark.parametrize("n", ["-1", "0", "1.1", "foo", " -1%", "0%", "101%", "bar%"])
@pytest.mark.parametrize("option", OPTIONS)
def test_smoke_with_invalid_n(pytester: Pytester, option, n):
    """Test the option with invalid values"""
    result = pytester.runpytest(option, n)
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines(
        [rf".+ {option}: The value must be a positive number or a valid percentage if given\."]
    )


@pytest.mark.filterwarnings("ignore::pluggy.PluggyTeardownRaisedWarning")
@pytest.mark.parametrize("options", [comb for r in range(2, len(OPTIONS) + 1) for comb in combinations(OPTIONS, r)])
def test_smoke_options_are_mutually_exclusive(pytester: Pytester, options):
    """Test smoke options are mutually exclusive"""
    result = pytester.runpytest(*options)
    assert result.ret == ExitCode.USAGE_ERROR
    result.stderr.re_match_lines(["ERROR: --smoke, --smoke-last, and --smoke-random are mutually exclusive"])
