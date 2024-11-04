import pytest
from pytest import Testdir

pytest_plugins = "pytester"


NUM_PARAMETRIZATION1 = 5
NUM_PARAMETRIZATION2 = 10


@pytest.mark.parametrize(
    "n", [None, 1, 2, NUM_PARAMETRIZATION1, NUM_PARAMETRIZATION1 + 1, NUM_PARAMETRIZATION2, NUM_PARAMETRIZATION2 + 1]
)
def test_smoke_with_valid_n(testdir: Testdir, n):
    """Test --smoke option with no value, or with positive numbers"""
    assert NUM_PARAMETRIZATION1 < NUM_PARAMETRIZATION2
    testdir.makepyfile(f"""
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

    args = ["--smoke"]
    if n:
        args.append(n)
    result = testdir.runpytest(*args)

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
    result.assert_outcomes(passed=num_passed)


@pytest.mark.parametrize("n", [-1, 0, "foo"])
def test_smoke_with_invalid_n(testdir: Testdir, n):
    """Test --smoke option with invalid values"""
    testdir.makepyfile(
        """
        import pytest
        def test_something:
            pass
    """
    )
    result = testdir.runpytest("--smoke", n)
    assert "The value must be a positive number if given." in str(result.stderr)
