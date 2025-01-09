from __future__ import annotations

import ast
from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from functools import wraps
from itertools import chain
from typing import Optional

import pytest

from pytest_smoke import smoke
from pytest_smoke.plugin import DEFAULT_N, SmokeScope
from pytest_smoke.utils import scale_down

TEST_NAME_BASE = "test_something"
PARAMETRIZED_ARG_NAME_CLS = "p_c"
PARAMETRIZED_ARG_NAME_FUNC = "p_f"

requires_xdist = pytest.mark.skipif(not smoke.is_xdist_installed, reason="pytest-xdist is required")


@dataclass
class TestFileSpec:
    """Specification of a test file"""

    __test__ = False

    test_specs: list[TestFuncSpec | TestClassSpec] = field(default_factory=list)
    test_dir: Optional[str] = None


@dataclass
class TestClassSpec:
    """Specification of a test class"""

    __test__ = False

    name: str
    test_func_specs: list[TestFuncSpec] = field(default_factory=list)
    num_params: int = 0
    param_marker: Callable[[int], str | None] = None

    def __post_init__(self):
        for test_func_spec in self.test_func_specs:
            test_func_spec.test_class_spec = self


@dataclass
class TestFuncSpec:
    """Specification of a test function"""

    __test__ = False

    num_params: int = 0
    test_class_spec: TestClassSpec = field(init=False, default=None)
    param_marker: Callable[[int], str | None] = None
    func_body: str = None


def generate_test_code(test_spec: TestFileSpec | TestFuncSpec) -> str:
    """Generate test code from the test file spec

    :param test_spec: Test file spec or Test func spec
    """
    code = "import pytest\n"

    def add_parametrize_marker(
        *param_names: str,
        num_params: int = 0,
        with_indent: bool = False,
        param_marker: Callable[[int], str | None] = None,
    ):
        nonlocal code
        params = ", ".join(param_names)
        if with_indent:
            code += "\t"
        if param_marker:
            param_values = ", ".join(
                [
                    (f"pytest.param({p}, marks=pytest.mark.{param_marker(p)})" if param_marker(p) else str(p))
                    for p in range(num_params)
                ]
            )
            code += f"@pytest.mark.parametrize('{params}', [{param_values}])\n"
        else:
            code += f"@pytest.mark.parametrize('{params}', range({num_params}))\n"

    def add_class(test_class_spec: TestClassSpec):
        nonlocal code
        if test_class_spec.num_params:
            add_parametrize_marker(
                PARAMETRIZED_ARG_NAME_CLS,
                num_params=test_class_spec.num_params,
                param_marker=test_class_spec.param_marker,
            )
        code += f"class {test_class_spec.name}:\n"

    def add_function(name: str, test_func_spec: TestFuncSpec, test_class_spec: TestClassSpec = None):
        nonlocal code
        params = []
        if test_class_spec and test_class_spec.num_params:
            params.append(PARAMETRIZED_ARG_NAME_CLS)
        if test_func_spec.num_params:
            params.append(PARAMETRIZED_ARG_NAME_FUNC)
            add_parametrize_marker(
                PARAMETRIZED_ARG_NAME_FUNC,
                num_params=test_func_spec.num_params,
                param_marker=test_func_spec.param_marker,
                with_indent=bool(test_class_spec),
            )
        sig = ", ".join(params)
        if test_class_spec:
            sig = "self, " + sig
            code += "\t"
        func_body = test_func_spec.func_body or "\tpass\n"
        code += f"def {name}({sig}):{func_body}\n"

    if isinstance(test_spec, TestFileSpec):
        for i, spec in enumerate(test_spec.test_specs, start=1):
            if isinstance(spec, TestClassSpec):
                add_class(spec)
                for j, func_spec in enumerate(spec.test_func_specs, start=1):
                    add_function(f"{TEST_NAME_BASE}{j}", func_spec, test_class_spec=spec)
            else:
                add_function(f"{TEST_NAME_BASE}{i}", spec)
    else:
        add_function(TEST_NAME_BASE, test_spec)

    ast.parse(code)
    return code


def get_num_tests(*test_specs: TestFuncSpec | TestClassSpec | TestFileSpec) -> int:
    """Calculate the total number of tests from the given test specs

    :param test_specs: One or more TestFuncSpec, TestClassSpec, or TestFileSpec objects to calculate the total number of
                       tests against
    """
    num_tests = 0
    for spec in test_specs:
        if isinstance(spec, TestFileSpec):
            num_tests += get_num_tests(*spec.test_specs)
        elif isinstance(spec, TestClassSpec):
            num_tests += get_num_tests(*spec.test_func_specs)
        else:
            if spec.test_class_spec:
                num_outer_params = spec.test_class_spec.num_params or 1
            else:
                num_outer_params = 1
            num_tests += num_outer_params * (spec.num_params or 1)
    return num_tests


def get_num_tests_to_be_selected(test_file_specs: list[TestFileSpec], n: str | None, scope: SmokeScope | None) -> int:
    """Calculate the number of expected tests to be selected from the test file specs for the given conditions

    :param test_file_specs: Test file specs
    :param n: N value given for the smoke option
    :param scope: Smoke scope value
    """

    def get_num_expected_tests_per_scope(*test_specs):
        n_ = n or str(DEFAULT_N)
        if n_.endswith("%"):
            scale = float(n_[:-1])
            return int(scale_down(get_num_tests(*test_specs), scale))
        else:
            return min([int(n_), get_num_tests(*test_specs)])

    test_class_specs = get_test_class_specs(test_file_specs) if scope in [SmokeScope.AUTO, SmokeScope.CLASS] else None
    if scope == SmokeScope.ALL:
        num_expected_tests = get_num_expected_tests_per_scope(*test_file_specs)
    elif scope == SmokeScope.DIRECTORY:
        test_specs_per_dir = {}
        for test_file_spec in test_file_specs:
            test_specs_per_dir.setdefault(test_file_spec.test_dir, []).extend(test_file_spec.test_specs)
        num_expected_tests = sum(
            get_num_expected_tests_per_scope(*test_specs) for test_specs in test_specs_per_dir.values()
        )
    elif scope == SmokeScope.FILE:
        num_expected_tests = sum(get_num_expected_tests_per_scope(*x.test_specs) for x in test_file_specs)
    elif scope == SmokeScope.AUTO:
        num_expected_tests = sum(
            [
                *(get_num_expected_tests_per_scope(x) for x in test_class_specs),
                *(
                    get_num_expected_tests_per_scope(x)
                    for x in get_test_func_specs(test_file_specs, exclude_class=True)
                ),
            ]
        )
    elif scope == SmokeScope.CLASS:
        num_expected_tests = sum(get_num_expected_tests_per_scope(x) for x in test_class_specs)
    else:
        # default = function
        num_expected_tests = sum(get_num_expected_tests_per_scope(x) for x in get_test_func_specs(test_file_specs))

    return num_expected_tests


def get_test_class_specs(test_file_specs: list[TestFileSpec]) -> list[TestClassSpec]:
    """Returns all TestClassSpec objects from test file specs

    :param test_file_specs: Test file specs
    """
    test_specs = list(chain(*[x.test_specs for x in test_file_specs]))
    return [x for x in test_specs if isinstance(x, TestClassSpec)]


def get_test_func_specs(test_file_specs: list[TestFileSpec], exclude_class: bool = False) -> list[TestFuncSpec]:
    """Returns all TestFuncSpec objects from test file specs

    :param test_file_specs: Test file specs
    :param exclude_class: Exclude test func specs defined under a test class spec
    """
    test_specs = list(chain(*[x.test_specs for x in test_file_specs]))
    if exclude_class:
        test_specs = [x for x in test_specs if not isinstance(x, TestClassSpec)]
    return list(chain(*[(x.test_func_specs if isinstance(x, TestClassSpec) else [x]) for x in test_specs]))


@contextmanager
def mock_column_width(width: int):
    """Temporarily mock the column width

    :param width: Column width
    """
    mp = pytest.MonkeyPatch()
    mp.setenv("COLUMNS", str(width))
    try:
        yield
    finally:
        mp.undo()


def patch_runpytest(f):
    """A decorator for patching pytester.runpytest() to temporarily mock the column width during a test when the -v
    option is given to ensure the stdout is captured in a standard terminal size.
    This prevents the flaky test results caused by a teser's actual terminal size
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        with mock_column_width(150) if "-v" in args else nullcontext():
            return f(*args, **kwargs)

    return wrapper
