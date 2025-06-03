from __future__ import annotations

import ast
from collections.abc import Callable, Generator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from functools import reduce, wraps
from itertools import chain
from typing import Any

import pytest

from pytest_smoke.plugin import DEFAULT_N, SmokeScope
from pytest_smoke.utils import scale_down

TEST_NAME_BASE = "test_something"


@dataclass
class TestFileSpec:
    """Specification of a test file"""

    __test__ = False

    test_specs: list[TestFuncSpec | TestClassSpec] = field(default_factory=list)
    test_dir: str | None = None


@dataclass
class TestClassSpec:
    """Specification of a test class"""

    __test__ = False

    name: str
    test_func_specs: list[TestFuncSpec] = field(default_factory=list)
    num_params: int = 0
    param_marker: Callable[[int], str | None] | None = None
    nested_test_class_specs: list[TestClassSpec] = field(default_factory=list)
    parent_test_class_spec: TestClassSpec | None = field(init=False, default=None)
    param_arg_name: str = field(init=False, default="")

    def __post_init__(self) -> None:
        if self.num_params:
            self.param_arg_name = f"c{COUNTER.get_next()}"
        for test_func_spec in self.test_func_specs:
            test_func_spec.test_class_spec = self
        for nested_test_class_spec in self.nested_test_class_specs:
            nested_test_class_spec.parent_test_class_spec = self

    @property
    def param_arg_names(self) -> list[str]:
        def get_arg_names(class_spec: TestClassSpec, arg_names: list[str] | None = None) -> list[str]:
            if arg_names is None:
                arg_names = []
            if arg_name := class_spec.param_arg_name:
                arg_names.append(arg_name)
            if class_spec.parent_test_class_spec:
                get_arg_names(class_spec.parent_test_class_spec, arg_names=arg_names)
            return arg_names

        return get_arg_names(self)

    @property
    def has_parametrized_test(self) -> bool:
        def is_test_class_parametrized(test_class_spec: TestClassSpec) -> bool:
            return test_class_spec.num_params > 0 or (
                test_class_spec.parent_test_class_spec is not None
                and is_test_class_parametrized(test_class_spec.parent_test_class_spec)
            )

        if is_test_class_parametrized(self):
            return True

        for test_spec in self.test_func_specs:
            if test_spec.num_params:
                return True
        return False


@dataclass
class TestFuncSpec:
    """Specification of a test function"""

    __test__ = False
    param_arg_name = "p"

    num_params: int = 0
    test_class_spec: TestClassSpec | None = field(init=False, default=None)
    param_marker: Callable[[int], str | None] | None = None
    func_body: str | None = None

    @property
    def has_parametrized_test(self) -> bool:
        if self.num_params > 0 or (self.test_class_spec and self.test_class_spec.has_parametrized_test):
            return True
        return False


class Counter:
    def __init__(self) -> None:
        self._count = 0

    def get_next(self) -> int:
        self._count += 1
        return self._count


COUNTER = Counter()


def generate_test_code(test_spec: TestFileSpec | TestFuncSpec) -> str:
    """Generate test code from the test file spec

    :param test_spec: Test file spec or Test func spec
    """
    code = "import pytest\n"

    def add_parametrize_marker(
        *param_names: str,
        num_params: int = 1,
        param_marker: Callable[[int], str | None] | None = None,
        indent: int = 0,
    ) -> None:
        nonlocal code
        params = ", ".join(param_names)
        tabs = "\t" * indent
        if param_marker:
            param_values = ", ".join(
                [
                    (f"pytest.param({p}, marks=pytest.mark.{param_marker(p)})" if param_marker(p) else str(p))
                    for p in range(num_params)
                ]
            )
            code += f"{tabs}@pytest.mark.parametrize('{params}', [{param_values}])\n"
        else:
            code += f"{tabs}@pytest.mark.parametrize('{params}', range({num_params}))\n"

    def add_class(test_class_spec: TestClassSpec, indent: int = 0) -> None:
        nonlocal code
        if test_class_spec.num_params:
            add_parametrize_marker(
                test_class_spec.param_arg_name,
                num_params=test_class_spec.num_params,
                param_marker=test_class_spec.param_marker,
                indent=indent,
            )

        tabs = "\t" * indent
        code += f"{tabs}class {test_class_spec.name}:\n"
        for j, func_spec in enumerate(test_class_spec.test_func_specs, start=1):
            add_function(f"{TEST_NAME_BASE}{j}", func_spec, indent=indent + 1)

        for nested_test_class in test_class_spec.nested_test_class_specs:
            add_class(nested_test_class, indent=indent + 1)

    def add_function(name: str, test_func_spec: TestFuncSpec, indent: int = 0) -> None:
        nonlocal code
        params: list[str] = []
        test_class_spec = test_func_spec.test_class_spec
        if test_class_spec and test_class_spec.param_arg_names:
            params.extend(test_class_spec.param_arg_names)
        if test_func_spec.num_params:
            params.append(test_func_spec.param_arg_name)
            add_parametrize_marker(
                test_func_spec.param_arg_name,
                num_params=test_func_spec.num_params,
                param_marker=test_func_spec.param_marker,
                indent=indent,
            )
        if test_class_spec:
            params = ["self", *params]
        func_args = ", ".join(params)
        func_body = test_func_spec.func_body or "\tpass\n"
        tabs = "\t" * indent
        code += f"{tabs}def {name}({func_args}):{func_body}\n"

    if isinstance(test_spec, TestFileSpec):
        for i, spec in enumerate(test_spec.test_specs, start=1):
            if isinstance(spec, TestClassSpec):
                add_class(spec)
            else:
                add_function(f"{TEST_NAME_BASE}{i}", spec)
    else:
        add_function(TEST_NAME_BASE, test_spec)

    try:
        ast.parse(code)
    except Exception as e:
        raise RuntimeError(
            f"Failed to parse the generated code:\nError: {type(e).__name__} {e}\nGenerated code:\n{code}"
        )
    return code


def get_num_tests(*test_specs: TestFuncSpec | TestClassSpec | TestFileSpec, include_nested_classes: bool = True) -> int:
    """Calculate the total number of tests from the given test specs

    :param test_specs: One or more TestFuncSpec, TestClassSpec, or TestFileSpec objects to calculate the total number of
                       tests against
    :param include_nested_classes: Count tests defined inside nested classes, if any
    """

    def _get_num_tests(test_func_spec: TestFuncSpec) -> int:
        def collect_num_params_on_test_class(current_class_spec: TestClassSpec) -> None:
            num_params.append(current_class_spec.num_params or 1)
            if current_class_spec.parent_test_class_spec:
                collect_num_params_on_test_class(current_class_spec.parent_test_class_spec)

        num_params = [test_func_spec.num_params or 1]
        if test_func_spec.test_class_spec:
            collect_num_params_on_test_class(test_func_spec.test_class_spec)
        return reduce(lambda x, y: x * y, num_params)

    num_tests = 0
    for spec in test_specs:
        if isinstance(spec, TestFileSpec):
            num_tests += get_num_tests(*spec.test_specs, include_nested_classes=include_nested_classes)
        elif isinstance(spec, TestClassSpec):
            num_tests += get_num_tests(*spec.test_func_specs, include_nested_classes=include_nested_classes)
            if include_nested_classes and spec.nested_test_class_specs:
                num_tests += get_num_tests(*spec.nested_test_class_specs, include_nested_classes=include_nested_classes)
        else:
            num_tests += _get_num_tests(spec)
    return num_tests


def get_num_tests_to_be_selected(test_file_specs: list[TestFileSpec], n: str | None, scope: SmokeScope | None) -> int:
    """Calculate the number of expected tests to be selected from the test file specs for the given conditions

    :param test_file_specs: Test file specs
    :param n: N value given for the smoke option
    :param scope: Smoke scope value
    """
    scopes_handle_class_specs = [None, SmokeScope.CLASS, SmokeScope.AUTO]

    def get_num_expected_tests(
        *test_specs: TestFuncSpec | TestClassSpec | TestFileSpec, effective_scope: SmokeScope | None = scope
    ) -> int:
        if effective_scope == SmokeScope.AUTO:
            raise ValueError("Must give one of the non-Auto scopes")

        n_ = n or str(DEFAULT_N)
        include_nested_classes = effective_scope not in scopes_handle_class_specs
        if n_.endswith("%"):
            scale = float(n_[:-1])
            return int(scale_down(get_num_tests(*test_specs, include_nested_classes=include_nested_classes), scale))
        else:
            return min([int(n_), get_num_tests(*test_specs, include_nested_classes=include_nested_classes)])

    if scope == SmokeScope.ALL:
        num_expected_tests = get_num_expected_tests(*test_file_specs)
    elif scope == SmokeScope.DIRECTORY:
        test_specs_per_dir: dict[str | None, list[TestFuncSpec | TestClassSpec]] = {}
        for test_file_spec in test_file_specs:
            test_specs_per_dir.setdefault(test_file_spec.test_dir, []).extend(test_file_spec.test_specs)
        num_expected_tests = sum(get_num_expected_tests(*test_specs) for test_specs in test_specs_per_dir.values())
    elif scope == SmokeScope.FILE:
        num_expected_tests = sum(get_num_expected_tests(*x.test_specs) for x in test_file_specs)
    elif scope == SmokeScope.CLASS:
        test_class_specs = get_test_class_specs(test_file_specs)
        num_expected_tests = sum(get_num_expected_tests(x) for x in test_class_specs)
    elif scope == SmokeScope.FUNCTION:
        num_expected_tests = sum(get_num_expected_tests(x) for x in get_test_func_specs(test_file_specs))
    else:
        # default scope = auto
        num_expected_tests = 0
        for test_file_spec in test_file_specs:
            test_func_specs, test_class_specs = _get_test_specs_per_type([test_file_spec])
            if test_func_specs:
                if any(x.has_parametrized_test for x in test_func_specs):
                    num_expected_tests += sum(
                        get_num_expected_tests(x, effective_scope=SmokeScope.FUNCTION) for x in test_func_specs
                    )
                else:
                    num_expected_tests += get_num_expected_tests(*test_func_specs, effective_scope=SmokeScope.FILE)
            if test_class_specs:
                for test_class_spec in test_class_specs:
                    if test_class_spec.has_parametrized_test:
                        num_expected_tests += sum(
                            get_num_expected_tests(x, effective_scope=SmokeScope.FUNCTION)
                            for x in test_class_spec.test_func_specs
                        )
                    else:
                        num_expected_tests += get_num_expected_tests(test_class_spec, effective_scope=SmokeScope.CLASS)
    return num_expected_tests


def get_test_class_specs(test_file_specs: list[TestFileSpec]) -> list[TestClassSpec]:
    """Returns all TestClassSpec objects from test file specs

    :param test_file_specs: Test file specs
    """
    _, test_class_specs = _get_test_specs_per_type(test_file_specs)
    return test_class_specs


def get_test_func_specs(test_file_specs: list[TestFileSpec], exclude_class: bool = False) -> list[TestFuncSpec]:
    """Returns all TestFuncSpec objects from test file specs

    :param test_file_specs: Test file specs
    :param exclude_class: Exclude test func specs defined under a test class spec
    """
    test_func_specs, test_class_specs = _get_test_specs_per_type(test_file_specs)
    if exclude_class:
        return test_func_specs
    else:
        test_class_func_specs = list(chain(*[x.test_func_specs for x in test_class_specs]))
        return [*test_func_specs, *test_class_func_specs]


def _get_test_specs_per_type(test_file_specs: list[TestFileSpec]) -> tuple[list[TestFuncSpec], list[TestClassSpec]]:
    test_specs = list(chain(*[x.test_specs for x in test_file_specs]))
    test_class_specs = [x for x in test_specs if isinstance(x, TestClassSpec)]
    nested_test_class_specs = list(chain(*[x.nested_test_class_specs for x in test_class_specs]))
    func_specs = [x for x in test_specs if isinstance(x, TestFuncSpec)]
    return (func_specs, [*test_class_specs, *nested_test_class_specs])


@contextmanager
def mock_column_width(width: int) -> Generator[None, Any, None]:
    """Temporarily mock the column width

    :param width: Column width
    """
    mp = pytest.MonkeyPatch()
    mp.setenv("COLUMNS", str(width))
    try:
        yield
    finally:
        mp.undo()


def patch_runpytest(f: Callable[..., Any]) -> Callable[..., Any]:
    """A decorator for patching pytester.runpytest() to temporarily mock the column width during a test when the -v
    option is given to ensure the stdout is captured in a standard terminal size.
    This prevents the flaky test results caused by a teser's actual terminal size
    """

    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with mock_column_width(150) if "-v" in args else nullcontext():
            return f(*args, **kwargs)

    return wrapper
