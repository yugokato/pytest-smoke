pytest-smoke
======================

[![PyPI](https://img.shields.io/pypi/v/pytest-smoke)](https://pypi.org/project/pytest-smoke/)
[![Supported Python
versions](https://img.shields.io/pypi/pyversions/pytest-smoke.svg)](https://pypi.org/project/pytest-smoke/)
[![test](https://github.com/yugokato/pytest-smoke/actions/workflows/test.yml/badge.svg)](https://github.com/yugokato/pytest-smoke/actions/workflows/test.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/yugokato/pytest-smoke/main.svg)](https://results.pre-commit.ci/latest/github/yugokato/pytest-smoke/main)
[![Code style ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)

A `pytest` plugin that provides a quick way to perform smoke testing against a large test suite by limiting the 
number of tests executed from each test function (or specified scope) to a value of `N`.  
You can specify `N` as either a fixed number or a percentage, allowing you to scale the test execution down to a smaller 
subset.


## Installation

```
pip install pytest-smoke
```


## Usage

This plugin provides the following command options:
```
$ pytest -h

<snip>

Smoke testing:
  --smoke=[N]           Run only N tests from each test function or specified scope.
                        If N is explicitly provided to the option, it can be a number (e.g. 5) or a percentage (e.g. 10%).
                        Otherwise, the default value of 1 will be applied.
  --smoke-scope=SCOPE   Specify the scope at which the value of N from the above options is applied.
                        The plugin provides the following predefined scopes, as well as custom user-defined scopes via a hook:
                        - function: Applies to each test function (default)
                        - class: Applies to each test class
                        - auto: Applies function scope for test functions, class scope for test methods
                        - file: Applies to each test file
                        - all: Applies to the entire test suite
  --smoke-select-mode=MODE
                        Specify the mode for selecting tests from each scope.
                        The plugin provides the following predefined values, as well as custom user-defined values via a hook:
                        - first: The first N tests (default)
                        - last: The last N tests
                        - random: N randomly selected tests
```

> - The `--smoke` option is required to use any `pytest-smoke` plugin functionality
> - The `--smoke-scope` and `--smoke-select-mode` options also support any custom values, as long as they are handled in the hook. See the "Hooks" section below
> - You can override the plugin's default values for `N`, `SCOPE`, and `MODE` using INI options. See the "INI Options" section below
> - When using the [pytest-xdist](https://pypi.org/project/pytest-xdist/) plugin for parallel testing, you can configure the `pytest-smoke` plugin to replace the default scheduler with a custom distribution algorithm that distributes tests based on the smoke scope


## Examples

Given you have the following test code:

```python
import pytest


def test_something1():
    pass
    
@pytest.mark.parametrize("p", range(10))
def test_something2(p):
    pass
    
@pytest.mark.parametrize("p", range(20))
def test_something3(p):
    pass
```

You can run smoke tests with the `--smoke` option. Here are some basic examples:

- Run only the first test from each test function
```
$ pytest -v --smoke
======================== test session starts ==========================
<snip>
collected 31 items / 28 deselected / 3 selected

tests/test_something.py::test_something1 PASSED                  [ 33%]
tests/test_something.py::test_something2[0] PASSED               [ 66%]
tests/test_something.py::test_something3[0] PASSED               [100%]

=================== 3 passed, 28 deselected in 0.02s ===================
```

- Run up to 3 tests from each test function (`N`=3)
```
$ pytest -v --smoke 3
======================== test session starts ==========================
<snip>
collected 31 items / 24 deselected / 7 selected

tests/test_something.py::test_something1 PASSED                  [ 14%]
tests/test_something.py::test_something2[0] PASSED               [ 28%]
tests/test_something.py::test_something2[1] PASSED               [ 42%]
tests/test_something.py::test_something2[2] PASSED               [ 57%]
tests/test_something.py::test_something3[0] PASSED               [ 71%]
tests/test_something.py::test_something3[1] PASSED               [ 85%]
tests/test_something.py::test_something3[2] PASSED               [100%]

=================== 7 passed, 24 deselected in 0.02s ===================
```

- Run 20% of tests from each test function (`N`=20%)
```
$ pytest -v --smoke 20%
======================== test session starts ==========================
<snip>
collected 31 items / 24 deselected / 7 selected

tests/test_something.py::test_something1 PASSED                  [ 14%]
tests/test_something.py::test_something2[0] PASSED               [ 28%]
tests/test_something.py::test_something2[1] PASSED               [ 42%]
tests/test_something.py::test_something3[0] PASSED               [ 57%]
tests/test_something.py::test_something3[1] PASSED               [ 71%]
tests/test_something.py::test_something3[2] PASSED               [ 85%]
tests/test_something.py::test_something3[3] PASSED               [100%]

=================== 7 passed, 24 deselected in 0.02s ===================
```


## Markers

### `@pytest.mark.smoke(mustpass=False)`
Collected tests explicitly marked with `@pytest.mark.smoke` are considered "critical" smoke tests while ones without 
this marker are considered "regular" smoke tests. Additionally, if the optional `mustpass` keyword argument is set to 
`True` in the marker, the test is considered a "must-pass" critical smoke test. 

By default, this categorization has no impact on the plugin. However, when the `smoke_marked_tests_as_critical` 
INI option is set to `true`, the plugin will apply the following behavior:
- All collected critical tests are automatically included, in addition to the regular tests selected as part of `N`
- Execute all critical smoke tests first, before any regular smoke tests
- If any "must-pass" test fails, all subsequent regular smoke tests will be skipped

> This feature assumes that tests will run sequentially. It will not work when running tests in parallel using a plugin like `pytest-xdist`


## Hooks

The plugin provides the following hooks to customize or extend the plugin's capabilities: 

### `pytest_smoke_generate_group_id(item, scope)`
This hook allows you to implement your own custom scopes for the `--smoke-scope` option, or override the logic of the 
predefined scopes. Items with the same group ID are grouped together and are considered to be in the same scope, 
at which `N` is applied.  
Any custom values passed to the  `--smoke-scope` option must be handled in this hook.

### `pytest_smoke_include(item, scope)`
Return `True` for tests that should be included as "additional" tests. These tests will not be counted towards the 
calculation of `N`.

### `pytest_smoke_exclude(item, scope)`
Return `True` for tests that should not be selected. These items will not be included in the total number of tests to 
which `N`% is applied. An example use case is to prevent tests that are marked with `skip` and/or `xfail` from being 
selected.  
Note that this hook takes precedence over any other options provided by the plugin.

### `pytest_smoke_sort_by_select_mode(items, scope, select_mode)`
This hook allows you to implement your own custom select modes for the `--smoke-select-mode` option. Return sorted items 
to implement a test selection logic for the custom select mode. The plugin will pick `N` tests from each scope group 
based on the sorted items, meaning that an item appearing earlier in the same scope group has a higher chance of being 
selected.  
Any custom values passed to the `--smoke-select-mode` option must be handled in this hook.  
Note that the hook does not affect the test execution order.


## INI Options

You can override the plugin's default values by setting the following options in a configuration 
file (pytest.ini, pyproject.toml, etc.).  

### `smoke_default_n`
The default `N` value to be applied when not provided to the `--smoke` option.  
Plugin default: `1`

### `smoke_default_scope`
The default smoke scope to be applied when not explicitly specified with the `--smoke-scope` option.  
Plugin default: `function`

### `smoke_default_select_mode`
The default smoke select mode to be applied when not explicitly specified with the `--smoke-select-mode` 
option.  
Plugin default: `first`

### `smoke_default_xdist_dist_by_scope`
When using the [pytest-xdist](https://pypi.org/project/pytest-xdist/) plugin (>=2.3.0) for parallel testing, this 
option replaces the default scheduler with a custom distribution algorithm that distributes tests based on the smoke 
scope. When enabled, the custom scheduler will be automatically used when the `-n`/`--numprocesses` option is used 
without a dist option (`--dist` or `-d`).  
Plugin default: `false`

### `smoke_marked_tests_as_critical`
Treat tests marked with `@pytest.mark.smoke` as "critical" smoke tests.    
Plugin default: `false`
