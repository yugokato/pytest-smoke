from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import chain

from pytest_smoke.plugin import DEFAULT_N, SmokeScope
from pytest_smoke.utils import scale_down

TEST_NAME_BASE = "test_something"


@dataclass
class TestFileSpec:
    """Specification of a test file"""

    __test__ = False

    test_specs: list[TestFuncSpec | TestClassSpec] = field(default_factory=list)


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


def generate_test_code(test_spec: TestFileSpec | TestFuncSpec) -> str:
    """Generate test code from the test file spec

    :param test_spec: Test file spec or Test func spec
    """
    param_c = "c"
    param_f = "f"
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
                param_c, num_params=test_class_spec.num_params, param_marker=test_class_spec.param_marker
            )
        code += f"class {test_class_spec.name}:\n"

    def add_function(name: str, test_func_spec: TestFuncSpec, test_class_spec: TestClassSpec = None):
        nonlocal code
        params = []
        if test_class_spec and test_class_spec.num_params:
            params.append(param_c)
        if test_func_spec.num_params:
            params.append(param_f)
            add_parametrize_marker(
                param_f,
                num_params=test_func_spec.num_params,
                param_marker=test_func_spec.param_marker,
                with_indent=bool(test_class_spec),
            )
        sig = ", ".join(params)
        if test_class_spec:
            sig = "self, " + sig
            code += "\t"
        code += f"def {name}({sig}):\tpass\n\n"

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
    n = n or str(DEFAULT_N)
    is_scale = n.endswith("%")
    test_class_specs = get_test_class_specs(test_file_specs)
    if is_scale:
        scale = float(n[:-1])
        if scope == SmokeScope.ALL:
            num_expected_tests = scale_down(get_num_tests(*test_file_specs), scale)
        elif scope == SmokeScope.FILE:
            num_expected_tests = sum([int(scale_down(get_num_tests(*x.test_specs), scale)) for x in test_file_specs])
        elif scope == SmokeScope.AUTO:
            num_expected_tests = sum(
                [
                    *(int(scale_down(get_num_tests(x), scale)) for x in test_class_specs),
                    *(
                        int(scale_down(get_num_tests(x), scale))
                        for x in get_test_func_specs(test_file_specs, exclude_class=True)
                    ),
                ]
            )
        elif scope == SmokeScope.CLASS:
            num_expected_tests = sum([int(scale_down(get_num_tests(x), scale)) for x in test_class_specs])
        else:
            num_expected_tests = sum(
                [int(scale_down(get_num_tests(x), scale)) for x in get_test_func_specs(test_file_specs)]
            )
    else:
        if scope == SmokeScope.ALL:
            num_expected_tests = min([int(n), get_num_tests(*test_file_specs)])
        elif scope == SmokeScope.FILE:
            num_expected_tests = sum([min([int(n), get_num_tests(*x.test_specs)]) for x in test_file_specs])
        elif scope == SmokeScope.AUTO:
            num_expected_tests = sum(
                [
                    *(min([int(n), get_num_tests(x)]) for x in test_class_specs),
                    *(
                        min([int(n), get_num_tests(x)])
                        for x in get_test_func_specs(test_file_specs, exclude_class=True)
                    ),
                ]
            )
        elif scope == SmokeScope.CLASS:
            num_expected_tests = sum([min([int(n), get_num_tests(x)]) for x in test_class_specs])
        else:
            num_expected_tests = sum([min([int(n), get_num_tests(x)]) for x in get_test_func_specs(test_file_specs)])

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
