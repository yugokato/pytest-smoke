from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pytest
from pytest import Pytester
from pytest_mock import MockerFixture

from pytest_smoke import smoke

if TYPE_CHECKING:
    from pytest import Item


if os.environ.get("IGNORE_XDIST") == "true":
    smoke.is_xdist_installed = False

from pytest_smoke.compat import StrEnum
from tests.helper import TestClassSpec, TestFileSpec, TestFuncSpec, generate_test_code, patch_runpytest

Pytester.runpytest = patch_runpytest(Pytester.runpytest)
pytest_plugins = "pytester"


def pytest_runtest_setup(item: Item) -> None:
    if item.get_closest_marker("xdist") and not smoke.is_xdist_installed:
        pytest.skip(reason="pytest-xdist is required")


@pytest.hookimpl(trylast=True)
def pytest_make_parametrize_id(val: Any, argname: str) -> str:
    if isinstance(val, StrEnum):
        val = str(val)
    return f"{argname}={val!r}"


@pytest.fixture(autouse=True)
def mock_is_xdist_installed(mocker: MockerFixture) -> None:
    """Mock the smoke.is_xdist_installed flag value to limit the effect of a change the plugin will make during some
    tests to be within a test
    """
    mocker.patch.object(smoke, "_is_xdist_installed", return_value=smoke.is_xdist_installed)


@pytest.fixture(scope="session")
def test_file_specs() -> list[TestFileSpec]:
    """Specifications for test files to generate"""
    # file1: Non-parametrized test functions
    test_file_spec1 = TestFileSpec([TestFuncSpec(), TestFuncSpec()])
    # file2: With parametrized test functions
    test_file_spec2 = TestFileSpec([TestFuncSpec(), TestFuncSpec(num_params=10), TestFuncSpec(num_params=20)])
    # file3: Test classes with/without class-level parametrization and with/without nested test classes
    test_file_spec3 = TestFileSpec(
        [
            TestClassSpec("Test1", [TestFuncSpec(), TestFuncSpec()]),
            TestClassSpec("Test2", [TestFuncSpec(), TestFuncSpec(num_params=5), TestFuncSpec(num_params=10)]),
            TestClassSpec("Test3", [TestFuncSpec(), TestFuncSpec(num_params=3)], num_params=2),
            TestClassSpec(
                "Test4",
                [TestFuncSpec(), TestFuncSpec()],
                nested_test_class_specs=[
                    TestClassSpec("TestNested1", [TestFuncSpec(), TestFuncSpec()]),
                    TestClassSpec("TestNested2", [TestFuncSpec(), TestFuncSpec(num_params=3)]),
                    TestClassSpec("TestNested3", [TestFuncSpec(), TestFuncSpec(num_params=2)], num_params=3),
                ],
            ),
            TestClassSpec(
                "Test5",
                [TestFuncSpec(), TestFuncSpec()],
                num_params=2,
                nested_test_class_specs=[
                    TestClassSpec("TestNested1", [TestFuncSpec(), TestFuncSpec()]),
                    TestClassSpec("TestNested2", [TestFuncSpec(), TestFuncSpec(num_params=3)]),
                    TestClassSpec("TestNested3", [TestFuncSpec(), TestFuncSpec(num_params=2)], num_params=3),
                ],
            ),
        ]
    )
    # file4: A mix of everything above, inside a sub directory
    test_file_spec4 = TestFileSpec(
        [*test_file_spec1.test_specs, *test_file_spec2.test_specs, *test_file_spec3.test_specs],
        test_dir="tests_something1",
    )
    return [test_file_spec1, test_file_spec2, test_file_spec3, test_file_spec4]


@pytest.fixture
def generate_test_files(pytester: Pytester, test_file_specs: list[TestFileSpec]) -> None:
    """Generate test files with given test file specs"""
    test_files = {}
    for i, test_file_spec in enumerate(test_file_specs, start=1):
        test_filename = f"test_{i}"
        if test_dir := test_file_spec.test_dir:
            test_filename = test_dir + os.sep + test_filename
        test_files[test_filename] = generate_test_code(test_file_spec)
    pytester.makepyfile(**test_files)
