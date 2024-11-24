import pytest
from pytest import Pytester

from pytest_smoke.plugin import SmokeScope
from tests.helper import TestClassSpec, TestFileSpec, TestFuncSpec, generate_test_code

pytest_plugins = "pytester"


@pytest.hookimpl(trylast=True)
def pytest_make_parametrize_id(val, argname):
    if isinstance(val, SmokeScope):
        val = str(val)
    return f"{argname}={repr(val)}"


@pytest.fixture(scope="session")
def test_file_specs() -> list[TestFileSpec]:
    """Specifications for test files to generate"""
    # file1: A test file with non-parametrized test functions
    test_file_spec1 = TestFileSpec([TestFuncSpec(), TestFuncSpec()])
    # file2: A test file with parametrized test functions
    test_file_spec2 = TestFileSpec([TestFuncSpec(num_params=10), TestFuncSpec(num_params=20)])
    # file3: A test file with test classes, with/without class-level parametrization
    test_file_spec3 = TestFileSpec(
        [
            TestClassSpec("Test1", [TestFuncSpec(num_params=5), TestFuncSpec()]),
            TestClassSpec("Test2", [TestFuncSpec(num_params=5), TestFuncSpec(num_params=10)]),
            TestClassSpec("Test3", [TestFuncSpec(num_params=3), TestFuncSpec()], num_params=2),
        ]
    )
    # file4: A test file with a mix of everything above
    test_file_spec4 = TestFileSpec(
        [*test_file_spec1.test_specs, *test_file_spec2.test_specs, *test_file_spec3.test_specs]
    )
    return [test_file_spec1, test_file_spec2, test_file_spec3, test_file_spec4]


@pytest.fixture
def generate_test_files(pytester: Pytester, test_file_specs: list[TestFileSpec]):
    """Generate test files with given test file specs"""
    test_files = {}
    for i, test_file_spec in enumerate(test_file_specs, start=1):
        test_files[f"test_{i}"] = generate_test_code(test_file_spec)
    pytester.makepyfile(**test_files)
